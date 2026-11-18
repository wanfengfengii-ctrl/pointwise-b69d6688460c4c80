from dataclasses import dataclass

from .selection import ReleaseSelection


@dataclass(frozen=True, slots=True)
class FrozenRelease:
    release_id: str
    selection: ReleaseSelection


def same_release_content(left: FrozenRelease, right: FrozenRelease) -> bool:
    return (
        dict(left.selection.revisions) == dict(right.selection.revisions)
        and left.selection.entries == right.selection.entries
    )
