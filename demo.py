import json
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from audit.entrypoints import entries
from audit.inventory import inventory
from audit.traversal import follow
from catalog.revisions import put
from catalog.storage import open_source
from exchange.encoding import encode_package
from exchange.packages import pack
from releases.catalog import freeze
from warehouse.imports import mount
from warehouse.storage import open_warehouse


SAMPLES = Path(__file__).resolve().parent / 'samples'


def load_sample() -> tuple[dict, dict]:
    sample = json.loads((SAMPLES / 'releases.json').read_text(encoding='utf-8'))
    expected = json.loads((SAMPLES / 'expected.json').read_text(encoding='utf-8'))
    return sample, expected


def seed_source(connection, sample: dict) -> None:
    for record in sample['records']:
        put(connection, **record)
    for release in sample['releases']:
        freeze(connection, **release)


def main() -> None:
    sample, expected = load_sample()
    release_ids = [release['release_id'] for release in sample['releases']]
    with TemporaryDirectory(prefix='calibration-demo-') as directory:
        root = Path(directory)
        with closing(open_source(root / 'source.sqlite')) as source:
            seed_source(source, sample)
            packages = {release_id: encode_package(pack(source, release_id)) for release_id in release_ids}
        with closing(open_warehouse(root / 'warehouse.sqlite')) as warehouse:
            for package in packages.values():
                mount(warehouse, package)
        with closing(open_warehouse(root / 'warehouse.sqlite')) as warehouse:
            ordered = {release_id: entries(warehouse, release_id) for release_id in release_ids}
            targets = {
                release_id: follow(warehouse, release_id, 0, sample['calibration_path'])
                for release_id in release_ids
            }
            reports = {release_id: inventory(warehouse, release_id) for release_id in release_ids}

    numbers = {
        release_id: {row.key: row.instance_id for row in report.rows}
        for release_id, report in reports.items()
    }
    first, second = release_ids
    shared = sorted(key for key in numbers[first] if numbers[first][key] == numbers[second].get(key))
    separate = sorted(set(numbers[first]) & set(numbers[second]) - set(shared))
    values = {release_id: target.payload for release_id, target in targets.items()}
    downstream = {
        'entries': {release_id: [key for key, _ in result] for release_id, result in ordered.items()},
        'rows': {
            release_id: [[row.key, row.revision, row.payload] for row in report.rows]
            for release_id, report in reports.items()
        },
        'shared': shared,
        'separate': separate,
    }
    downstream_expected = {
        'entries': {release_id: expected['entries'] for release_id in release_ids},
        'rows': expected['rows'],
        'shared': expected['shared'],
        'separate': expected['separate'],
    }
    if values != expected['values'] or downstream != downstream_expected:
        raise SystemExit(f'calibration demo mismatch actual={(values, downstream)!r} expected={(expected["values"], downstream_expected)!r}')
    if any(target.instance_id != numbers[release_id]['C'] for release_id, target in targets.items()):
        raise SystemExit('calibration path did not return the reconciled instance')

    for release_id in release_ids:
        print(f'{release_id} entries={ordered[release_id]!r} calibration={values[release_id]} instances={numbers[release_id]!r}')
    print(f'Shared D instance={numbers[first]["D"]}')
    evidence = {
        'case_id': 'n7',
        'input': sample,
        'expected': expected['values'],
        'actual': values,
        'downstream_expected': downstream_expected,
        'downstream_actual': downstream,
        'code_paths': ['exchange/packages.py', 'warehouse/imports.py', 'audit/traversal.py', 'audit/inventory.py'],
        'oracle': 'Follow the named sample edges by hand to the selected C revision. Compare four hand-listed rows and the unchanged D binding.',
    }
    print('POINTWISE_SCENARIO ' + json.dumps(evidence, ensure_ascii=False, separators=(',', ':')))


if __name__ == '__main__':
    main()
