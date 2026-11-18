import sqlite3
from collections.abc import Mapping, Sequence

from catalog.storage import source_write_transaction
from catalog.validation import require_identifier

from .qualification import qualify_release
from .receipts import FrozenRelease, same_release_content
from .selection import ReleaseSelection, parse_selection


def initialize_releases(connection: sqlite3.Connection) -> None:
    connection.execute('''
        CREATE TABLE IF NOT EXISTS frozen_releases (
            release_id TEXT PRIMARY KEY NOT NULL
        )
    ''')
    connection.execute('''
        CREATE TABLE IF NOT EXISTS release_selections (
            release_id TEXT NOT NULL REFERENCES frozen_releases (release_id),
            logical_key TEXT NOT NULL,
            revision TEXT NOT NULL,
            PRIMARY KEY (release_id, logical_key),
            FOREIGN KEY (logical_key, revision) REFERENCES source_revisions (logical_key, revision)
        )
    ''')
    connection.execute('''
        CREATE TABLE IF NOT EXISTS frozen_entries (
            release_id TEXT NOT NULL,
            position INTEGER NOT NULL CHECK (position >= 0),
            logical_key TEXT NOT NULL,
            PRIMARY KEY (release_id, position),
            FOREIGN KEY (release_id, logical_key) REFERENCES release_selections (release_id, logical_key)
        )
    ''')


def _read_receipt(connection: sqlite3.Connection, release_id: str) -> FrozenRelease | None:
    row = connection.execute(
        'SELECT release_id FROM frozen_releases WHERE release_id = ?', (release_id,),
    ).fetchone()
    if row is None:
        return None
    revisions = tuple(connection.execute(
        '''SELECT logical_key, revision FROM release_selections
           WHERE release_id = ? ORDER BY logical_key''',
        (release_id,),
    ))
    entries = tuple(key for (key,) in connection.execute(
        'SELECT logical_key FROM frozen_entries WHERE release_id = ? ORDER BY position',
        (release_id,),
    ))
    return FrozenRelease(release_id, ReleaseSelection(revisions, entries))


def get_frozen_release(connection: sqlite3.Connection, release_id: str) -> FrozenRelease:
    release_id = require_identifier(release_id, 'release ID')
    receipt = _read_receipt(connection, release_id)
    if receipt is None:
        raise KeyError(f'unknown frozen release {release_id!r}')
    return receipt


def freeze(
    connection: sqlite3.Connection,
    release_id: str,
    selection: Mapping[str, str],
    entries: Sequence[str],
) -> FrozenRelease:
    release_id = require_identifier(release_id, 'release ID')
    requested = FrozenRelease(release_id, parse_selection(selection, entries))
    with source_write_transaction(connection):
        existing = _read_receipt(connection, release_id)
        if existing is not None:
            if not same_release_content(existing, requested):
                raise ValueError(f'conflicting frozen release {release_id!r}')
            return existing
        qualify_release(connection, requested.selection)
        connection.execute('INSERT INTO frozen_releases (release_id) VALUES (?)', (release_id,))
        connection.executemany(
            'INSERT INTO release_selections (release_id, logical_key, revision) VALUES (?, ?, ?)',
            ((release_id, key, revision) for key, revision in requested.selection.revisions),
        )
        connection.executemany(
            'INSERT INTO frozen_entries (release_id, position, logical_key) VALUES (?, ?, ?)',
            ((release_id, position, key) for position, key in enumerate(requested.selection.entries)),
        )
    return requested
