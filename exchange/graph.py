from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PackageRecord:
    key: str
    revision: str
    payload: int
    references: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class ReleasePackage:
    release_id: str
    entries: tuple[str, ...]
    records: tuple[PackageRecord, ...]


def index_package_records(records: Iterable[PackageRecord]) -> dict[str, PackageRecord]:
    by_key = {}
    for record in records:
        if record.key in by_key:
            raise ValueError(f'duplicate package record {record.key!r}')
        by_key[record.key] = record
    return by_key


def reachable_package_keys(records: Mapping[str, PackageRecord], entries: tuple[str, ...]) -> set[str]:
    pending = list(entries)
    reached = set()
    while pending:
        key = pending.pop()
        if key in reached:
            continue
        reached.add(key)
        pending.extend(target for _, target in records[key].references)
    return reached
