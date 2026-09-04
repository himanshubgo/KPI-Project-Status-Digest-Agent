"""Turns the normalised exports into the facts the brief is built from.

Two measurement decisions matter more than any threshold here:

*   Completion is measured on *matured cohorts* only. A month's items are
    counted once that month is at least COHORT_MATURITY_DAYS old. Measured
    sooner, the newest month reads catastrophically low purely because its work
    has not had time to close -- August 2026 reads 50.9% raw against a true run
    rate near 96%.

*   "Dormant" is only asserted for projects that actually appear in the
    timesheet. The two systems join on project name alone and match roughly
    40% of the time, so for an unmatched project the absence of logged hours is
    evidence of nothing at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from . import config
from .sources import Exports, normalise_name


def last_complete_month(run: pd.Timestamp) -> pd.Period:
    return (run.to_period("M") - 1) if run.day < 28 else run.to_period("M")


def fmt_month(p) -> str:
    """Periods stringify as '2026-08'; briefs read better as "Aug'26"."""
    return p.strftime("%b'%y") if p is not None else ""


def _rate(num: float, den: float, scale: float = 100.0) -> Optional[float]:
    return None if not den else num / den * scale


@dataclass
class Facts:
    run: pd.Timestamp
    month: pd.Period                       # last complete month
    months: list[pd.Period]                # trend window

    # projects
    active: pd.DataFrame = field(default_factory=pd.DataFrame)
    past_due: pd.DataFrame = field(default_factory=pd.DataFrame)
    dormant: pd.DataFrame = field(default_factory=pd.DataFrame)
    shells: pd.DataFrame = field(default_factory=pd.DataFrame)
    evergreen: pd.DataFrame = field(default_factory=pd.DataFrame)
    unmatched_past_due: int = 0
    join_rate: float = 0.0
    owner_past_due: pd.DataFrame = field(default_factory=pd.DataFrame)
    owner_load: pd.DataFrame = field(default_factory=pd.DataFrame)
    group_table: pd.DataFrame = field(default_factory=pd.DataFrame)
    no_milestones: int = 0
    no_end_date: int = 0
    active_at_100: int = 0

    # tickets
    open_tickets: pd.DataFrame = field(default_factory=pd.DataFrame)
    unowned: pd.DataFrame = field(default_factory=pd.DataFrame)
    future_dated: int = 0
    future_finished: int = 0
    due_before_created: int = 0
    resolved_before_created: int = 0
    priority_table: pd.DataFrame = field(default_factory=pd.DataFrame)
    demand: pd.Series = field(default_factory=pd.Series)
    unowned_by_month: pd.Series = field(default_factory=pd.Series)
    technicians: int = 0
    client_impacting_pct: float = 0.0

    # monthly series
    bug_rate: dict = field(default_factory=dict)
    completion: dict = field(default_factory=dict)
    completion_months: list = field(default_factory=list)
    bug_median: float = 0.0
    completion_median: float = 0.0

    # scalar KPIs
    kpi: dict = field(default_factory=dict)


def analyse(ex: Exports, run_date: date | None = None) -> Facts:
    run = pd.Timestamp(run_date or config.today())
    month = last_complete_month(run)
    months = [month - i for i in range(config.TREND_MONTHS - 1, -1, -1)]
    f = Facts(run=run, month=month, months=months)

    # ============================================================== PROJECTS
    p = ex.projects
    active = p[~p["STATUS"].isin(config.CLOSED_PROJECT_STATUSES)].copy()
    f.active = active
    past_due = active[active["end"].notna() & (active["end"] < run) & (active["pct"] < 100)].copy()
    past_due["late_days"] = (run - past_due["end"]).dt.days
    f.past_due = past_due

    f.no_milestones = int(((active["OPEN MILESTONES"] + active["CLOSED MILESTONES"]) == 0).sum())
    f.no_end_date = int(active["end"].isna().sum())
    f.active_at_100 = int((active["pct"] == 100).sum())

    # effort join
    log_keys = set(ex.logs["key"]) | set(normalise_name(ex.logs["Project Name"])) \
        if "Project Name" in ex.logs.columns else set(ex.logs["key"])
    f.join_rate = float(active["key"].isin(log_keys).mean() * 100) if len(active) else 0.0

    window = ex.logs[(ex.logs["Log Date"] > run - pd.Timedelta(days=config.DORMANT_DAYS))
                     & (ex.logs["Log Date"] <= run)]
    hours_by_key = window.groupby("key")["hours"].sum()
    past_due["matched"] = past_due["key"].isin(log_keys)
    past_due["recent_hours"] = past_due["key"].map(hours_by_key).fillna(0.0)

    f.dormant = past_due[past_due["matched"] & (past_due["recent_hours"] == 0)]
    f.evergreen = past_due[past_due["recent_hours"] > 0]
    f.shells = past_due[(past_due["pct"] == 0) & (past_due["OPEN TASKS"] == 0)
                        & (past_due["CLOSED TASKS"] == 0)]
    f.unmatched_past_due = int((~past_due["matched"]).sum())

    f.owner_past_due = (past_due.groupby("OWNER")
                        .agg(projects=("PROJECT ID", "count"),
                             open_tasks=("OPEN TASKS", "sum"),
                             worst_days=("late_days", "max"))
                        .sort_values(["projects", "open_tasks"], ascending=False))
    pd_ids = set(past_due["PROJECT ID"])
    f.owner_load = (active.groupby("OWNER")
                    .agg(active=("PROJECT ID", "count"),
                         open_tasks=("OPEN TASKS", "sum"),
                         past_due=("PROJECT ID", lambda s: s.isin(pd_ids).sum()))
                    .sort_values("open_tasks", ascending=False))
    g = active.groupby("PROJECT GROUP").agg(projects=("PROJECT ID", "count"),
                                            open_tasks=("OPEN TASKS", "sum"),
                                            past_due=("PROJECT ID", lambda s: s.isin(pd_ids).sum()))
    g["late_pct"] = (g["past_due"] / g["projects"] * 100).round(0)
    f.group_table = g.sort_values("projects", ascending=False)

    # =============================================================== TICKETS
    raw, tk = ex.tickets_raw, ex.tickets
    f.future_dated = int((raw["Created Time_dt"] > run + pd.Timedelta(days=1)).sum())
    f.future_finished = int(((raw["Created Time_dt"] > run + pd.Timedelta(days=1))
                             & (raw["Request Status"] == "Finished")).sum())
    if "Due By Time_dt" in raw:
        f.due_before_created = int((raw["Due By Time_dt"] < raw["Created Time_dt"]).sum())
    if "Resolved Time_dt" in raw:
        f.resolved_before_created = int((raw["Resolved Time_dt"] < raw["Created Time_dt"]).sum())

    op = tk[tk["Request Status"].isin(config.OPEN_TICKET_STATUSES)].copy()
    op["age_days"] = (run - op["Created Time_dt"]).dt.days
    f.open_tickets = op
    f.unowned = op[op["unassigned"] & op["never_responded"]]
    f.technicians = int(tk["Technician"].nunique() - (1 if (tk["Technician"] == "Not Assigned").any() else 0))
    f.client_impacting_pct = float((tk["Client Impacting"] == "Yes").mean() * 100)

    pt = tk.groupby("Priority").agg(n=("RequestID", "count"),
                                    fr=("First Response Overdue Status", "mean"),
                                    res=("Overdue Status", "mean"))
    pt["fr"] = (pt["fr"] * 100).round(0)
    pt["res"] = (pt["res"] * 100).round(0)
    f.priority_table = pt.sort_values("n", ascending=False)

    tk = tk.assign(cmonth=tk["Created Time_dt"].dt.to_period("M"))
    f.demand = tk.groupby("cmonth").size()
    f.unowned_by_month = tk[tk["unassigned"]].groupby("cmonth").size()

    # ============================================================ WORK ITEMS
    items = ex.items.copy()
    items["cmonth"] = items["created"].dt.to_period("M")
    in_window = items[items["cmonth"].isin(months)]

    for label, group in config.STREAMS.items():
        sub = in_window[in_window["Project Group"] == group]
        by = sub.groupby("cmonth")["Item Type"].apply(lambda s: (s == "Bug").mean() * 100)
        f.bug_rate[label] = [round(by.get(m), 1) if m in by.index and pd.notna(by.get(m)) else None
                             for m in months]

    mature_cut = run - pd.Timedelta(days=config.COHORT_MATURITY_DAYS)
    mature = items[items["created"] <= mature_cut]
    f.completion_months = [m for m in months if m.end_time <= mature_cut]
    for label, group in config.STREAMS.items():
        sub = mature[(mature["Project Group"] == group) & (mature["cmonth"].isin(f.completion_months))]
        by = sub.groupby("cmonth")["Status"].apply(lambda s: s.isin(config.DONE_ITEM_STATUSES).mean() * 100)
        f.completion[label] = [round(by.get(m), 1) if m in by.index and pd.notna(by.get(m)) else None
                               for m in f.completion_months]

    allbug = in_window.groupby("cmonth")["Item Type"].apply(lambda s: (s == "Bug").mean() * 100)
    f.bug_median = round(float(allbug.median()), 1) if len(allbug) else 0.0
    allcomp = mature[mature["cmonth"].isin(f.completion_months)] \
        .groupby("cmonth")["Status"].apply(lambda s: s.isin(config.DONE_ITEM_STATUSES).mean() * 100)
    f.completion_median = round(float(allcomp.median()), 1) if len(allcomp) else 0.0

    # ============================================================ SCALAR KPIs
    cur = f.month
    k = f.kpi

    k["portfolio_on_time"] = _rate(len(active) - len(past_due), len(active))
    k["past_due_count"] = len(past_due)
    k["active_count"] = len(active)
    k["unowned_tickets"] = len(f.unowned)
    k["open_tickets"] = len(op)
    k["unowned_high"] = int(f.unowned["Priority"].isin(config.HIGH_TICKET_PRIORITIES).sum())
    k["unowned_ci"] = int((f.unowned["Client Impacting"] == "Yes").sum())
    k["unowned_oldest"] = int(f.unowned["age_days"].max()) if len(f.unowned) else 0
    k["open_breached"] = int(op["Overdue Status"].sum())
    k["open_high_ci"] = int((op["Priority"].isin(config.HIGH_TICKET_PRIORITIES)
                             & (op["Client Impacting"] == "Yes")).sum())

    rca = items[items.get("Ticket with RCA", pd.Series(dtype=object)).isin(["Yes", "No"])] \
        if "Ticket with RCA" in items else items.iloc[0:0]
    k["rca_coverage"] = _rate((rca["Ticket with RCA"] == "Yes").sum(), len(rca))
    k["rca_n"] = len(rca)
    k["rca_yes"] = int((rca["Ticket with RCA"] == "Yes").sum()) if len(rca) else 0

    sla = in_window[in_window.get("Ticket Closure within SLA", pd.Series(dtype=object)).isin(["Yes", "No"])] \
        if "Ticket Closure within SLA" in in_window else in_window.iloc[0:0]
    sla_cur = sla[sla["cmonth"] == cur]
    k["sla_closure"] = _rate((sla_cur["Ticket Closure within SLA"] == "Yes").sum(), len(sla_cur))
    k["sla_n"] = len(sla_cur)
    sla_first = sla[sla["cmonth"] == months[0]]
    k["sla_closure_first"] = _rate((sla_first["Ticket Closure within SLA"] == "Yes").sum(), len(sla_first))

    fin = tk[(tk["Request Status"] == "Finished") & tk["Resolved Time_dt"].notna()].copy()
    fin["res_h"] = (fin["Resolved Time_dt"] - fin["Created Time_dt"]).dt.total_seconds() / 3600
    fin = fin[fin["res_h"] >= 0]
    fin_cur = fin[fin["Resolved Time_dt"].dt.to_period("M") == cur]
    k["mttr_hours"] = float(fin_cur["res_h"].median()) if len(fin_cur) else None
    k["mttr_n"] = len(fin_cur)

    resp = tk[tk["Responded Date_dt"].notna()].copy()
    resp["resp_h"] = (resp["Responded Date_dt"] - resp["Created Time_dt"]).dt.total_seconds() / 3600
    resp = resp[resp["resp_h"] >= 0]
    resp_cur = resp[resp["cmonth"] == cur]
    k["first_response_h"] = float(resp_cur["resp_h"].median()) if len(resp_cur) else None
    k["first_response_n"] = len(resp_cur)
    resp_first = resp[resp["cmonth"] == months[0]]
    k["first_response_first"] = float(resp_first["resp_h"].median()) if len(resp_first) else None

    tk_cur = tk[tk["cmonth"] == cur]
    k["first_resp_breach"] = _rate(tk_cur["First Response Overdue Status"].sum(), len(tk_cur))
    k["first_resp_breach_n"] = len(tk_cur)

    comp_vals = [v for v in (f.completion.get(lbl) or [] for lbl in config.STREAMS) if v]
    latest_cohort = f.completion_months[-1] if f.completion_months else None
    if latest_cohort is not None:
        cohort = mature[mature["cmonth"] == latest_cohort]
        k["item_completion"] = _rate(cohort["Status"].isin(config.DONE_ITEM_STATUSES).sum(), len(cohort))
        k["item_completion_month"] = fmt_month(latest_cohort)
        k["item_completion_n"] = len(cohort)

    bug_cur = in_window[in_window["cmonth"] == cur]
    k["bug_rate"] = _rate((bug_cur["Item Type"] == "Bug").sum(), len(bug_cur))
    k["bug_n"] = len(bug_cur)
    k["bug_bugs"] = int((bug_cur["Item Type"] == "Bug").sum())

    logs = ex.logs.assign(lmonth=ex.logs["Log Date"].dt.to_period("M"))
    lm = logs[logs["lmonth"] == cur]
    people = int(lm["Log owner"].nunique())
    workdays = int(np.busday_count(str(cur.start_time.date()),
                                   str((cur.end_time + pd.Timedelta(days=1)).date())))
    capacity = people * workdays * config.WORKING_HOURS_PER_DAY
    k["utilisation"] = _rate(lm["hours"].sum(), capacity)
    k["utilisation_hours"] = float(lm["hours"].sum())
    k["utilisation_people"] = people
    k["utilisation_days"] = workdays
    prev = cur - 2
    lp = logs[logs["lmonth"] == prev]
    ppl = int(lp["Log owner"].nunique())
    wd = int(np.busday_count(str(prev.start_time.date()),
                             str((prev.end_time + pd.Timedelta(days=1)).date())))
    k["utilisation_prev"] = _rate(lp["hours"].sum(), ppl * wd * config.WORKING_HOURS_PER_DAY)
    k["utilisation_prev_month"] = fmt_month(prev)

    win = logs[(logs["Log Date"] > run - pd.Timedelta(days=config.DORMANT_DAYS))
               & (logs["Log Date"] <= run)]
    k["window_hours"] = float(win["hours"].sum())
    k["window_people"] = int(win["Log owner"].nunique())
    k["window_projects"] = int(win["Project"].nunique())
    billable = win[win.get("Billing Status", pd.Series(dtype=object)) == "Billable"] \
        if "Billing Status" in win else win.iloc[0:0]
    k["billable_pct"] = _rate(billable["hours"].sum(), win["hours"].sum())
    if "Billing Status" in ex.logs.columns:
        k["billable_all_time"] = int((ex.logs["Billing Status"] == "Billable").sum())
        k["logs_all_time"] = len(ex.logs)

    if "Estimated Hours" in ex.logs.columns:
        act = ex.logs.groupby("Item Id")["hours"].sum()
        est = ex.logs.groupby("Item Id")["Estimated Hours"].first()
        ea = pd.DataFrame({"est": est, "act": act}).dropna()
        ea = ea[ea["est"] > 0]
        if len(ea):
            k["effort_variance"] = (ea["act"].sum() / ea["est"].sum() - 1) * 100
            k["effort_items"] = len(ea)
            k["effort_est"] = float(ea["est"].sum())
            k["effort_act"] = float(ea["act"].sum())
            k["effort_over_2x"] = int((ea["act"] / ea["est"] > 2).sum())

    if "Testing Status" in items.columns:
        tst = items[items["Testing Status"].isin(["PASS", "FAILED"])]
        tst_cur = tst[tst["cmonth"] == cur]
        k["test_pass_rate"] = _rate((tst_cur["Testing Status"] == "PASS").sum(), len(tst_cur))
        k["test_n_total"] = len(tst)
        k["test_n_month"] = len(tst_cur)
        k["items_total"] = len(items)

    return f
