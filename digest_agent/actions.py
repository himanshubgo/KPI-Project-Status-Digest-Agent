"""Derives the action board and the watch list.

Every action is gated on a trigger computed from the data. If a condition
clears, the action stops appearing -- the board is not a fixed template with
numbers dropped into it.
"""

from __future__ import annotations

import pandas as pd

from . import config
from .analysis import Facts, fmt_month
from .models import Action, Chip, Note

BAND_LABELS = {"week": "Do this week", "month": "Do this month", "quarter": "Do this quarter"}
BAND_ORDER = ["week", "month", "quarter"]


def _due(f: Facts, band: str) -> str:
    run = f.run
    if band == "week":
        return (run + pd.Timedelta(days=7)).strftime("%d %b %Y")
    if band == "month":
        return (run.to_period("M").end_time).strftime("%d %b %Y")
    q_end = pd.Timestamp(year=run.year, month=12, day=31)
    return q_end.strftime("%d %b %Y")


def build(f: Facts) -> list[Action]:
    k = f.kpi
    out: list[Action] = []

    # ---- 01 unowned tickets -------------------------------------------------
    if k.get("unowned_tickets", 0) > 0:
        recent = f.unowned_by_month.tail(2)
        spike = ("Unowned intake: " + ", ".join(f"{v} in {fmt_month(m)}" for m, v in recent.items())
                 + ".") if len(recent) else ""
        out.append(Action(
            rank=0, band="week", severity="crit",
            title=f"Name a triage owner and clear the {k['unowned_tickets']} unclaimed tickets",
            chips=[
                Chip(str(k["unowned_tickets"]), "no owner, never answered", "crit"),
                Chip(str(k["unowned_high"]), "High or Urgent", "crit"),
                Chip(str(k["unowned_ci"]), "client-impacting"),
                Chip(f"{k['unowned_oldest']}d", "oldest"),
                Chip(str(k["open_tickets"]), "open in total"),
                Chip(f"{f.client_impacting_pct:.0f}%", "of queue is client-impacting"),
            ],
            owner="Vacant — field empty on all %d" % k["unowned_tickets"], owner_vacant=True,
            due=_due(f, "week"),
            do=f"Work them down by age, then auto-escalate anything unassigned past 24h. {spike}".strip(),
            effect="Removes the only live client-facing risk",
            fingerprint=f"unowned={k['unowned_tickets']}"))

    # ---- 02 priority inversion ---------------------------------------------
    pt = f.priority_table
    if {"Urgent", "Normal"} <= set(pt.index):
        urgent_fr, normal_fr = pt.loc["Urgent", "fr"], pt.loc["Normal", "fr"]
        if urgent_fr > normal_fr:
            high_fr = pt.loc["High", "fr"] if "High" in pt.index else None
            labels = sorted(set(pt.index) - {"Not Assigned"})
            out.append(Action(
                rank=0, band="month", severity="crit",
                title="Collapse the priority scale to three tiers and re-measure",
                chips=[
                    Chip(f"{urgent_fr:.0f}%", "Urgent miss first response", "crit"),
                    *([Chip(f"{high_fr:.0f}%", "High miss", "warn")] if high_fr is not None else []),
                    Chip(f"{normal_fr:.0f}%", "Normal miss", "ok"),
                    Chip(str(len(labels)), "overlapping labels in use"),
                ],
                owner="Service desk + PMO", owner_vacant=False, due=_due(f, "month"),
                do="Merge Normal/Medium and High/Urgent; set a response target per tier",
                effect="Escalation starts buying attention instead of predicting neglect",
                fingerprint=f"urgent_fr={urgent_fr:.0f}"))

    # ---- 03 ticket integrity ------------------------------------------------
    if f.future_dated or f.due_before_created:
        out.append(Action(
            rank=0, band="month", severity="crit",
            title="Explain the impossible ticket dates before automating any reporting",
            chips=[
                Chip(str(f.future_dated), "created in the future", "crit"),
                Chip(str(f.future_finished), "of those marked Finished", "crit"),
                Chip(str(f.due_before_created), "due before created", "warn"),
                Chip(str(f.resolved_before_created), "resolved before created", "warn"),
            ],
            owner="Zoho administrator", owner_vacant=False, due=_due(f, "month"),
            do="Trace whether this is a template, a timezone fault, or backdated bulk edits",
            effect="Unblocks automated SLA reporting — currently not trustworthy",
            fingerprint=f"future={f.future_dated}|dbc={f.due_before_created}"))

    # ---- 04 billing default -------------------------------------------------
    if (k.get("billable_pct") or 0) < 5:
        out.append(Action(
            rank=0, band="month", severity="warn",
            title="Set a billing-status default so utilisation becomes reportable",
            chips=[
                Chip(f"{k.get('billable_pct', 0):.0f}%", f"of {config.DORMANT_DAYS}-day hours billable", "crit"),
                Chip(f"{k.get('window_hours', 0):,.0f}h", f"logged in {config.DORMANT_DAYS} days"),
                Chip(str(k.get("window_people", 0)), "people logging"),
            ],
            owner="Finance + PMO", owner_vacant=False, due=_due(f, "month"),
            do="Confirm whether non-billable is the real position or an unchanged default",
            effect="First billable ratio the team can actually report",
            fingerprint=f"billable={k.get('billable_pct', 0):.1f}"))

    # ---- 05 portfolio reconciliation ---------------------------------------
    if len(f.past_due):
        top = f.owner_past_due.head(3)
        owners = " · ".join(f"{name} {row.projects}" for name, row in top.iterrows())
        median_days = int(f.past_due["late_days"].median())
        over_year = int((f.past_due["late_days"] > 365).sum())
        out.append(Action(
            rank=0, band="quarter", severity="crit",
            title=f"Clear all {len(f.past_due)} past-due projects in one reconciliation pass",
            chips=[
                Chip(str(len(f.past_due)), "past end date", "crit"),
                Chip(f"{median_days}d", "median overrun"),
                Chip(str(over_year), "over a year late", "crit"),
                Chip(str(len(f.dormant)), "dormant — close"),
                Chip(str(len(f.shells)), "never recorded a task"),
                Chip(str(len(f.evergreen)), "evergreen — reclassify", "ok"),
            ],
            owner=owners, owner_vacant=False, due=_due(f, "quarter"),
            do="Close, re-baseline or reclassify as a batch — the overrun is systemic, not per-project",
            effect="Register becomes usable for forecasting and capacity",
            fingerprint=f"pastdue={len(f.past_due)}"))

    # ---- 06 project hygiene -------------------------------------------------
    if f.no_milestones or f.no_end_date:
        n_active = len(f.active)
        out.append(Action(
            rank=0, band="quarter", severity="warn",
            title="Add an evergreen status; require an end date and one milestone to open a project",
            chips=[
                Chip(f"{f.no_milestones}/{n_active}", "active have no milestones", "crit"),
                Chip(str(f.no_end_date), "active have no end date"),
                Chip(str(len(f.evergreen)), "maintenance lines read as late"),
                Chip(str(f.active_at_100), "active sitting at 100%", "warn"),
            ],
            owner="PMO", owner_vacant=False, due=_due(f, "quarter"),
            do="Make the two fields mandatory at creation, not optional",
            effect="Stops the overrun rebuilding, and lets schedule rules run automatically",
            fingerprint=f"nomilestones={f.no_milestones}"))

    out.sort(key=lambda a: (BAND_ORDER.index(a.band), {"crit": 0, "warn": 1, "ok": 2}[a.severity]))
    for i, a in enumerate(out, 1):
        a.rank = i
    return out


