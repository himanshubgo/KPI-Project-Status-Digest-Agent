"""Loads the three Zoho exports and normalises them.

Two hard-won rules are baked in:

1.  Workbooks are found by filename *fragment*, and sheets by *column
    signature* -- never by exact name. During the assessment the service desk
    export was replaced under a filename describing a different date, and its
    single sheet was renamed at the same time. Anything keyed on names breaks
    silently when that happens.

2.  Every timestamp column is parsed against an explicit list of formats. The
    exports mix "%m-%d-%Y", "%d/%b/%Y %I:%M %p" and native datetimes, and a
    silent NaT here would quietly drop rows from every downstream count.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import config
from .models import Feed

DATE_FORMATS = [
    "%m-%d-%Y %I:%M %p",
    "%m-%d-%Y %H:%M",
    "%m-%d-%Y",
    "%d/%b/%Y %I:%M %p",
    "%d/%b/%Y",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
]


def parse_dates(s: pd.Series) -> pd.Series:
    """Parse a column that may hold datetimes, or strings in any known format."""
    if pd.api.types.is_datetime64_any_dtype(s):
        return s
    text = s.astype("string").str.strip()
    text = text.mask(text.isin(["-", "", "Not Assigned", "NaT", "nan", "None"]))
    best = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    for fmt in DATE_FORMATS:
        missing = best.isna() & text.notna()
        if not missing.any():
            break
        attempt = pd.to_datetime(text[missing], format=fmt, errors="coerce")
        best.loc[missing] = attempt
    still = best.isna() & text.notna()
    if still.any():
        best.loc[still] = pd.to_datetime(text[still], errors="coerce", format="mixed")
    return best


def _pct(s: pd.Series) -> pd.Series:
    """'85%' / 0.85 / 85 -> 85.0"""
    if pd.api.types.is_numeric_dtype(s):
        v = s.astype(float)
        # a column stored as a fraction (Zoho does this on some exports)
        return v * 100 if v.max(skipna=True) is not None and v.max(skipna=True) <= 1.0 else v
    return pd.to_numeric(s.astype(str).str.rstrip("%").str.strip(), errors="coerce")


def normalise_name(s: pd.Series) -> pd.Series:
    """Project-name key. Unicode dashes and doubled spaces differ between systems."""
    return (s.astype(str).str.strip().str.lower()
             .str.replace(r"[‐-―]", "-", regex=True)
             .str.replace(r"\s+", " ", regex=True))


class FeedNotFound(Exception):
    """No sheet in the supplied files matches a required feed's column signature."""


@dataclass
class Candidate:
    path: Path
    sheet: str
    columns: set
    fragment_hit: bool


def _candidates(data_dir: Path) -> list[Candidate]:
    """Every sheet in every spreadsheet in the folder, with its column names.

    Only headers are read here -- the 21MB timesheet workbook is far too large
    to load speculatively.
    """
    out: list[Candidate] = []
    fragments = {k: v.lower() for k, v in config.WORKBOOKS.items()}
    for path in sorted(data_dir.iterdir()):
        if path.name.startswith("~$") or not path.is_file():
            continue
        suffix = path.suffix.lower()
        hit = any(fr in path.name.lower() for fr in fragments.values())
        try:
            if suffix in (".xlsx", ".xlsm", ".xls"):
                # Closed explicitly: an open ExcelFile keeps a Windows file
                # handle, which would leave uploaded files locked and make the
                # web app's own "delete run" fail.
                with pd.ExcelFile(path) as book:
                    for sheet in book.sheet_names:
                        cols = set(book.parse(sheet, nrows=0).columns)
                        out.append(Candidate(path, sheet, cols, hit))
            elif suffix == ".csv":
                cols = set(pd.read_csv(path, nrows=0).columns)
                out.append(Candidate(path, "", cols, hit))
        except Exception:
            continue  # unreadable file: skipped, and reported as a missing feed
    return out


def _read(cand: Candidate) -> pd.DataFrame:
    if cand.sheet == "":
        return pd.read_csv(cand.path)
    with pd.ExcelFile(cand.path) as book:
        return book.parse(cand.sheet)


def discover(feed: str, cands: list[Candidate], *, min_overlap: int = 3) -> tuple[Candidate, pd.DataFrame]:
    """Pick the sheet that best matches a feed's column signature.

    Matching is on columns, never on filenames or sheet names. During the
    assessment the service desk export was replaced under a filename describing
    a different date, and its sheet was renamed in the same swap -- so the
    filename is only ever a tie-breaker, never the identifier.
    """
    signature = config.SHEET_SIGNATURES[feed]
    scored = [(len(signature & c.columns), c) for c in cands]
    scored = [(n, c) for n, c in scored if n >= min(min_overlap, len(signature))]
    if not scored:
        raise FeedNotFound(feed)
    best = max(n for n, _ in scored)
    finalists = [c for n, c in scored if n == best]
    if len(finalists) > 1:
        finalists.sort(key=lambda c: (not c.fragment_hit, -c.path.stat().st_mtime))
        frames = {(c.path, c.sheet): _read(c) for c in finalists}
        chosen = max(finalists, key=lambda c: (c.fragment_hit, len(frames[(c.path, c.sheet)])))
        return chosen, frames[(chosen.path, chosen.sheet)]
    return finalists[0], _read(finalists[0])


