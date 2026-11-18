import sqlite3
from collections.abc import Mapping


def initialize_references(connection: sqlite3.Connection) -> None:
    connection.execute('''
        CREATE TABLE IF NOT EXISTS instance_references (
            source_id INTEGER NOT NULL REFERENCES instances (instance_id),
            name TEXT NOT NULL,
            target_id INTEGER NOT NULL REFERENCES instances (instance_id),
            PRIMARY KEY (source_id, name)
        )
    ''')


def write_references(connection: sqlite3.Connection, instance_id: int, references: Mapping[str, int]) -> None:
    connection.executemany(
        'INSERT INTO instance_references (source_id, name, target_id) VALUES (?, ?, ?)',
        ((instance_id, name, target) for name, target in sorted(references.items())),
    )


def read_references(connection: sqlite3.Connection, instance_id: int) -> dict[str, int]:
    return dict(connection.execute(
        'SELECT name, target_id FROM instance_references WHERE source_id = ?', (instance_id,),
    ))
