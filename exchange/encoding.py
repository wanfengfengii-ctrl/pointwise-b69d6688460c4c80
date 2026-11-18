import json

from .graph import PackageRecord, ReleasePackage
from .validation import ValidatedPackage, validate_package


def _decimal_text(value: int) -> str:
    try:
        return str(value)
    except ValueError:
        # Preserve exact JSON integers even when Python limits decimal conversions.
        magnitude = abs(value)
        chunks = []
        while magnitude >= 10**9:
            magnitude, remainder = divmod(magnitude, 10**9)
            chunks.append(f'{remainder:09d}')
        sign = '-' if value < 0 else ''
        return sign + str(magnitude) + ''.join(reversed(chunks))


def _read_decimal(text: str) -> int:
    try:
        return int(text)
    except ValueError:
        # The JSON lexer has already checked the integer syntax.
        negative = text.startswith('-')
        digits = text[1:] if negative else text
        value = 0
        for start in range(0, len(digits), 9):
            chunk = digits[start:start + 9]
            value = value * 10**len(chunk) + int(chunk)
        return -value if negative else value


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def _encode_record(record: PackageRecord) -> str:
    return (
        '{"key":' + _json(record.key)
        + ',"revision":' + _json(record.revision)
        + ',"payload":' + _decimal_text(record.payload)
        + ',"references":' + _json(record.references) + '}'
    )


def encode_validated_package(validated: ValidatedPackage) -> str:
    package = validated.package
    records = ','.join(_encode_record(validated.records[key]) for key in sorted(validated.records))
    return (
        '{"release_id":' + _json(package.release_id)
        + ',"entries":' + _json(package.entries)
        + ',"records":[' + records + ']}'
    )


def encode_package(package: ReleasePackage) -> str:
    return encode_validated_package(validate_package(package))


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON field {key!r}')
        result[key] = value
    return result


def _bad_constant(token: str):
    raise ValueError(f'invalid JSON number {token!r}')


def _require_fields(value: object, fields: set[str], name: str) -> None:
    if not isinstance(value, dict) or value.keys() != fields:
        raise ValueError(f'{name} must contain exactly {sorted(fields)!r}')


def _decode_record(value: object) -> PackageRecord:
    _require_fields(value, {'key', 'revision', 'payload', 'references'}, 'package record')
    references = value['references']
    if not isinstance(references, list):
        raise ValueError('record references must be an array')
    pairs = []
    for pair in references:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError('each reference must be an array with a name and target')
        pairs.append((pair[0], pair[1]))
    return PackageRecord(value['key'], value['revision'], value['payload'], tuple(pairs))


def decode_package(text: str | bytes) -> ReleasePackage:
    if isinstance(text, bytes):
        text = text.decode('utf-8')
    if not isinstance(text, str):
        raise ValueError('package JSON must be text or UTF-8 bytes')
    try:
        value = json.loads(
            text, object_pairs_hook=_unique_object, parse_int=_read_decimal, parse_constant=_bad_constant,
        )
    except RecursionError as error:
        raise ValueError('excessively nested package JSON') from error
    _require_fields(value, {'release_id', 'entries', 'records'}, 'package')
    if not isinstance(value['entries'], list) or not isinstance(value['records'], list):
        raise ValueError('package entries and records must be arrays')
    return ReleasePackage(
        value['release_id'], tuple(value['entries']), tuple(_decode_record(record) for record in value['records']),
    )
