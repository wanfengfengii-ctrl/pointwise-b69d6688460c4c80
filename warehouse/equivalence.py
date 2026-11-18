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
    # Two roots share an instance only when their whole reachable graphs agree on
    # logical keys, revisions, payloads, and named edges. Walk both graphs in
    # lockstep from the roots; the pairing is deterministic because edge names
    # are unique per record. The visited mapping terminates cycles and rejects
    # convergent shapes that would pair one package key with two instances.
    paired = {root_key: root_instance}
    pending = [root_key]
    while pending:
        key = pending.pop()
        instance_id = paired[key]
        record = graph.records[key]
        instance = read_instance(connection, instance_id)
        if _label(record) != _label(instance):
            return False
        incoming = graph.edges[key]
        stored = read_references(connection, instance_id)
        if incoming.keys() != stored.keys():
            return False
        for name, target in incoming.items():
            target_instance = stored[name]
            known = paired.get(target)
            if known is None:
                paired[target] = target_instance
                pending.append(target)
            elif known != target_instance:
                return False
    return True


def find_reusable_instances(connection: sqlite3.Connection, graph: ValidatedPackage) -> dict[str, int]:
    reusable = {}
    for key in sorted(graph.records):
        record = graph.records[key]
        for candidate in find_candidates(connection, record.key, record.revision, record.payload):
            if bindings_equal(connection, graph, key, candidate):
                reusable[key] = candidate
                break
    return reusable
