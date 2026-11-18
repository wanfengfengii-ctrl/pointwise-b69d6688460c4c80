import sqlite3
from collections.abc import Callable

from exchange.encoding import decode_package, encode_validated_package
from exchange.graph import ReleasePackage
from exchange.validation import ValidatedPackage, validate_package

from .equivalence import find_reusable_instances
from .instances import allocate_instance
from .publications import MountReceipt, get_mount_receipt, save_mount_receipt
from .references import write_references
from .storage import MountError, warehouse_write_transaction


def _prepare_instances(connection: sqlite3.Connection, graph: ValidatedPackage) -> dict[str, int]:
    bindings = find_reusable_instances(connection, graph)
    allocated = []
    for key in sorted(graph.records):
        if key in bindings:
            continue
        record = graph.records[key]
        bindings[key] = allocate_instance(connection, key, record.revision, record.payload)
        allocated.append(key)
    for key in allocated:
        targets = {name: bindings[target] for name, target in graph.edges[key].items()}
        write_references(connection, bindings[key], targets)
    return bindings


def mount(
    connection: sqlite3.Connection,
    package: ReleasePackage | str | bytes,
    before_commit: Callable[[], None] | None = None,
) -> tuple[tuple[str, int], ...]:
    if isinstance(package, (str, bytes)):
        package = decode_package(package)
    validated = validate_package(package)
    release_id = validated.package.release_id
    package_content = encode_validated_package(validated)
    try:
        with warehouse_write_transaction(connection, before_commit=before_commit):
            existing = get_mount_receipt(connection, release_id)
            if existing is not None:
                if existing.package_content != package_content:
                    raise ValueError(f'conflicting mounted release {release_id!r}')
                return existing.entries
            bindings = _prepare_instances(connection, validated)
            ordered = tuple((key, bindings[key]) for key in validated.package.entries)
            save_mount_receipt(connection, MountReceipt(release_id, package_content, ordered))
    except sqlite3.Error as error:
        raise MountError(f'could not mount release {release_id!r}') from error
    return ordered
