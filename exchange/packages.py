import sqlite3

from releases.catalog import get_frozen_release
from releases.selection import resolve_selection

from .closure import build_closure
from .graph import ReleasePackage


def pack(connection: sqlite3.Connection, release_id: str) -> ReleasePackage:
    receipt = get_frozen_release(connection, release_id)
    selected = resolve_selection(connection, receipt.selection)
    entries = receipt.selection.entries
    return ReleasePackage(receipt.release_id, entries, build_closure(selected, entries))
