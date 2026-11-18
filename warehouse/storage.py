import sqlite3
from collections.abc import Callable
from contextlib import contextmanager

from .instances import initialize_instances
from .publications import initialize_publications
from .references import initialize_references


class MountError(RuntimeError):
    pass


@contextmanager
def warehouse_write_transaction(
    connection: sqlite3.Connection, *, before_commit: Callable[[], None] | None = None,
):
    connection.execute('BEGIN IMMEDIATE')
    initial_changes = connection.total_changes
    try:
        yield
        if before_commit is not None and connection.total_changes != initial_changes:
            try:
                before_commit()
            except Exception as error:
                raise MountError('mount interrupted before commit') from error
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def initialize_warehouse(connection: sqlite3.Connection) -> None:
    connection.execute('PRAGMA foreign_keys = ON')
    with warehouse_write_transaction(connection):
        initialize_instances(connection)
        initialize_references(connection)
        initialize_publications(connection)


def open_warehouse(path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, isolation_level=None)
    try:
        initialize_warehouse(connection)
    except BaseException:
        connection.close()
        raise
    return connection
