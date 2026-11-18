import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass

from catalog.records import SourceRevision
from catalog.revision_queries import get_revision
from catalog.validation import identifier_sequence, require_identifier


@dataclass(frozen=True, slots=True)
class ReleaseSelection:
    revisions: tuple[tuple[str, str], ...]
    entries: tuple[str, ...]


def parse_selection(selection: object, entries: object) -> ReleaseSelection:
    if not isinstance(selection, Mapping):
        raise ValueError('selection must map logical keys to revisions')
    revisions = tuple(sorted(
        (require_identifier(key, 'selected key'), require_identifier(revision, 'selected revision'))
        for key, revision in selection.items()
    ))
    return ReleaseSelection(revisions, identifier_sequence(entries, 'entry key'))


def resolve_selection(connection: sqlite3.Connection, selection: ReleaseSelection) -> dict[str, SourceRevision]:
    records = {}
    for key, revision in selection.revisions:
        record = get_revision(connection, key, revision)
        if record is None:
            raise KeyError(f'unknown source revision {(key, revision)!r}')
        records[key] = record
    return records


def walk_selected_records(
    records: Mapping[str, SourceRevision], entries: tuple[str, ...],
) -> tuple[SourceRevision, ...]:
    reached: dict[str, SourceRevision] = {}
    pending = list(reversed(entries))
    while pending:
        key = pending.pop()
        if key in reached:
            continue
        if key not in records:
            raise ValueError(f'entry {key!r} is missing from the selection')
        record = records[key]
        reached[key] = record
        for name, target in reversed(record.references):
            if target not in records:
                raise ValueError(f'{key!r} reference {name!r} targets unselected key {target!r}')
            if target not in reached:
                pending.append(target)
    return tuple(reached.values())
