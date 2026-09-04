"""Renders the analyzed exceptions into the plain-language digest."""

from datetime import date
from typing import Dict, List

from .rules import Exception_
from .state import change_note

CATEGORY_LABELS = {
    "behind_schedule": "Behind Schedule",
    "sla_breach": "SLA Breaches",
    "blocker": "Blockers",
}
CATEGORY_ORDER = ["behind_schedule", "sla_breach", "blocker"]


def _summary_line(by_category: Dict[str, List[Exception_]]) -> str:
    projects = by_category.get("behind_schedule", [])
    slas = by_category.get("sla_breach", [])
    blockers = by_category.get("blocker", [])

    if not projects and not slas and not blockers:
        return "All projects on track, no SLA breaches, no blockers requiring attention. No change from last digest."

    parts = []
    if projects:
        parts.append(f"{len(projects)} project(s) behind schedule")
    if slas:
        sla_names = ", ".join(exc.title for exc in slas[:2])
        suffix = f" on {sla_names}" + (", among others" if len(slas) > 2 else "")
        parts.append(f"{len(slas)} SLA breach(es){suffix}")
    if blockers:
        parts.append(f"{len(blockers)} blocker(s) needing attention")

    return ", ".join(parts) + "."


def render_digest(
    exceptions: List[Exception_],
    previous_fingerprints: Dict[str, str],
    run_date: date = None,
) -> str:
    run_date = run_date or date.today()

    by_category: Dict[str, List[Exception_]] = {}
    for exc in exceptions:
        by_category.setdefault(exc.category, []).append(exc)

    lines = [f"Project Status Digest — {run_date.isoformat()}", ""]
    lines.append(_summary_line(by_category))

    if not exceptions:
        return "\n".join(lines)

    for category in CATEGORY_ORDER:
        items = by_category.get(category)
        if not items:
            continue
        lines.append("")
        lines.append(f"{CATEGORY_LABELS[category]}:")
        for exc in items:
            note = change_note(exc, previous_fingerprints)
            lines.append(f"- {exc.title} — {exc.description} Owner: {exc.owner}. {note}")

    return "\n".join(lines)
