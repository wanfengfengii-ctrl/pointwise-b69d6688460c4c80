import json
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from audit.entrypoints import entries
from audit.inventory import inventory
from audit.traversal import follow
from catalog.revisions import put
from catalog.storage import open_source
from demo import load_sample, seed_source
from exchange.encoding import decode_package, encode_package
from exchange.graph import PackageRecord, ReleasePackage
from exchange.packages import pack
from releases.catalog import freeze
from warehouse.imports import mount
from warehouse.storage import open_warehouse


def cyclic_package(release_id, revision, payload):
    return ReleasePackage(release_id, ('A', 'D'), (
        PackageRecord('A', '1', 0, (('aux', 'B'),)),
        PackageRecord('B', '1', -2, (('back', 'A'), ('cal', 'C'))),
        PackageRecord('C', revision, payload),
        PackageRecord('D', '1', 4),
    ))


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.warehouse = self.enterContext(closing(open_warehouse(self.root / 'warehouse.sqlite')))

    def test_n3_export_only_reachable_records_and_mount_offline(self):
        with closing(open_source(self.root / 'source.sqlite')) as source:
            put(source, 'A', '1', 0, {'cal': 'C'})
            put(source, 'C', '1', 10)
            put(source, 'D', '1', 4)
            freeze(source, 'R', {'D': '1', 'C': '1', 'A': '1'}, ['A'])
            package = pack(source, 'R')
            wire = encode_package(package).encode('utf-8')
        self.assertEqual([record.key for record in package.records], ['A', 'C'])
        self.assertEqual(package.records[0].references, (('cal', 'C'),))
        self.assertEqual(mount(self.warehouse, wire), entries(self.warehouse, 'R'))
        self.assertEqual(follow(self.warehouse, 'R', 0, ['cal']).payload, 10)
        self.assertEqual([row.key for row in inventory(self.warehouse, 'R').rows], ['A', 'C'])

    def test_n3_fixed_snapshot_uses_each_versions_cyclic_closure(self):
        sample, _ = load_sample()
        with closing(open_source(self.root / 'source.sqlite')) as source:
            seed_source(source, sample)
            put(source, 'C', '3', 30)
            first = pack(source, 'R1')
            second = pack(source, 'R2')
            self.assertEqual(pack(source, 'R1'), first)
        for package, revision, value in [(first, '1', 10), (second, '2', 20)]:
            with self.subTest(release=package.release_id):
                self.assertEqual([record.key for record in package.records], ['A', 'B', 'C', 'D'])
                self.assertEqual(package.entries, ('A', 'D'))
                edges = {(node.key, name, target) for node in package.records for name, target in node.references}
                self.assertEqual(edges, {('A', '辅助', 'B'), ('B', '回入口', 'A'), ('B', '校准', 'C')})
                self.assertEqual((package.records[2].revision, package.records[2].payload), (revision, value))
        mount(self.warehouse, second)
        self.assertEqual(follow(self.warehouse, 'R2', 0, ['辅助', '校准']).payload, 20)

    def test_n3_unknown_release(self):
        with closing(open_source(self.root / 'source.sqlite')) as source:
            with self.assertRaises(KeyError):
                pack(source, 'unknown')

    def test_n3_pack_uses_own_selection_regardless_of_pack_order(self):
        sample, _ = load_sample()
        with closing(open_source(self.root / 'source.sqlite')) as source:
            seed_source(source, sample)
            second = pack(source, 'R2')
            first = pack(source, 'R1')
        self.assertEqual([(r.key, r.revision, r.payload) for r in first.records if r.key == 'C'], [('C', '1', 10)])
        self.assertEqual([(r.key, r.revision, r.payload) for r in second.records if r.key == 'C'], [('C', '2', 20)])
        self.assertNotEqual(first, second)

    def test_n3_empty_closure_valid_mount_and_inventory(self):
        with closing(open_source(self.root / 'source.sqlite')) as source:
            put(source, 'D', '1', 4)
            freeze(source, 'empty', {'D': '1'}, [])
            package = pack(source, 'empty')
        self.assertEqual(package.entries, ())
        self.assertEqual(package.records, ())
        self.assertEqual(mount(self.warehouse, encode_package(package)), ())
        self.assertEqual(entries(self.warehouse, 'empty'), ())
        report = inventory(self.warehouse, 'empty')
        self.assertEqual((report.count, report.rows), (0, ()))
        with self.assertRaises(IndexError):
            follow(self.warehouse, 'empty', 0, ())

    def test_n3_deterministic_encoding_and_exact_integer(self):
        huge = -(2**16000 + 17)
        with closing(open_source(self.root / 'source.sqlite')) as source:
            put(source, 'A', '1', 0, [('z', 'C'), ('a', 'D')])
            put(source, 'C', '1', huge)
            put(source, 'D', '1', -4)
            freeze(source, 'R', {'D': '1', 'C': '1', 'A': '1'}, ['D', 'A'])
            package = pack(source, 'R')
        reordered = replace(package, records=tuple(
            replace(record, references=tuple(reversed(record.references))) for record in reversed(package.records)
        ))
        wire = encode_package(package)
        self.assertEqual(wire, encode_package(reordered))
        self.assertEqual(wire, encode_package(decode_package(wire)))
        parsed = decode_package(wire)
        self.assertEqual(parsed.entries, ('D', 'A'))
        self.assertEqual(parsed.records[0].references, (('a', 'D'), ('z', 'C')))
        self.assertTrue(parsed.records[1].payload == huge)
        mount(self.warehouse, wire)
        self.assertTrue(follow(self.warehouse, 'R', 1, ['z']).payload == huge)
        self.assertEqual(follow(self.warehouse, 'R', 0, []).payload, -4)

    def test_n4_replay_equal_wire_permutation_keeps_ids(self):
        package = cyclic_package('R', '1', 10)
        original = mount(self.warehouse, package)
        wire = json.loads(encode_package(package))
        wire['records'].reverse()
        for record in wire['records']:
            record['references'].reverse()
        self.assertEqual(mount(self.warehouse, json.dumps(wire)), original)
        self.assertEqual(entries(self.warehouse, 'R'), original)
        self.assertEqual(self.warehouse.execute('SELECT COUNT(*) FROM instances').fetchone(), (4,))

    def test_n4_mount_conflict_preserves_original(self):
        package = cyclic_package('R', '1', 10)
        original = mount(self.warehouse, package)
        cases = [cyclic_package('R', '1', 11), replace(package, entries=('D', 'A'))]
        for changed in cases:
            with self.subTest(entries=changed.entries):
                with self.assertRaisesRegex(ValueError, 'conflicting mounted release'):
                    mount(self.warehouse, changed)
        self.assertEqual(entries(self.warehouse, 'R'), original)
        self.assertEqual(follow(self.warehouse, 'R', 0, ('aux', 'cal')).payload, 10)
        self.assertEqual(self.warehouse.execute('SELECT COUNT(*) FROM instances').fetchone(), (4,))

    def test_n4_cross_release_equivalence_from_independent_packages(self):
        first = cyclic_package('old', '1', 10)
        second = cyclic_package('new', '2', 20)
        mount(self.warehouse, first)
        mount(self.warehouse, second)
        mount(self.warehouse, replace(first, release_id='same-old'))
        old = {row.key: row.instance_id for row in inventory(self.warehouse, 'old').rows}
        new = {row.key: row.instance_id for row in inventory(self.warehouse, 'new').rows}
        clone = {row.key: row.instance_id for row in inventory(self.warehouse, 'same-old').rows}
        self.assertEqual(old, clone)
        self.assertEqual({key for key in old if old[key] == new[key]}, {'D'})
        self.assertEqual(follow(self.warehouse, 'old', 0, ['aux', 'cal']).payload, 10)
        self.assertEqual(follow(self.warehouse, 'new', 0, ['aux', 'cal']).payload, 20)
        self.assertEqual(self.warehouse.execute('SELECT COUNT(*) FROM instances').fetchone(), (7,))

    def test_n4_deep_structural_difference_prevents_sharing(self):
        cyclic = ReleasePackage('cyclic-root', ('A',), (
            PackageRecord('A', '1', 0, (('next', 'B'),)),
            PackageRecord('B', '1', 0, (('loop', 'A'),)),
        ))
        broken = ReleasePackage('broken-root', ('A',), (
            PackageRecord('A', '1', 0, (('next', 'B'),)),
            PackageRecord('B', '1', 0),
        ))
        first = dict(mount(self.warehouse, cyclic))
        second = dict(mount(self.warehouse, broken))
        first_rows = {row.key: row.instance_id for row in inventory(self.warehouse, 'cyclic-root').rows}
        second_rows = {row.key: row.instance_id for row in inventory(self.warehouse, 'broken-root').rows}
        self.assertNotEqual(second['A'], first['A'])
        self.assertNotEqual(second_rows['B'], first_rows['B'])
        self.assertEqual(follow(self.warehouse, 'cyclic-root', 0, ['next', 'loop']).instance_id, first['A'])
        with self.assertRaises(KeyError):
            follow(self.warehouse, 'broken-root', 0, ['next', 'loop'])

    def test_n4_deep_payload_difference_beyond_direct_targets(self):
        def chain(release_id, payload):
            return ReleasePackage(release_id, ('A',), (
                PackageRecord('A', '1', 0, (('to-b', 'B'),)),
                PackageRecord('B', '1', 0, (('to-c', 'C'),)),
                PackageRecord('C', '1', 0, (('to-d', 'D'),)),
                PackageRecord('D', '1', payload),
            ))
        mount(self.warehouse, chain('chain-old', 10))
        mount(self.warehouse, chain('chain-new', 20))
        first = {row.key: row.instance_id for row in inventory(self.warehouse, 'chain-old').rows}
        second = {row.key: row.instance_id for row in inventory(self.warehouse, 'chain-new').rows}
        for key in ('A', 'B', 'C', 'D'):
            self.assertNotEqual(second[key], first[key])
        self.assertEqual(follow(self.warehouse, 'chain-new', 0, ['to-b', 'to-c', 'to-d']).payload, 20)
        self.assertEqual(follow(self.warehouse, 'chain-old', 0, ['to-b', 'to-c', 'to-d']).payload, 10)

    def test_n4_binding_labels_include_revision_payload_name_and_target(self):
        first = ReleasePackage('base', ('A', 'C', 'D'), (
            PackageRecord('A', '1', 0, (('left', 'C'), ('right', 'D'))),
            PackageRecord('C', '1', 10), PackageRecord('D', '1', 10),
        ))
        root, calibration, other = first.records
        original = dict(mount(self.warehouse, first))
        cases = [
            ('revision', root, replace(calibration, revision='2')),
            ('payload', root, replace(calibration, payload=11)),
            ('edge-name', replace(root, references=(('other', 'C'), ('right', 'D'))), calibration),
            ('edge-target', replace(root, references=(('left', 'D'), ('right', 'C'))), calibration),
        ]
        for release_id, changed_root, changed_calibration in cases:
            with self.subTest(release_id=release_id):
                changed = replace(first, release_id=release_id, records=(changed_root, changed_calibration, other))
                landed = dict(mount(self.warehouse, changed))
                self.assertNotEqual(landed['A'], original['A'])
                self.assertEqual(landed['D'], original['D'])
                self.assertNotEqual(landed['C'], landed['D'])
                if release_id in ('revision', 'payload'):
                    self.assertNotEqual(landed['C'], original['C'])
                else:
                    self.assertEqual(landed['C'], original['C'])
        self.assertEqual(follow(self.warehouse, 'edge-target', 0, ['left']).key, 'D')
