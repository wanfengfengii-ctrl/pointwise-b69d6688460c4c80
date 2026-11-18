from collections.abc import Iterable
from dataclasses import dataclass

from warehouse.instances import BoundInstance


@dataclass(frozen=True, slots=True)
class AuditRow:
    key: str
    instance_id: int
    revision: str
    payload: int


@dataclass(frozen=True, slots=True)
class Reconciliation:
    rows: tuple[AuditRow, ...]

    @property
    def count(self) -> int:
        return len(self.rows)


def build_reconciliation(instances: Iterable[BoundInstance]) -> Reconciliation:
    ordered = sorted(instances, key=lambda instance: (instance.key, instance.instance_id))
    return Reconciliation(tuple(
        AuditRow(instance.key, instance.instance_id, instance.revision, instance.payload)
        for instance in ordered
    ))
