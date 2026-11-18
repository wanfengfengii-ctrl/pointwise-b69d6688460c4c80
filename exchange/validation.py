from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from catalog.validation import (
    identifier_sequence,
    is_sequence,
    normalize_references,
    require_identifier,
    require_payload,
)

from .graph import PackageRecord, ReleasePackage, index_package_records, reachable_package_keys


@dataclass(frozen=True, slots=True)
class ValidatedPackage:
    package: ReleasePackage
    records: Mapping[str, PackageRecord]
    edges: Mapping[str, Mapping[str, str]]


def _validate_record(record: object) -> PackageRecord:
    if not isinstance(record, PackageRecord):
        raise ValueError('package records must be PackageRecord values')
    if not is_sequence(record.references):
        raise ValueError('package references must retain their pair sequence')
    return PackageRecord(
        require_identifier(record.key, 'record key'),
        require_identifier(record.revision, 'record revision'),
        require_payload(record.payload),
        normalize_references(record.references),
    )


def validate_package(package: ReleasePackage) -> ValidatedPackage:
    if not isinstance(package, ReleasePackage):
        raise ValueError('mount requires a ReleasePackage or package JSON')
    release_id = require_identifier(package.release_id, 'release ID')
    entries = identifier_sequence(package.entries, 'entry key')
    if not is_sequence(package.records):
        raise ValueError('package records must be an ordered sequence')
    records = tuple(_validate_record(record) for record in package.records)
    by_key = index_package_records(records)
    for entry in entries:
        if entry not in by_key:
            raise ValueError(f'missing package entry {entry!r}')
    for record in records:
        for name, target in record.references:
            if target not in by_key:
                raise ValueError(f'{record.key!r} reference {name!r} targets missing record {target!r}')
    reached = reachable_package_keys(by_key, entries)
    if reached != by_key.keys():
        raise ValueError(f'unreachable package records {sorted(by_key.keys() - reached)!r}')
    edges = {record.key: MappingProxyType(dict(record.references)) for record in records}
    return ValidatedPackage(
        ReleasePackage(release_id, entries, records), MappingProxyType(by_key), MappingProxyType(edges),
    )
