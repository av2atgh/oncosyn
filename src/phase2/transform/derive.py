"""Post-load derivation: fill computed columns in the database.

Run after `load` (needs regimen_component + agent populated):
  * agent.is_targeted      <- drug_class in the targeted set (NULL if class unknown)
  * arm.combination_size   <- # anticancer agents per arm (excludes radiation/
                              surgery/steroid)
  * arm.regimen_class      <- targeted / cytotoxic / mixed / other, from the
                              anticancer agents' classes
"""
from __future__ import annotations

from .. import db

TARGETED_CLASSES = {
    "hormonal", "mAb", "kinase_inhibitor", "proteasome_inhibitor",
    "checkpoint_inhibitor", "car_t",
}
# recorded but not counted as anticancer agents for size/class
NON_ANTICANCER = {"radiation", "surgery", "steroid"}


def classify_regimen(drug_classes: list[str | None]) -> tuple[int, str]:
    """Return (combination_size, regimen_class) from an arm's agent classes."""
    anti = [c for c in drug_classes if c not in NON_ANTICANCER]
    size = len(anti)
    if size == 0:
        return 0, "other"
    has_targeted = any(c in TARGETED_CLASSES for c in anti)
    has_cytotoxic = any(c == "cytotoxic" for c in anti)
    if has_targeted and has_cytotoxic:
        return size, "mixed"
    if has_targeted:
        return size, "targeted"
    if has_cytotoxic:
        return size, "cytotoxic"
    return size, "other"          # unknown-class agents only


def run() -> None:
    with db.session() as conn:
        # agent.is_targeted: 1 targeted, 0 known non-targeted, NULL if class unknown
        conn.execute(
            "UPDATE agent SET is_targeted = CASE "
            "  WHEN drug_class IS NULL THEN NULL "
            "  WHEN drug_class IN (%s) THEN 1 ELSE 0 END"
            % ",".join("?" * len(TARGETED_CLASSES)),
            tuple(TARGETED_CLASSES),
        )

        # arm.combination_size + regimen_class from constituent agent classes.
        # INNER join so arms with no components simply don't appear here.
        by_arm: dict[str, list[str | None]] = {}
        for r in conn.execute(
            "SELECT rc.arm_id, ag.drug_class "
            "FROM regimen_component rc JOIN agent ag ON ag.agent_id = rc.agent_id"
        ):
            by_arm.setdefault(r["arm_id"], []).append(r["drug_class"])

        updates = [
            (*classify_regimen(by_arm.get(r["arm_id"], [])), r["arm_id"])
            for r in conn.execute("SELECT arm_id FROM arm")
        ]
        conn.executemany(
            "UPDATE arm SET combination_size = ?, regimen_class = ? WHERE arm_id = ?",
            updates,
        )
    print(f"[derive] is_targeted set; {len(updates)} arms classified")


if __name__ == "__main__":
    run()
