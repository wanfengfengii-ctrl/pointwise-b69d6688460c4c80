import sqlite3
from collections.abc import Sequence

from catalog.validation import identifier_sequence
from warehouse.instances import BoundInstance, read_instance
from warehouse.references import read_references

from .entrypoints import entries


def follow(
    connection: sqlite3.Connection, release_id: str, position: int, path: Sequence[str],
) -> BoundInstance:
    ordered = entries(connection, release_id)
    if type(position) is not int or not 0 <= position < len(ordered):
        raise IndexError(f'invalid entry position {position!r}')
    instance_id = ordered[position][1]
    for name in identifier_sequence(path, 'path edge name'):
        edges = read_references(connection, instance_id)
        if name not in edges:
            raise KeyError(f'instance {instance_id} has no reference {name!r}')
        instance_id = edges[name]
    return read_instance(connection, instance_id)
