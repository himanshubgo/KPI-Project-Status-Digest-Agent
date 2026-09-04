"""Data-quality caveats.

These are as much a deliverable as the KPIs: the assessment asked for the gaps
to be reported alongside the numbers. Each caveat is triggered by a measured
condition, so it disappears once the underlying problem is fixed.
"""

from __future__ import annotations

from . import config
from .analysis import Facts, fmt_month
from .models import Note
from .sources import Exports


def build(f: Facts, ex: Exports) -> list[Note]:
    k, out = f.kpi, []

    if f.future_dated:
        out.append(Note(
            f"<b>Ticket integrity is the one hard blocker.</b> {len(ex.tickets):,} tickets are analysable "
            f"after excluding {f.future_dated} dated in the future, {f.future_finished} of which are already "
            f"marked Finished. A further {f.due_before_created} carry a due date before their creation date. "
            f"Exclusions are defensible; the export is not yet a trustworthy system of record.", "crit"))

    if f.join_rate < 80:
        out.append(Note(
            f"<b>Projects and timesheets join on name alone, matching {f.join_rate:.0f}% of the time.</b> "
            f"The two systems use unrelated ID schemes, so {f.unmatched_past_due} of the {len(f.past_due)} "
            f"past-due projects cannot be checked against effort at all. The {len(f.dormant)} dormant and "
            f"{len(f.evergreen)} evergreen splits are solid; the rest are unverified.", "warn"))

    if k.get("window_projects") and len(f.active):
        out.append(Note(
            f"<b>Only {k['window_projects']} project lines received logged time in "
            f"{config.DORMANT_DAYS} days</b> against {len(f.active)} active projects. The naming mismatch "
            f"above inflates that gap, so treat it as directional rather than exact.", "warn"))

    out.append(Note(
        "<b>The two streams are Project Groups, not Scrum and Kanban.</b> No board-type field exists in the "
        "current export, so " + " and ".join(config.STREAMS) + " are the closest real split the data "
        "supports. Read the charts as project delivery versus maintenance.", "warn"))

    out.append(Note(
        "<b>No KPI targets exist anywhere in the source.</b> The thresholds colouring the tiles are proposals "
        "set in <code>config.TARGETS</code> pending sign-off, and the dashed chart lines are 12-month medians "
        "computed from the data itself — not agreed thresholds.", "warn"))

    out.append(Note(
        f"<b>Completion is measured on matured cohorts.</b> Items count only once their creation month is at "
        f"least {config.COHORT_MATURITY_DAYS} days old, because measuring recent months directly makes them "
        f"look catastrophic purely from immaturity. The chart therefore ends at "
        f"{fmt_month(f.completion_months[-1]) if f.completion_months else 'n/a'}, not "
        f"{fmt_month(f.month)}.", "ok"))

    if k.get("test_n_total") and k.get("items_total"):
        share = k["test_n_total"] / k["items_total"] * 100
        out.append(Note(
            f"<b>Two KPIs rest on thin samples.</b> Test pass rate covers {k['test_n_total']:,} of "
            f"{k['items_total']:,} work items ({share:.0f}%), and RCA is populated on {k.get('rca_n', 0):,}. "
            f"Both are directionally useful; neither should be trended yet.", "ok"))

    out.append(Note(
        f"<b>Utilisation assumes {config.WORKING_HOURS_PER_DAY:.0f} hours per business day with no leave "
        f"calendar</b>, so it overstates any month containing holiday or absence.", "ok"))

    stale = [f_.name for f_ in ex.feeds if f_.days_old is not None and f_.days_old > 7]
    if stale:
        out.append(Note(
            "<b>Not every feed is current.</b> " + ", ".join(
                f"{f_.name} is {f_.days_old} days old" for f_ in ex.feeds
                if f_.days_old is not None and f_.days_old > 7) +
            ". Cross-checks between feeds of different vintages are approximate.", "warn"))
    else:
        out.append(Note(
            "<b>All three feeds are current</b> — " + " · ".join(
                f"{f_.name} {f_.days_old}d" for f_ in ex.feeds if f_.days_old is not None) +
            " — so cross-checks between them are sound.", "ok"))

    out.append(Note(
        "<b>Zoho Print is still absent.</b> No export supplied and no definition of what it should "
        "contribute to the brief.", "warn"))
    return out
