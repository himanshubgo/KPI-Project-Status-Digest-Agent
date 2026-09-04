"""Builds the KPI tiles from computed facts.

Severity comes from comparing each value to its target in config.TARGETS.
Those targets are proposals, not agreed thresholds -- nothing in the source
exports defines one -- so the rendered brief says so next to the board.
"""

from __future__ import annotations

from . import config
from .analysis import Facts, fmt_month
from .models import Kpi


def severity(value, key) -> str:
    spec = config.TARGETS.get(key)
    if value is None or spec is None:
        return "warn"
    target, direction = spec["target"], spec["direction"]
    if direction == "max":
        if target == 0:
            return "ok" if value <= 0 else "crit"
        if value <= target:
            return "ok"
        return "warn" if value <= target * (1 + config.WARN_BAND) else "crit"
    if value >= target:
        return "ok"
    return "warn" if value >= target * (1 - config.WARN_BAND) else "crit"


def pct(v, dp=1) -> str:
    return "—" if v is None else f"{v:.{dp}f}%"


def hours(v) -> str:
    if v is None:
        return "—"
    if v < 1:
        return f"{round(v * 60)}m"
    h = int(v)
    m = round((v - h) * 60)
    if m == 60:
        h, m = h + 1, 0
    return f"{h}h{m:02d}m"


def build(f: Facts) -> list[Kpi]:
    k = f.kpi
    cur, first = fmt_month(f.month), fmt_month(f.months[0])
    out: list[Kpi] = []

    def add(key, label, value, display, context, badge, sev=None):
        spec = config.TARGETS.get(key, {})
        out.append(Kpi(key=key, label=label, value=value, display=display,
                       context=context, badge=badge,
                       severity=sev or severity(value, key),
                       target=spec.get("target"), direction=spec.get("direction")))

    add("portfolio_on_time", "Portfolio on time", k.get("portfolio_on_time"),
        pct(k.get("portfolio_on_time"), 0),
        f"{k['active_count'] - k['past_due_count']} of {k['active_count']} active projects",
        f"{k['past_due_count']} past end date")

    add("unowned_tickets", "Tickets unowned", float(k.get("unowned_tickets", 0)),
        str(k.get("unowned_tickets", 0)),
        f"of {k.get('open_tickets', 0)} open · never answered",
        "Action 01")

    add("rca_coverage", "RCA coverage", k.get("rca_coverage"), pct(k.get("rca_coverage")),
        f"{k.get('rca_yes', 0):,} of {k.get('rca_n', 0):,} scored items",
        "No root-cause trail")

    sla_first = k.get("sla_closure_first")
    add("sla_closure", "Ticket closure in SLA", k.get("sla_closure"), pct(k.get("sla_closure")),
        f"{k.get('sla_n', 0)} items scored · {cur}",
        f"✓ up from {pct(sla_first, 0)} {first}" if sla_first else "✓")

    add("mttr_hours", "MTTR service desk", k.get("mttr_hours"), hours(k.get("mttr_hours")),
        f"median of {k.get('mttr_n', 0)} resolved", "✓ steady")

    fr_first = k.get("first_response_first")
    add("first_response_h", "First response", k.get("first_response_h"),
        hours(k.get("first_response_h")),
        f"median · {k.get('first_response_n', 0)} tickets",
        f"✓ from {hours(fr_first)} {first}" if fr_first else "✓")

    add("first_resp_breach", "First-resp. breach", k.get("first_resp_breach"),
        pct(k.get("first_resp_breach"), 0),
        f"of {k.get('first_resp_breach_n', 0)} raised in {cur}",
        "⚠ flat all year")

    comp = k.get("item_completion")
    add("item_completion", "Work item completion", comp, pct(comp),
        f"{k.get('item_completion_month', '')} cohort · {k.get('item_completion_n', 0)} items",
        f"⚠ below {f.completion_median}% median" if comp is not None and comp < f.completion_median
        else f"✓ at or above {f.completion_median}% median")

    add("bug_rate", "Bug rate", k.get("bug_rate"), pct(k.get("bug_rate")),
        f"{k.get('bug_bugs', 0)} of {k.get('bug_n', 0)} items raised",
        f"✓ below {f.bug_median}% median" if (k.get("bug_rate") or 0) < f.bug_median
        else f"⚠ above {f.bug_median}% median")

    prev = k.get("utilisation_prev")
    add("utilisation", "Team utilisation", k.get("utilisation"), pct(k.get("utilisation")),
        f"{k.get('utilisation_hours', 0):,.0f}h · {k.get('utilisation_people', 0)} people "
        f"· {k.get('utilisation_days', 0)} days",
        f"↓ from {pct(prev)} in {k.get('utilisation_prev_month', '')}" if prev else "—")

    ev = k.get("effort_variance")
    add("effort_variance", "Effort vs estimate", abs(ev) if ev is not None else None,
        f"{ev:+.0f}%" if ev is not None else "—",
        f"{k.get('effort_act', 0):,.0f}h actual / {k.get('effort_est', 0):,.0f}h planned",
        f"⚠ {k.get('effort_over_2x', 0)} items over 2×")

    add("test_pass_rate", "Test pass rate", k.get("test_pass_rate"), pct(k.get("test_pass_rate")),
        f"{cur} · {k.get('test_n_month', 0)} items · thin sample",
        f"⚠ only {k.get('test_n_total', 0)} items scored")

    return out
