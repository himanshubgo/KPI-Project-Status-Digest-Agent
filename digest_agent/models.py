"""Data structures shared across the pipeline."""

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Optional

Severity = Literal["ok", "warn", "crit"]


@dataclass
class Feed:
    """One source export and how current it is."""
    name: str
    path_name: str
    sheet: str
    rows: int
    as_of: Optional[date]
    days_old: Optional[int]

    @property
    def freshness(self) -> Severity:
        if self.days_old is None:
            return "crit"
        if self.days_old <= 7:
            return "ok"
        return "warn" if self.days_old <= 45 else "crit"


@dataclass
class Kpi:
    key: str
    label: str
    value: float
    display: str          # pre-formatted value, e.g. "3h02m" or "96.9%"
    context: str          # what the number is drawn from
    badge: str            # short status phrase
    severity: Severity
    target: Optional[float] = None
    direction: Optional[str] = None


@dataclass
class Chip:
    value: str
    label: str
    severity: Severity = "ok"


@dataclass
class Action:
    rank: int
    band: str             # "week" | "month" | "quarter"
    title: str
    chips: list[Chip]
    owner: str
    owner_vacant: bool
    due: str
    do: str
    effect: str
    severity: Severity
    fingerprint: str = ""

    @property
    def id(self) -> str:
        return f"action:{self.rank}"


@dataclass
class Note:
    """A watch item or a data-quality caveat."""
    text: str
    severity: Severity = "ok"


@dataclass
class Series:
    label: str
    values: list[Optional[float]]
    colour_slot: str      # "s1" | "s2"


@dataclass
class Brief:
    run_date: date
    feeds: list[Feed]
    kpis: list[Kpi]
    actions: list[Action]
    watch: list[Note]
    caveats: list[Note]
    months: list[str] = field(default_factory=list)
    bug_series: list[Series] = field(default_factory=list)
    completion_series: list[Series] = field(default_factory=list)
    completion_months: list[str] = field(default_factory=list)
    demand_months: list[str] = field(default_factory=list)
    demand_values: list[int] = field(default_factory=list)
    demand_split_index: int = 0
    source_line: str = ""
