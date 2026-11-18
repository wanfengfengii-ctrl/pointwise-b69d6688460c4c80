import sqlite3
from contextlib import contextmanager


def initialize_revisions(connection: sqlite3.Connection) -> None:
    connection.execute('''
        CREATE TABLE IF NOT EXISTS source_revisions (
            logical_key TEXT NOT NULL,
            revision TEXT NOT NULL,
            payload_hex TEXT NOT NULL,
            references_json TEXT NOT NULL,
            PRIMARY KEY (logical_key, revision)
        )
    ''')


@contextmanager
def source_write_transaction(connection: sqlite3.Connection):
    connection.execute('BEGIN IMMEDIATE')
    try:
        yield
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def open_source(path) -> sqlite3.Connection:
    from releases.catalog import initialize_releases

    connection = sqlite3.connect(path, isolation_level=None)
    try:
        connection.execute('PRAGMA foreign_keys = ON')
        with source_write_transaction(connection):
            initialize_revisions(connection)
            initialize_releases(connection)
    except BaseException:
        connection.close()
        raise
    return connection
