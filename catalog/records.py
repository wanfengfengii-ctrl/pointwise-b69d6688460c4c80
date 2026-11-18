from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceRevision:
    key: str
    revision: str
    payload: int
    references: tuple[tuple[str, str], ...]


def revision_content(record: SourceRevision) -> tuple[int, tuple[tuple[str, str], ...]]:
    return record.payload, record.references
