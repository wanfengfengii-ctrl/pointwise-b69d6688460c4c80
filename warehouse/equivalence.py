import sqlite3

from exchange.graph import PackageRecord
from exchange.validation import ValidatedPackage

from .instances import BoundInstance, find_candidates, read_instance
from .references import read_references


def _label(record: PackageRecord | BoundInstance) -> tuple[str, str, int]:
    return record.key, record.revision, record.payload


def bindings_equal(
    connection: sqlite3.Connection,
    graph: ValidatedPackage,
    root_key: str,
    root_instance: int,
) -> bool:
    record = graph.records[root_key]
    instance = read_instance(connection, root_instance)
    if _label(record) != _label(instance):
        return False
    incoming = graph.edges[root_key]
    stored = read_references(connection, root_instance)
    if incoming.keys() != stored.keys():
        return False
    return all(
        _label(graph.records[target]) == _label(read_instance(connection, stored[name]))
        for name, target in incoming.items()
    )


def find_reusable_instances(connection: sqlite3.Connection, graph: ValidatedPackage) -> dict[str, int]:
    reusable = {}
    for key in sorted(graph.records):
        record = graph.records[key]
        for candidate in find_candidates(connection, record.key, record.revision, record.payload):
            if bindings_equal(connection, graph, key, candidate):
                reusable[key] = candidate
                break
    return reusable