def build_watch(f: Facts) -> list[Note]:
    k, out = f.kpi, []

    ev = k.get("effort_variance")
    if ev is not None and abs(ev) > 5:
        out.append(Note(
            f"<b>Effort is running {ev:+.0f}% against estimate.</b> {k['effort_items']:,} work items "
            f"carry an estimate — a field absent from earlier exports — showing "
            f"{k['effort_act']:,.0f}h actual against {k['effort_est']:,.0f}h planned, with "
            f"{k['effort_over_2x']} items past double. Give it another month before drawing a conclusion.",
            "ok"))

    for label, vals in f.completion.items():
        clean = [(m, v) for m, v in zip(f.completion_months, vals) if v is not None]
        if len(clean) >= 4:
            recent = [v for _, v in clean[-3:]]
            if recent == sorted(recent, reverse=True) and recent[0] - recent[-1] > 8:
                out.append(Note(
                    f"<b>{label} completion has fallen three months running</b> — "
                    f"{recent[0]:.1f}% down to {recent[-1]:.1f}% ({fmt_month(clean[-1][0])} cohort), while "
                    f"the other stream held. The newest cohort has only just passed the "
                    f"{config.COHORT_MATURITY_DAYS}-day maturity line, so part of the drop may still close "
                    f"out. Re-read in four weeks.", "warn"))

    util, prev = k.get("utilisation"), k.get("utilisation_prev")
    if util is not None and prev is not None and prev - util > 10:
        out.append(Note(
            f"<b>Utilisation dropped from {prev:.1f}% in {k['utilisation_prev_month']} to {util:.1f}% "
            f"in {fmt_month(f.month)}</b> — {k['utilisation_hours']:,.0f} hours across "
            f"{k['utilisation_people']} people. "
            f"No leave calendar exists in the data, so this could be absence, under-logging, or genuine "
            f"slack. One question to the team leads before it is read as capacity.", "warn"))

    load = f.owner_load
    if len(load) >= 3 and load["open_tasks"].sum():
        top3 = load.head(3)
        share = top3["open_tasks"].sum() / load["open_tasks"].sum() * 100
        if share > 40:
            who = ", ".join(f"{n} {int(r.open_tasks)}" for n, r in top3.iterrows())
            out.append(Note(
                f"<b>Three owners hold {share:.0f}% of open work.</b> {who}, of "
                f"{int(load['open_tasks'].sum()):,} across {len(load)} owners. Much of this is likely dormant "
                f"projects inflating the count — re-measure after the reconciliation.", "ok"))

    for label, vals in f.bug_rate.items():
        clean = [v for v in vals if v is not None]
        if len(clean) >= 6 and (max(clean) - min(clean)) > 50:
            out.append(Note(
                f"<b>Bug rate is not a usable signal for {label}.</b> It swings between {min(clean):.0f}% "
                f"and {max(clean):.0f}% month to month, which points to batch-logging rather than genuine "
                f"quality movement.", "warn"))

    g = f.group_table
    if len(g):
        worst = g.sort_values("late_pct", ascending=False)
        worst = worst[worst["projects"] >= 5]
        if len(worst):
            name = worst.index[0]
            best = worst.sort_values("late_pct").index[0]
            out.append(Note(
                f"<b>{name} is the weakest group on schedule.</b> {int(worst.iloc[0].past_due)} of "
                f"{int(worst.iloc[0].projects)} projects past due ({worst.iloc[0].late_pct:.0f}%), against "
                f"{worst.loc[best, 'late_pct']:.0f}% in {best}.", "ok"))
    return out
