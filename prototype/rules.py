"""Analysis rules that turn raw project/SLA/issue data into exceptions.

Only items that fail a rule below become an Exception. Healthy items are
dropped here and never reach the digest -- the digest only ever sees
exceptions, per the "don't report on what's fine" requirement.
"""

from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from .models import Issue, Project, SLA

# How many points of completion a project may trail its expected pace
# before it counts as "behind schedule" even though it isn't past its
# planned end date yet.
PACE_TOLERANCE_PCT = 10.0

# A blocker/unassigned issue must be open longer than this to be surfaced
# on age alone. High/critical priority and explicit blockers are always
# surfaced regardless of age.
STALE_ISSUE_THRESHOLD_DAYS = 3

HIGH_PRIORITIES = {"high", "critical"}


@dataclass
class Exception_:
    id: str  # stable key used to track this item across runs, e.g. "project:PRJ-3"
    category: str  # "behind_schedule" | "sla_breach" | "blocker"
    title: str
    owner: str
    description: str  # what it is / why it matters, one or two sentences
    fingerprint: str  # short string of the current state, used to detect changes run-to-run


def _expected_completion_pct(project: Project, today: date) -> float:
    total_days = (project.planned_end_date - project.start_date).days
    if total_days <= 0:
        return 100.0
    elapsed_days = (today - project.start_date).days
    return max(0.0, min(100.0, elapsed_days / total_days * 100))


def evaluate_project(project: Project, today: date) -> Optional[Exception_]:
    expected_pct = _expected_completion_pct(project, today)
    past_due = today > project.planned_end_date and project.completion_pct < 100
    behind_pace = project.completion_pct < expected_pct - PACE_TOLERANCE_PCT
    reported_exception = project.reported_status in ("at_risk", "behind_schedule")

    if not (past_due or behind_pace or reported_exception):
        return None

    if past_due:
        days_late = (today - project.planned_end_date).days
        description = (
            f"{days_late} day(s) past its planned end date at {project.completion_pct:.0f}% complete."
        )
        computed_state = "behind_schedule"
    elif behind_pace:
        description = (
            f"At {project.completion_pct:.0f}% complete vs an expected ~{expected_pct:.0f}% "
            f"for this point in the timeline."
        )
        computed_state = "at_risk_pace"
    else:
        description = f"Reported as {project.reported_status.replace('_', ' ')} by the project owner."
        computed_state = "reported_only"

    fingerprint = f"{computed_state}|reported={project.reported_status}|{project.completion_pct:.0f}%"

    return Exception_(
        id=f"project:{project.key}",
        category="behind_schedule",
        title=f"{project.name} ({project.key})",
        owner=project.owner,
        description=description,
        fingerprint=fingerprint,
    )


def evaluate_sla(sla: SLA, today: date) -> Optional[Exception_]:
    if sla.direction == "max":
        breached = sla.current_value > sla.target
    elif sla.direction == "min":
        breached = sla.current_value < sla.target
    else:
        raise ValueError(f"Unknown SLA direction: {sla.direction!r}")

    if not breached:
        return None

    description = f"Currently {sla.current_value:g} {sla.unit} against a target of {sla.target:g} {sla.unit}."

    return Exception_(
        id=f"sla:{sla.name}",
        category="sla_breach",
        title=sla.name,
        owner=sla.owner,
        description=description,
        fingerprint=f"{sla.current_value:g}{sla.unit}/target={sla.target:g}{sla.unit}",
    )


def evaluate_issue(issue: Issue, today: date) -> Optional[Exception_]:
    age_days = (today - issue.created_date).days
    is_stale_unassigned = issue.assignee is None and age_days > STALE_ISSUE_THRESHOLD_DAYS

    worth_surfacing = (
        issue.is_blocking
        or issue.is_overdue
        or issue.priority in HIGH_PRIORITIES
        or is_stale_unassigned
    )
    if not worth_surfacing:
        return None

    reasons = []
    if issue.is_blocking:
        reasons.append("blocking")
    if issue.is_overdue:
        reasons.append("overdue")
    if issue.priority in HIGH_PRIORITIES:
        reasons.append(f"{issue.priority} priority")
    if is_stale_unassigned:
        reasons.append(f"unassigned {age_days}d")

    owner = issue.assignee or "Unassigned"
    description = f"{issue.title} ({', '.join(reasons)}, {issue.project_key})."

    return Exception_(
        id=f"issue:{issue.key}",
        category="blocker",
        title=f"{issue.key}",
        owner=owner,
        description=description,
        fingerprint="|".join(sorted(reasons)) + f"|assignee={issue.assignee}",
    )


def analyze(
    projects: List[Project],
    slas: List[SLA],
    issues: List[Issue],
    today: date = None,
) -> List[Exception_]:
    today = today or date.today()
    exceptions: List[Exception_] = []

    for project in projects:
        exc = evaluate_project(project, today)
        if exc:
            exceptions.append(exc)

    for sla in slas:
        exc = evaluate_sla(sla, today)
        if exc:
            exceptions.append(exc)

    for issue in issues:
        exc = evaluate_issue(issue, today)
        if exc:
            exceptions.append(exc)

    return exceptions
