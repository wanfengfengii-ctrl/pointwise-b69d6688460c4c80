import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from catalog.revision_queries import get_revision
from catalog.revisions import put
from catalog.storage import open_source
from demo import load_sample, seed_source
from exchange.packages import pack
from releases.catalog import freeze


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(TemporaryDirectory())
        self.path = Path(self.directory) / 'source.sqlite'
        self.source = self.enterContext(closing(open_source(self.path)))

    def test_n1_conflict_preserves_revision_for_release(self):
        original = put(self.source, 'C', '1', 10)
        with self.assertRaisesRegex(ValueError, 'conflicting source revision'):
            put(self.source, 'C', '1', 20)
        self.assertEqual(get_revision(self.source, 'C', '1'), original)
        freeze(self.source, 'R1', {'C': '1'}, ['C'])
        self.assertEqual([(r.key, r.revision, r.payload) for r in pack(self.source, 'R1').records], [('C', '1', 10)])

    def test_n1_idempotent_under_reference_permutation(self):
        saved = put(self.source, 'A', '1', -7, [('z', 'C'), ('a', 'B')])
        self.assertEqual(put(self.source, 'A', '1', -7, {'a': 'B', 'z': 'C'}), saved)
        self.assertEqual(saved.references, (('a', 'B'), ('z', 'C')))
        with self.assertRaises(ValueError):
            put(self.source, 'A', '1', -7, {'a': 'C', 'z': 'B'})
        self.assertEqual(get_revision(self.source, 'A', '1'), saved)

    def test_n1_invalid_record_has_no_persisted_revision(self):
        bad = [
            ('A', '1', None, ()), ('A', '1', True, ()), ('A', '1', 10.0, ()),
            ('A', '1', '10', ()), ('', '1', 1, ()), ('A', '', 1, ()),
            ('A', '1', 1, [('name', 'B'), ('name', 'B')]),
            ('A', '1', 1, [('', 'B')]), ('A', '1', 1, [('name', '')]),
            ('A', '1', 1, [('name',)]), ('A', '1', 1, None),
        ]
        for key, revision, value, references in bad:
            with self.subTest(key=key, revision=revision, value=value, references=references):
                with self.assertRaises(ValueError):
                    put(self.source, key, revision, value, references)
        with self.assertRaises(TypeError):
            put(self.source, 'A', '1')
        self.assertIsNone(get_revision(self.source, 'A', '1'))
        self.assertEqual(self.source.execute('SELECT COUNT(*) FROM source_revisions').fetchone(), (0,))

    def test_n1_reinitialize_and_seed_again_preserve_user_data(self):
        sample, _ = load_sample()
        seed_source(self.source, sample)
        original = put(self.source, 'user', 'own', -11)
        freeze(self.source, 'user-release', {'user': 'own'}, ['user'])
        self.source.close()
        with closing(open_source(self.path)) as reopened:
            seed_source(reopened, sample)
            self.assertEqual(get_revision(reopened, 'user', 'own'), original)
            self.assertEqual(pack(reopened, 'user-release').records[0].payload, -11)
            self.assertEqual(pack(reopened, 'R1').entries, ('A', 'D'))
            self.assertEqual(reopened.execute('SELECT COUNT(*) FROM source_revisions').fetchone(), (6,))
            self.assertEqual(reopened.execute('SELECT COUNT(*) FROM frozen_releases').fetchone(), (3,))
