import json
import sqlite3

from .records import SourceRevision, revision_content
from .revision_queries import get_revision
from .storage import source_write_transaction
from .validation import validate_revision


def put(
    connection: sqlite3.Connection,
    key: str,
    revision: str,
    payload: int,
    references: object = (),
) -> SourceRevision:
    record = validate_revision(key, revision, payload, references)
    with source_write_transaction(connection):
        existing = get_revision(connection, record.key, record.revision)
        if existing is not None:
            if revision_content(existing) != revision_content(record):
                raise ValueError(f'conflicting source revision {(record.key, record.revision)!r}')
            return existing
        connection.execute(
            '''INSERT INTO source_revisions (logical_key, revision, payload_hex, references_json)
               VALUES (?, ?, ?, ?)''',
            (
                record.key,
                record.revision,
                hex(record.payload),
                json.dumps(record.references, ensure_ascii=False, separators=(',', ':')),
            ),
        )
    return record
