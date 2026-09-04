"""Tunable configuration for the digest agent.

Everything a reviewer might want to argue about lives here rather than being
buried in the rules: thresholds, the stream split, and the KPI targets.

IMPORTANT: the source exports contain no KPI targets of any kind. Every value
in TARGETS below is a *proposed* threshold pending sign-off from the reporting
team, and the rendered brief labels them as such. Until they are agreed, the
trend charts reference a 12-month median computed from the data itself.
"""

from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT
STATE_DIR = PROJECT_ROOT / "state"

# --- run date -----------------------------------------------------------------
# Overridable so a run can be reproduced against a historical position.
TODAY: date | None = None


def today() -> date:
    return TODAY or date.today()


# --- source workbooks ---------------------------------------------------------
# Matched by filename fragment, not exact name: the service desk export arrived
# mid-assessment under a filename describing a different date, and the sheet
# inside it was renamed between two runs. Sheets are chosen by column signature
# (see sources.py), never by name.
WORKBOOKS = {
    "projects": "All Projects Report",
    "timesheet": "Sprints Data with Task",
    "tickets": "HRIS_Detailed_Report",
}

# Column signatures used to identify the right sheet inside a multi-sheet book.
SHEET_SIGNATURES = {
    "projects": {"PROJECT ID", "PROJECT NAME", "OWNER", "STATUS", "OPEN TASKS"},
    "timesheet": {"Item Id", "Log Date", "Log owner", "Project"},
    "tickets": {"RequestID", "Request Status", "Technician", "Created Time"},
}

# --- vocabulary ---------------------------------------------------------------
CLOSED_PROJECT_STATUSES = {"Completed", "Closed", "Cancelled"}
EVERGREEN_STATUSES = {"Live-Under Maintenance", "Ongoing"}
OPEN_TICKET_STATUSES = {"Open", "In-Process", "Waiting", "On Hold"}
DONE_ITEM_STATUSES = {"Done", "Closed"}
HIGH_TICKET_PRIORITIES = {"High", "Urgent"}

# The two delivery streams the data can actually separate. There is no board-type
# (Scrum/Kanban) field in the current export, so this is a Project Group split.
STREAMS = {
    "DevOps": "DevOps",
    "Ticket Mgmt (M&S)": "Ticket Management",
}

# --- thresholds ---------------------------------------------------------------
# How far a project may trail its expected pace before counting as behind.
PACE_TOLERANCE_PCT = 10.0
# A work-item cohort must be this old before its completion rate means anything;
# measured sooner, recent months look catastrophic purely from immaturity.
COHORT_MATURITY_DAYS = 60
# No logged effort in this many days => dormant (only assertable for projects
# that actually appear in the timesheet).
DORMANT_DAYS = 90
# A ticket with no technician for longer than this is surfaced on age alone.
STALE_UNASSIGNED_DAYS = 3
# Months of history to chart.
TREND_MONTHS = 12
# Assumed working day for the utilisation denominator. No leave calendar exists
# in the source, so this overstates any month containing absence.
WORKING_HOURS_PER_DAY = 8.0

# --- proposed KPI targets (NOT from the source data) --------------------------
# direction: "max" => value must stay at or below target; "min" => at or above.
TARGETS = {
    "portfolio_on_time":   {"target": 80.0, "direction": "min", "unit": "%"},
    "unowned_tickets":     {"target": 0.0,  "direction": "max", "unit": ""},
    "rca_coverage":        {"target": 80.0, "direction": "min", "unit": "%"},
    "sla_closure":         {"target": 90.0, "direction": "min", "unit": "%"},
    "mttr_hours":          {"target": 8.0,  "direction": "max", "unit": "h"},
    "first_response_h":    {"target": 4.0,  "direction": "max", "unit": "h"},
    "first_resp_breach":   {"target": 10.0, "direction": "max", "unit": "%"},
    "item_completion":     {"target": 95.0, "direction": "min", "unit": "%"},
    "bug_rate":            {"target": 20.0, "direction": "max", "unit": "%"},
    "utilisation":         {"target": 80.0, "direction": "min", "unit": "%"},
    # 15% is a conventional estimation-variance tolerance. Kept deliberately
    # looser than the others: with only ~860 items carrying an estimate, a
    # tighter band would flag a signal the sample cannot yet support.
    "effort_variance":     {"target": 15.0, "direction": "max", "unit": "%"},
    "test_pass_rate":      {"target": 90.0, "direction": "min", "unit": "%"},
}

# A KPI within this fraction of its target reads as "warn" rather than "critical".
WARN_BAND = 0.25

# --- chart series colours -----------------------------------------------------
# Validated against the data-viz six checks (lightness band, chroma floor, CVD
# separation, normal-vision floor, contrast) in BOTH light and dark modes.
SERIES_COLOURS = {
    "light": {"s1": "#698722", "s2": "#347ec4"},
    "dark":  {"s1": "#678811", "s2": "#2b7ec9"},
}
