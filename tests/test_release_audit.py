import json
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from audit.entrypoints import entries
from audit.inventory import inventory
from audit.traversal import follow
from catalog.revision_queries import get_revision
from catalog.revisions import put
from catalog.storage import open_source
from demo import load_sample, seed_source
from exchange.encoding import encode_package
from exchange.packages import pack
from releases.catalog import freeze
from warehouse.imports import mount
from warehouse.storage import open_warehouse


class ReleaseAuditTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.source_path = self.root / 'source.sqlite'
        self.warehouse_path = self.root / 'warehouse.sqlite'
        self.sample, self.expected = load_sample()

    def export_sample(self):
        with closing(open_source(self.source_path)) as source:
            seed_source(source, self.sample)
            return {release_id: encode_package(pack(source, release_id)) for release_id in ('R1', 'R2')}

    def mount_sample(self, warehouse):
        return {release_id: mount(warehouse, text) for release_id, text in self.export_sample().items()}

    def test_n7_binding_drift(self):
        packages = self.export_sample()
        with closing(open_warehouse(self.warehouse_path)) as warehouse:
            receipts = {release_id: mount(warehouse, text) for release_id, text in packages.items()}
            ordered = {release_id: entries(warehouse, release_id) for release_id in packages}
            targets = {
                release_id: follow(warehouse, release_id, 0, self.sample['calibration_path']) for release_id in packages
            }
            reports = {release_id: inventory(warehouse, release_id) for release_id in packages}
        ids = {release_id: {row.key: row.instance_id for row in report.rows} for release_id, report in reports.items()}
        common_keys = ids['R1'].keys() & ids['R2'].keys()
        shared = sorted(key for key in common_keys if ids['R1'][key] == ids['R2'][key])
        separate = sorted(common_keys - set(shared))
        actual = {
            'values': {release_id: target.payload for release_id, target in targets.items()},
            'entry_keys': {release_id: [key for key, _ in result] for release_id, result in ordered.items()},
            'counts': {release_id: report.count for release_id, report in reports.items()},
            'rows': {
                release_id: [[row.key, row.revision, row.payload] for row in report.rows]
                for release_id, report in reports.items()
            },
            'shared': shared,
            'separate': separate,
            'path_matches_inventory': all(target.instance_id == ids[release_id].get('C') for release_id, target in targets.items()),
        }
        expected = {
            'values': self.expected['values'],
            'entry_keys': {'R1': ['A', 'D'], 'R2': ['A', 'D']},
            'counts': {'R1': 4, 'R2': 4},
            'rows': self.expected['rows'],
            'shared': self.expected['shared'],
            'separate': self.expected['separate'],
            'path_matches_inventory': True,
        }
        self.assertEqual(actual, expected, f'WAREHOUSE_RELEASE_BINDING_DRIFT actual={actual!r} expected={expected!r} ids={ids!r}')
        self.assertEqual(receipts, ordered)

    def test_n7_reverse_install_and_permuted_replay_keep_ids_after_reopen(self):
        packages = self.export_sample()
        with closing(open_warehouse(self.warehouse_path)) as warehouse:
            second = mount(warehouse, packages['R2'])
            first = mount(warehouse, packages['R1'])
            reordered = json.loads(packages['R2'])
            reordered['records'].reverse()
            for record in reordered['records']:
                record['references'].reverse()
            self.assertEqual(mount(warehouse, json.dumps(reordered)), second)
            before = {release_id: inventory(warehouse, release_id) for release_id in packages}
        with closing(open_warehouse(self.warehouse_path)) as warehouse:
            self.assertEqual(entries(warehouse, 'R1'), first)
            self.assertEqual(entries(warehouse, 'R2'), second)
            self.assertEqual(first[1], second[1])
            self.assertNotEqual(first[0][1], second[0][1])
            self.assertEqual(follow(warehouse, 'R1', 0, ['辅助']).key, 'B')
            self.assertNotEqual(follow(warehouse, 'R1', 0, ['辅助']).instance_id, follow(warehouse, 'R2', 0, ['辅助']).instance_id)
            self.assertEqual(follow(warehouse, 'R2', 0, ['辅助', '校准']).payload, 20)
            self.assertEqual(follow(warehouse, 'R1', 0, ['辅助', '校准']).payload, 10)
            self.assertEqual({release_id: inventory(warehouse, release_id) for release_id in packages}, before)

    def test_n7_named_edges_and_finite_return_through_cycle(self):
        with closing(open_warehouse(self.warehouse_path)) as warehouse:
            self.mount_sample(warehouse)
            for release_id, expected in self.expected['values'].items():
                with self.subTest(release_id=release_id):
                    start = follow(warehouse, release_id, 0, ())
                    self.assertEqual((start.key, start.payload), ('A', 0))
                    self.assertEqual(start.instance_id, entries(warehouse, release_id)[0][1])
                    self.assertEqual(follow(warehouse, release_id, 0, ['辅助', '回入口']), start)
                    direct = follow(warehouse, release_id, 0, ['辅助', '校准'])
                    around = follow(warehouse, release_id, 0, ['辅助', '回入口', '辅助', '校准'])
                    self.assertEqual(direct, around)
                    self.assertEqual((direct.key, direct.payload), ('C', expected))

    def test_n7_path_errors_are_specific(self):
        with closing(open_warehouse(self.warehouse_path)) as warehouse:
            self.mount_sample(warehouse)
            for invalid in (-1, 2, True, 0.0):
                with self.subTest(position=invalid):
                    with self.assertRaises(IndexError):
                        follow(warehouse, 'R1', invalid, ())
            with self.assertRaisesRegex(KeyError, 'missing-edge'):
                follow(warehouse, 'R1', 0, ['辅助', 'missing-edge'])
            with self.assertRaises(ValueError):
                follow(warehouse, 'R1', 0, '辅助')

    def test_n7_inventory_once_with_cycle_convergence_and_duplicate_entry(self):
        with closing(open_source(self.source_path)) as source:
            seed_source(source, self.sample)
            put(source, 'A', '2', 0, {'辅助': 'B', '直达': 'C'})
            freeze(source, 'joined', {'A': '2', 'B': '1', 'C': '2', 'D': '1'}, ['A', 'D', 'A'])
            package = pack(source, 'joined')
        with closing(open_warehouse(self.warehouse_path)) as warehouse:
            ordered = mount(warehouse, package)
            self.assertEqual(ordered[0], ordered[2])
            via_b = follow(warehouse, 'joined', 0, ['辅助', '校准'])
            direct = follow(warehouse, 'joined', 2, ['直达'])
            self.assertEqual(via_b, direct)
            report = inventory(warehouse, 'joined')
            self.assertEqual(report.count, 4)
            self.assertEqual([(row.key, row.payload) for row in report.rows], [('A', 0), ('B', -2), ('C', 20), ('D', 4)])
            self.assertEqual([row.instance_id for row in report.rows if row.key == 'C'], [direct.instance_id])

    def test_n8_source_correction_and_offline_reopen_keep_fixed_reads(self):
        with closing(open_warehouse(self.warehouse_path)) as warehouse:
            ordered = self.mount_sample(warehouse)
            before = {release_id: inventory(warehouse, release_id) for release_id in ordered}
            terminal = {release_id: follow(warehouse, release_id, 0, ['辅助', '校准']) for release_id in ordered}
        with closing(open_source(self.source_path)) as source:
            put(source, 'C', '3', 30)
            self.assertEqual(get_revision(source, 'C', '3').payload, 30)
        with closing(open_warehouse(self.warehouse_path)) as reopened:
            for release_id, payload in [('R1', 10), ('R2', 20)]:
                with self.subTest(release_id=release_id):
                    self.assertEqual(entries(reopened, release_id), ordered[release_id])
                    self.assertEqual(inventory(reopened, release_id), before[release_id])
                    result = follow(reopened, release_id, 0, ['辅助', '校准'])
                    self.assertEqual(result, terminal[release_id])
                    self.assertEqual(result.payload, payload)

    def test_n8_reinitialize_and_example_replay_keep_user_publication(self):
        packages = self.export_sample()
        with closing(open_source(self.source_path)) as source:
            put(source, 'user', 'local', -13)
            freeze(source, 'user', {'user': 'local'}, ['user'])
            user_package = pack(source, 'user')
        with closing(open_warehouse(self.warehouse_path)) as warehouse:
            original = {release_id: mount(warehouse, text) for release_id, text in packages.items()}
            user_entries = mount(warehouse, user_package)
            user_report = inventory(warehouse, 'user')
        with closing(open_warehouse(self.warehouse_path)) as reopened:
            replayed = self.mount_sample(reopened)
            self.assertEqual(replayed, original)
            self.assertEqual(entries(reopened, 'user'), user_entries)
            self.assertEqual(inventory(reopened, 'user'), user_report)
            self.assertEqual(follow(reopened, 'user', 0, ()).payload, -13)
            self.assertEqual(reopened.execute('SELECT COUNT(*) FROM instances').fetchone(), (8,))

    def test_n8_unknown_release_errors_after_reopen(self):
        with closing(open_warehouse(self.warehouse_path)) as warehouse:
            original = self.mount_sample(warehouse)
        with closing(open_warehouse(self.warehouse_path)) as reopened:
            for read in (entries, inventory):
                with self.assertRaises(KeyError):
                    read(reopened, 'unknown')
            with self.assertRaises(KeyError):
                follow(reopened, 'unknown', 0, ())
            self.assertEqual(entries(reopened, 'R1'), original['R1'])
