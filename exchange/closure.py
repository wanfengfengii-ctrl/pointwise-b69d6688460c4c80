from collections.abc import Mapping

from catalog.records import SourceRevision
from releases.selection import walk_selected_records

from .graph import PackageRecord


def build_closure(
    selected: Mapping[str, SourceRevision], entries: tuple[str, ...],
) -> tuple[PackageRecord, ...]:
    reached = walk_selected_records(selected, entries)
    return tuple(
        PackageRecord(record.key, record.revision, record.payload, record.references)
        for record in sorted(reached, key=lambda item: item.key)
    )
