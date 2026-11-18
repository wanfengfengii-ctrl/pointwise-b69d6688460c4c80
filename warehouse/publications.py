import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MountReceipt:
    release_id: str
    package_content: str
    entries: tuple[tuple[str, int], ...]


def initialize_publications(connection: sqlite3.Connection) -> None:
    connection.execute('''
        CREATE TABLE IF NOT EXISTS mounted_releases (
            release_id TEXT PRIMARY KEY NOT NULL,
            package_content TEXT NOT NULL
        )
    ''')
    connection.execute('''
        CREATE TABLE IF NOT EXISTS mounted_entries (
            release_id TEXT NOT NULL REFERENCES mounted_releases (release_id),
            position INTEGER NOT NULL CHECK (position >= 0),
            logical_key TEXT NOT NULL,
            instance_id INTEGER NOT NULL,
            PRIMARY KEY (release_id, position),
            FOREIGN KEY (instance_id, logical_key) REFERENCES instances (instance_id, logical_key)
        )
    ''')


def get_mount_receipt(connection: sqlite3.Connection, release_id: str) -> MountReceipt | None:
    row = connection.execute(
        'SELECT package_content FROM mounted_releases WHERE release_id = ?', (release_id,),
    ).fetchone()
    if row is None:
        return None
    entries = tuple(connection.execute(
        '''SELECT logical_key, instance_id FROM mounted_entries
           WHERE release_id = ? ORDER BY position''',
        (release_id,),
    ))
    return MountReceipt(release_id, row[0], entries)


def save_mount_receipt(connection: sqlite3.Connection, receipt: MountReceipt) -> None:
    connection.execute(
        'INSERT INTO mounted_releases (release_id, package_content) VALUES (?, ?)',
        (receipt.release_id, receipt.package_content),
    )
    connection.executemany(
        '''INSERT INTO mounted_entries (release_id, position, logical_key, instance_id)
           VALUES (?, ?, ?, ?)''',
        ((receipt.release_id, position, key, instance_id)
         for position, (key, instance_id) in enumerate(receipt.entries)),
    )
