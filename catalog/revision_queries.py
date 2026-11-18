import json
import sqlite3

from .records import SourceRevision


def get_revision(connection: sqlite3.Connection, key: str, revision: str) -> SourceRevision | None:
    row = connection.execute(
        '''SELECT payload_hex, references_json FROM source_revisions
           WHERE logical_key = ? AND revision = ?''',
        (key, revision),
    ).fetchone()
    if row is None:
        return None
    payload_hex, references_json = row
    references = tuple((name, target) for name, target in json.loads(references_json))
    return SourceRevision(key, revision, int(payload_hex, 16), references)
