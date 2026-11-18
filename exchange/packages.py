import sqlite3
from collections.abc import Mapping

from catalog.records import SourceRevision
from releases.catalog import get_frozen_release
from releases.receipts import FrozenRelease
from releases.selection import resolve_selection

from .closure import build_closure
from .graph import ReleasePackage


def _checkout_records(
    connection: sqlite3.Connection, receipt: FrozenRelease,
) -> Mapping[str, SourceRevision]:
    selected = resolve_selection(connection, receipt.selection)
    entries = receipt.selection.entries
    if not entries:
        return selected

    # Releases with the same entry bindings can share a qualified checkout.
    entry_scope = set(entries)
    entry_scope.update(target for key in entries for _, target in selected[key].references)
    entry_revisions = {key: selected[key].revision for key in entry_scope}
    earlier = connection.execute(
        "SELECT release_id FROM frozen_releases "
        "WHERE rowid < (SELECT rowid FROM frozen_releases WHERE release_id = ?) ORDER BY rowid",
        (receipt.release_id,),
    )
    for (release_id,) in earlier:
        prior = get_frozen_release(connection, release_id).selection
        if prior.entries != entries:
            continue
        prior_revisions = dict(prior.revisions)
        if all(prior_revisions.get(key) == revision for key, revision in entry_revisions.items()):
            return resolve_selection(connection, prior)
    return selected


def pack(connection: sqlite3.Connection, release_id: str) -> ReleasePackage:
    receipt = get_frozen_release(connection, release_id)
    selected = _checkout_records(connection, receipt)
    entries = receipt.selection.entries
    return ReleasePackage(receipt.release_id, entries, build_closure(selected, entries))
