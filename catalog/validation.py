from collections.abc import Mapping, Sequence

from .records import SourceRevision


def require_identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f'{field} must be a nonempty string')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError as error:
        raise ValueError(f'{field} must be valid Unicode') from error
    return value


def require_payload(value: object) -> int:
    if type(value) is not int:
        raise ValueError('payload must be an integer')
    return value


def is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview))


def identifier_sequence(value: object, field: str) -> tuple[str, ...]:
    if not is_sequence(value):
        raise ValueError(f'{field} must be an ordered sequence')
    return tuple(require_identifier(item, field) for item in value)


def normalize_references(references: object) -> tuple[tuple[str, str], ...]:
    if isinstance(references, Mapping):
        references = tuple(references.items())
    if not is_sequence(references):
        raise ValueError('references must be a sequence of name/target pairs')
    by_name: dict[str, str] = {}
    for pair in references:
        if not is_sequence(pair) or len(pair) != 2:
            raise ValueError('each reference must have a name and target')
        name = require_identifier(pair[0], 'reference name')
        target = require_identifier(pair[1], 'reference target')
        if name in by_name:
            raise ValueError(f'duplicate reference name {name!r}')
        by_name[name] = target
    return tuple(sorted(by_name.items()))


def validate_revision(key: object, revision: object, payload: object, references: object = ()) -> SourceRevision:
    return SourceRevision(
        require_identifier(key, 'logical key'),
        require_identifier(revision, 'revision'),
        require_payload(payload),
        normalize_references(references),
    )
