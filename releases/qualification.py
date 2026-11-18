import sqlite3

from .selection import ReleaseSelection, resolve_selection, walk_selected_records


def qualify_release(connection: sqlite3.Connection, selection: ReleaseSelection) -> None:
    selected = resolve_selection(connection, selection)
    walk_selected_records(selected, selection.entries)
