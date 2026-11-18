import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BoundInstance:
    instance_id: int
    key: str
    revision: str
    payload: int


def initialize_instances(connection: sqlite3.Connection) -> None:
    connection.execute('''
        CREATE TABLE IF NOT EXISTS instances (
            instance_id INTEGER PRIMARY KEY,
            logical_key TEXT NOT NULL,
            revision TEXT NOT NULL,
            payload_hex TEXT NOT NULL,
            UNIQUE (instance_id, logical_key)
        )
    ''')
    connection.execute('''
        CREATE INDEX IF NOT EXISTS instances_by_label
        ON instances (logical_key, revision, payload_hex, instance_id)
    ''')


def read_instance(connection: sqlite3.Connection, instance_id: int) -> BoundInstance:
    row = connection.execute(
        'SELECT logical_key, revision, payload_hex FROM instances WHERE instance_id = ?', (instance_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f'unknown instance {instance_id}')
    key, revision, payload_hex = row
    return BoundInstance(instance_id, key, revision, int(payload_hex, 16))


def find_candidates(connection: sqlite3.Connection, key: str, revision: str, payload: int) -> tuple[int, ...]:
    cursor = connection.execute(
        '''SELECT instance_id FROM instances
           WHERE logical_key = ? AND revision = ? AND payload_hex = ? ORDER BY instance_id''',
        (key, revision, hex(payload)),
    )
    return tuple(instance_id for (instance_id,) in cursor)


def allocate_instance(connection: sqlite3.Connection, key: str, revision: str, payload: int) -> int:
    cursor = connection.execute(
        'INSERT INTO instances (logical_key, revision, payload_hex) VALUES (?, ?, ?)',
        (key, revision, hex(payload)),
    )
    return cursor.lastrowid
