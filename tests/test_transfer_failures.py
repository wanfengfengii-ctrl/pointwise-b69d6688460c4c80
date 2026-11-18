import json
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from audit.entrypoints import entries
from audit.traversal import follow
from catalog.revisions import put
from catalog.storage import open_source
from demo import load_sample, seed_source
from exchange.encoding import encode_package
from exchange.graph import PackageRecord
from exchange.packages import pack
from releases.catalog import freeze
from warehouse.imports import mount
from warehouse.storage import MountError, open_warehouse


def warehouse_snapshot(connection):
    return (
        tuple(connection.execute('SELECT * FROM instances ORDER BY instance_id')),
        tuple(connection.execute('SELECT * FROM instance_references ORDER BY source_id, name')),
        tuple(connection.execute('SELECT * FROM mounted_releases ORDER BY release_id')),
        tuple(connection.execute('SELECT * FROM mounted_entries ORDER BY release_id, position')),
    )


class TransferFailureTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.path = self.root / 'warehouse.sqlite'
        self.warehouse = self.enterContext(closing(open_warehouse(self.path)))
        with closing(open_source(self.root / 'source.sqlite')) as source:
            put(source, 'A', '1', 0, {'cal': 'C'})
            put(source, 'C', '1', 10)
            put(source, 'C', '2', 20)
            freeze(source, 'old', {'A': '1', 'C': '1'}, ['A'])
            freeze(source, 'new', {'A': '1', 'C': '2'}, ['A'])
            self.old = pack(source, 'old')
            self.new = pack(source, 'new')

    def assert_rejected(self, release_id, package, message):
        before = warehouse_snapshot(self.warehouse)
        with self.assertRaisesRegex(ValueError, message):
            mount(self.warehouse, package)
        with self.assertRaises(KeyError):
            entries(self.warehouse, release_id)
        self.assertEqual(warehouse_snapshot(self.warehouse), before)
        self.assertFalse(self.warehouse.in_transaction)

    def test_n5_missing_target_rejects_package(self):
        self.assert_rejected('new', replace(self.new, records=self.new.records[:1]), 'missing record')
        mount(self.warehouse, self.new)
        self.assertEqual(follow(self.warehouse, 'new', 0, ['cal']).payload, 20)

    def test_n5_duplicate_key_survives_decoding_until_rejection(self):
        wire = json.loads(encode_package(self.new))
        wire['records'].append(wire['records'][1].copy())
        self.assert_rejected('new', json.dumps(wire), 'duplicate package record')
        mount(self.warehouse, self.new)
        self.assertEqual(follow(self.warehouse, 'new', 0, ['cal']).payload, 20)

    def test_n5_duplicate_edge_survives_decoding_until_rejection(self):
        wire = json.loads(encode_package(self.new))
        wire['records'][0]['references'].append(['cal', 'C'])
        self.assert_rejected('new', json.dumps(wire), 'duplicate reference name')

    def test_n5_unreachable_record_and_missing_entry(self):
        with_orphan = replace(self.new, records=self.new.records + (PackageRecord('D', '1', 4),))
        self.assert_rejected('new', with_orphan, 'unreachable package records')
        self.assert_rejected('new', replace(self.new, entries=('D',)), 'missing package entry')

    def test_n5_rejects_invalid_payload_and_repeated_json_field(self):
        for invalid in (None, False, 10.0, '20'):
            with self.subTest(payload=invalid):
                wire = json.loads(encode_package(self.new))
                wire['records'][1]['payload'] = invalid
                self.assert_rejected('new', json.dumps(wire), 'payload must be an integer')
        repeated = encode_package(self.new).replace('"payload":20', '"payload":20,"payload":20')
        self.assert_rejected('new', repeated, 'duplicate JSON field')

    def test_n5_cyclic_second_edition_rejects_removed_or_duplicate_calibration(self):
        sample, _ = load_sample()
        with closing(open_source(self.root / 'source.sqlite')) as source:
            seed_source(source, sample)
            first, second = pack(source, 'R1'), pack(source, 'R2')
        mount(self.warehouse, first)
        calibration = next(record for record in second.records if record.key == 'C')
        without_c = replace(second, records=tuple(record for record in second.records if record.key != 'C'))
        self.assert_rejected('R2', without_c, 'missing record')
        self.assert_rejected('R2', replace(second, records=second.records + (calibration,)), 'duplicate package record')
        self.assertEqual(follow(self.warehouse, 'R1', 0, ['辅助', '校准']).payload, 10)
        mount(self.warehouse, second)
        self.assertEqual(follow(self.warehouse, 'R2', 0, ['辅助', '校准']).payload, 20)

    def test_n6_precommit_failure_rolls_back_graph_and_receipt(self):
        old_entries = mount(self.warehouse, self.old)
        before = warehouse_snapshot(self.warehouse)
        prepared = []

        def fail_with_graph_prepared():
            prepared.append((entries(self.warehouse, 'new'), follow(self.warehouse, 'new', 0, ['cal']).payload))
            raise RuntimeError('simulated commit precondition failure')

        with self.assertRaises(MountError) as failure:
            mount(self.warehouse, self.new, before_commit=fail_with_graph_prepared)
        self.assertIsInstance(failure.exception.__cause__, RuntimeError)
        self.assertEqual(len(prepared), 1)
        self.assertEqual(prepared[0][1], 20)
        self.assertNotEqual(prepared[0][0], old_entries)
        self.assertEqual(warehouse_snapshot(self.warehouse), before)
        with self.assertRaises(KeyError):
            entries(self.warehouse, 'new')
        self.assertEqual(follow(self.warehouse, 'old', 0, ['cal']).payload, 10)
        self.warehouse.close()
        with closing(open_warehouse(self.path)) as reopened:
            self.assertEqual(warehouse_snapshot(reopened), before)
            self.assertEqual(entries(reopened, 'old'), old_entries)
            self.assertEqual(follow(reopened, 'old', 0, ['cal']).payload, 10)
            new_entries = mount(reopened, self.new)
            self.assertNotEqual(new_entries, old_entries)
            self.assertEqual(follow(reopened, 'new', 0, ['cal']).payload, 20)
            self.assertEqual(entries(reopened, 'old'), old_entries)

    def test_n6_other_connection_sees_only_committed_graph_and_can_retry(self):
        old_entries = mount(self.warehouse, self.old)
        replay = replace(self.new, release_id='new-copy')
        with closing(open_warehouse(self.path)) as observer:
            observer.execute('PRAGMA busy_timeout = 0')
            checks = []

            def check_before_commit():
                checks.append(entries(observer, 'old'))
                with self.assertRaises(KeyError):
                    entries(observer, 'new')
                with self.assertRaises(MountError):
                    mount(observer, replay)

            first = mount(self.warehouse, self.new, before_commit=check_before_commit)
            self.assertEqual(checks, [old_entries])
            self.assertEqual(mount(observer, replay), first)
            self.assertEqual(follow(observer, 'new-copy', 0, ['cal']).payload, 20)
            self.assertEqual(observer.execute('SELECT COUNT(*) FROM instances').fetchone(), (4,))
