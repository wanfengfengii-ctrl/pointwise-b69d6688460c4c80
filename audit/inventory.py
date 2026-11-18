import sqlite3

from warehouse.instances import read_instance
from warehouse.references import read_references

from .entrypoints import entries
from .reconciliation import Reconciliation, build_reconciliation


def inventory(connection: sqlite3.Connection, release_id: str) -> Reconciliation:
    pending = [instance_id for _, instance_id in entries(connection, release_id)]
    reached = {}
    while pending:
        instance_id = pending.pop()
        if instance_id in reached:
            continue
        reached[instance_id] = read_instance(connection, instance_id)
        pending.extend(read_references(connection, instance_id).values())
    return build_reconciliation(reached.values())