@dataclass
class Exports:
    projects: pd.DataFrame
    items: pd.DataFrame      # unique work items
    logs: pd.DataFrame       # time-log rows
    tickets: pd.DataFrame    # analysable tickets (created on/before run date)
    tickets_raw: pd.DataFrame
    feeds: list[Feed]

    def feed(self, name: str) -> Feed:
        return next(f for f in self.feeds if f.name == name)


def load(data_dir: Path | None = None, run_date=None) -> Exports:
    data_dir = data_dir or config.DATA_DIR
    run_ts = pd.Timestamp(run_date or config.today())
    feeds: list[Feed] = []

    def age(ts):
        """Freshness of a feed. Future timestamps are never treated as 'fresher
        than now' -- the service desk export carries rows dated months ahead,
        which would otherwise report a negative age."""
        if pd.isna(ts):
            return None, None
        d = ts.date() if hasattr(ts, "date") else ts
        days = (run_ts.normalize() - pd.Timestamp(d)).days
        return d, max(days, 0)

    cands = _candidates(data_dir)
    if not cands:
        raise FeedNotFound("no readable spreadsheet found")

    # ---------------------------------------------------------------- projects
    pcand, p = discover("projects", cands)
    ppath, psheet = pcand.path, pcand.sheet
    p = p.rename(columns={"PRIMARY CLIENT": "PRIMARY CUSTOMER"})
    p["start"] = parse_dates(p["START DATE"])
    p["end"] = parse_dates(p["END DATE"])
    p["modified"] = parse_dates(p["LAST MODIFIED TIME"])
    p["pct"] = _pct(p["%"])
    p["key"] = normalise_name(p["PROJECT NAME"])
    for col in ("OPEN TASKS", "CLOSED TASKS", "OPEN MILESTONES", "CLOSED MILESTONES"):
        if col in p.columns:
            p[col] = pd.to_numeric(p[col], errors="coerce").fillna(0).astype(int)
    as_of, days = age(p["modified"].max())
    feeds.append(Feed("Zoho Projects", ppath.name, psheet, len(p), as_of, days))

    # --------------------------------------------------------------- timesheet
    tcand, logs = discover("timesheet", cands)
    tpath, tsheet = tcand.path, tcand.sheet
    logs["Log Date"] = parse_dates(logs["Log Date"])
    logs["hours"] = pd.to_numeric(logs.get("Log Hours(for calculation)"), errors="coerce").fillna(0.0)
    logs["key"] = normalise_name(logs["Project"])
    as_of, days = age(logs["Log Date"].max())
    feeds.append(Feed("Timesheets", tpath.name, tsheet, len(logs), as_of, days))

    items = logs.dropna(subset=["Item Id"]).drop_duplicates("Item Id").copy()
    items["created"] = parse_dates(items["Created On.1"]) if "Created On.1" in items else pd.NaT
    items["completed"] = parse_dates(items["Completed On"]) if "Completed On" in items else pd.NaT

    # ----------------------------------------------------------------- tickets
    kcand, k = discover("tickets", cands)
    kpath, ksheet = kcand.path, kcand.sheet
    for col in ["Created Time", "Responded Date", "Resolved Time", "Due By Time",
                "Response Due By Time", "Last Updated Time", "Completed Time"]:
        if col in k.columns:
            k[col + "_dt"] = parse_dates(k[col])
    for col in ["Overdue Status", "Pending Status", "First Response Overdue Status"]:
        if col in k.columns:
            k[col] = k[col].astype(str).str.lower().isin(["true", "1", "yes"])
    k["never_responded"] = k["Responded Date"].astype(str).str.strip() == "Not Assigned"
    k["unassigned"] = k["Technician"].astype(str).str.strip() == "Not Assigned"
    # The run date is the anchor, not the file's own max timestamp: the export
    # carries rows dated into the future, which would corrupt every age.
    analysable = k[k["Created Time_dt"] <= run_ts + pd.Timedelta(days=1)].copy()
    touched = analysable["Last Updated Time_dt"]
    as_of, days = age(touched[touched <= run_ts + pd.Timedelta(days=1)].max())
    feeds.append(Feed("Service Desk", kpath.name, ksheet, len(k), as_of, days))

    return Exports(projects=p, items=items, logs=logs,
                   tickets=analysable, tickets_raw=k, feeds=feeds)
