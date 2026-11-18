import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from catalog.revisions import put
from catalog.storage import open_source
from exchange.packages import pack
from releases.catalog import freeze, get_frozen_release


class ReleasesTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.source = self.enterContext(closing(open_source(Path(directory) / 'source.sqlite')))

    def assert_unpublished(self, release_id):
        with self.assertRaises(KeyError):
            get_frozen_release(self.source, release_id)
        with self.assertRaises(KeyError):
            pack(self.source, release_id)

    def test_n2_missing_selected_target_prevents_receipt(self):
        put(self.source, 'A', '1', 0, {'next': 'B'})
        put(self.source, 'B', '1', 10)
        with self.assertRaisesRegex(ValueError, 'unselected key'):
            freeze(self.source, 'R', {'A': '1'}, ['A'])
        self.assert_unpublished('R')
        receipt = freeze(self.source, 'R', {'A': '1', 'B': '1'}, ['A'])
        self.assertEqual(receipt.selection.entries, ('A',))

    def test_n2_transitive_missing_target_prevents_receipt(self):
        put(self.source, 'A', '1', 0, {'next': 'B'})
        put(self.source, 'B', '1', 0, {'next': 'C'})
        put(self.source, 'C', '1', 9)
        with self.assertRaisesRegex(ValueError, "'B'.*'C'"):
            freeze(self.source, 'R', {'A': '1', 'B': '1'}, ['A'])
        self.assert_unpublished('R')

    def test_n2_unknown_revision_even_when_not_reachable(self):
        put(self.source, 'A', '1', 0)
        with self.assertRaisesRegex(KeyError, 'unknown source revision'):
            freeze(self.source, 'R', {'A': '1', 'D': '1'}, ['A'])
        self.assert_unpublished('R')

    def test_n2_entry_must_be_selected(self):
        put(self.source, 'A', '1', 0)
        with self.assertRaisesRegex(ValueError, 'entry'):
            freeze(self.source, 'R', {'A': '1'}, ['D'])
        self.assert_unpublished('R')

    def test_n2_cycle_qualification(self):
        put(self.source, 'A', '1', 5, {'peer': 'B'})
        put(self.source, 'B', '1', 6, {'peer': 'A'})
        receipt = freeze(self.source, 'cycle', {'A': '1', 'B': '1'}, ['A'])
        self.assertEqual(receipt, get_frozen_release(self.source, 'cycle'))
        self.assertEqual([record.key for record in pack(self.source, 'cycle').records], ['A', 'B'])

    def test_n2_freeze_replay_retains_order_and_repeated_positions(self):
        put(self.source, 'A', '1', 1)
        put(self.source, 'D', '1', 4)
        original = freeze(self.source, 'R', {'A': '1', 'D': '1'}, ['D', 'A', 'D'])
        replayed = freeze(self.source, 'R', {'D': '1', 'A': '1'}, ('D', 'A', 'D'))
        self.assertEqual(replayed, original)
        self.assertEqual(replayed.selection.entries, ('D', 'A', 'D'))
        self.assertEqual(pack(self.source, 'R').entries, ('D', 'A', 'D'))

    def test_n2_release_conflict_does_not_replace_fixed_selection(self):
        put(self.source, 'A', '1', 1)
        put(self.source, 'A', '2', 2)
        put(self.source, 'D', '1', 4)
        original = freeze(self.source, 'R', {'A': '1', 'D': '1'}, ['A', 'D'])
        for selection, order in [({'A': '2', 'D': '1'}, ['A', 'D']), ({'A': '1', 'D': '1'}, ['D', 'A'])]:
            with self.subTest(selection=selection, order=order):
                with self.assertRaisesRegex(ValueError, 'conflicting frozen release'):
                    freeze(self.source, 'R', selection, order)
        self.assertEqual(get_frozen_release(self.source, 'R'), original)
        self.assertEqual(pack(self.source, 'R').records[0].payload, 1)
