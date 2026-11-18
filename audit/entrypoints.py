import sqlite3

from catalog.validation import require_identifier
from warehouse.publications import get_mount_receipt


def entries(connection: sqlite3.Connection, release_id: str) -> tuple[tuple[str, int], ...]:
    release_id = require_identifier(release_id, 'release ID')
    receipt = get_mount_receipt(connection, release_id)
    if receipt is None:
        raise KeyError(f'unknown mounted release {release_id!r}')
    return receipt.entries
