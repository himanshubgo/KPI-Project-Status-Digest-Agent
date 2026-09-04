"""Assembles the executive brief as a self-contained HTML page."""

from __future__ import annotations

from html import escape
from typing import Sequence

import pandas as pd

from . import config
from .actions import BAND_LABELS, BAND_ORDER
from .analysis import Facts, fmt_month
from .charts import bar_chart, line_chart
from .models import Action, Kpi, Note, Series
from .sources import Exports

FONTS = ("https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800"
         "&family=IBM+Plex+Mono:wght@400;500;600&family=Public+Sans:wght@400;500;600;700&display=swap")

LIGHT_TOKENS = """
    --ground:#f6f5f2; --surface:#fffffe; --surface-2:#edece7;
    --ink:#15171a; --ink-2:#3c4148; --muted:#6b7178;
    --rule:#dedcd6; --rule-soft:#e9e7e2;
    --accent:#1c4a3a; --accent-soft:#e3ebe6; --accent-mid:#8fb3a3;
    --critical:#a3291f; --warn:#8a5c0a; --steady:#2f6a4f;
    --s1:%(l1)s; --s2:%(l2)s;""" % {"l1": config.SERIES_COLOURS["light"]["s1"],
                                    "l2": config.SERIES_COLOURS["light"]["s2"]}

DARK_TOKENS = """
    --ground:#0f1211; --surface:#171b19; --surface-2:#1f2422;
    --ink:#e9ece9; --ink-2:#bcc4bf; --muted:#8a938d;
    --rule:#2b322e; --rule-soft:#232927;
    --accent:#7bc0a2; --accent-soft:#172a22; --accent-mid:#3f6b57;
    --critical:#f0897d; --warn:#d9a441; --steady:#7bc0a2;
    --s1:%(d1)s; --s2:%(d2)s;""" % {"d1": config.SERIES_COLOURS["dark"]["s1"],
                                    "d2": config.SERIES_COLOURS["dark"]["s2"]}

CSS = """
:root {%(light)s
  --display:"Bricolage Grotesque","Helvetica Neue",Arial,sans-serif;
  --body:"Public Sans","Helvetica Neue",Arial,sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,Consolas,monospace; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {%(dark)s } }
:root[data-theme="dark"] {%(dark)s }
*{box-sizing:border-box}
body{background:var(--ground);color:var(--ink);font-family:var(--body);font-size:16px;
  line-height:1.55;-webkit-font-smoothing:antialiased}
.sheet{max-width:52rem;margin:0 auto;padding:2.5rem 1.5rem 4.5rem;display:flex;
  flex-direction:column;gap:2.25rem}
.masthead{display:flex;flex-direction:column;gap:.5rem}
.eyebrow{font-family:var(--mono);font-size:.68rem;letter-spacing:.15em;text-transform:uppercase;color:var(--muted)}
h1{font-family:var(--display);font-weight:800;font-size:clamp(2rem,5.5vw,2.85rem);line-height:1.02;
  letter-spacing:-.025em;margin:0}
.dateline{font-family:var(--mono);font-size:.73rem;color:var(--muted)}
.section-head{display:flex;flex-direction:column;gap:.2rem}
.section-head h2{font-family:var(--display);font-weight:800;font-size:1.3rem;letter-spacing:-.02em;margin:0}
.section-head p{margin:0;color:var(--muted);font-size:.88rem}
.stack-section{display:flex;flex-direction:column;gap:.8rem}
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(10.5rem,1fr));gap:.5rem}
.kpi{background:var(--surface);border:1px solid var(--rule);border-top:3px solid var(--steady);
  padding:.7rem .8rem .75rem;display:flex;flex-direction:column;gap:.18rem;min-width:0}
.kpi.warn{border-top-color:var(--warn)}
.kpi.crit{border-top-color:var(--critical)}
.k-label{font-family:var(--mono);font-size:.6rem;letter-spacing:.1em;text-transform:uppercase;
  color:var(--ink-2);line-height:1.3}
.k-val{font-family:var(--display);font-weight:800;font-size:1.7rem;line-height:1.05;
  letter-spacing:-.025em;font-variant-numeric:tabular-nums;color:var(--steady)}
.kpi.warn .k-val{color:var(--warn)}
.kpi.crit .k-val{color:var(--critical)}
.k-ctx{font-size:.74rem;color:var(--muted);line-height:1.35}
.k-badge{align-self:flex-start;margin-top:.2rem;font-family:var(--mono);font-size:.62rem;
  padding:.12rem .4rem .16rem;background:var(--accent-soft);color:var(--steady);white-space:nowrap;
  max-width:100%%;overflow:hidden;text-overflow:ellipsis}
.kpi.warn .k-badge{background:color-mix(in srgb,var(--warn) 12%%,transparent);color:var(--warn)}
.kpi.crit .k-badge{background:color-mix(in srgb,var(--critical) 12%%,transparent);color:var(--critical)}
.chart-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(20rem,1fr));gap:.8rem}
figure.chart{margin:0;background:var(--surface);border:1px solid var(--rule);
  padding:1.1rem 1.3rem 1rem;display:flex;flex-direction:column;gap:.45rem}
.chart-title{font-family:var(--display);font-weight:700;font-size:.98rem;letter-spacing:-.01em}
.chart-sub{font-size:.81rem;color:var(--muted)}
.chart-scroll{overflow-x:auto}
.chart-scroll svg{display:block;min-width:34rem;width:100%%;height:auto}
.legend{display:flex;gap:1rem;flex-wrap:wrap;font-family:var(--mono);font-size:.65rem;color:var(--muted)}
.legend span{display:inline-flex;align-items:center;gap:.35rem}
.swatch{width:.62rem;height:.62rem;display:inline-block}
.band{display:flex;flex-direction:column;gap:.8rem}
.band-head{display:flex;align-items:baseline;justify-content:space-between;gap:1rem;
  border-bottom:2px solid var(--ink);padding-bottom:.4rem;flex-wrap:wrap}
.band-head h2{font-family:var(--display);font-weight:800;font-size:1.3rem;letter-spacing:-.02em;margin:0}
.band-meta{font-family:var(--mono);font-size:.68rem;color:var(--muted);text-transform:uppercase;
  letter-spacing:.1em}
.action{background:var(--surface);border:1px solid var(--rule);border-left:4px solid var(--accent-mid);
  display:grid;grid-template-columns:2.9rem 1fr;min-width:0}
.action.crit{border-left-color:var(--critical)}
.action.warn{border-left-color:var(--warn)}
.a-num{font-family:var(--mono);font-size:.78rem;font-weight:600;color:var(--muted);
  padding:1rem 0 0;text-align:center;font-variant-numeric:tabular-nums}
.a-body{padding:.95rem 1.2rem 1.1rem 0;display:flex;flex-direction:column;gap:.6rem;min-width:0}
.a-body h3{font-family:var(--display);font-weight:700;font-size:1.1rem;line-height:1.22;
  letter-spacing:-.015em;margin:0;text-wrap:balance}
ul.chips{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:.28rem .3rem}
ul.chips>li{display:inline-flex;align-items:baseline;gap:.35rem;border:1px solid var(--rule);
  background:var(--ground);padding:.2rem .48rem .25rem}
.c-n{font-family:var(--display);font-weight:700;font-size:.87rem;font-variant-numeric:tabular-nums}
.c-n.crit{color:var(--critical)}
.c-n.warn{color:var(--warn)}
.c-n.ok{color:var(--steady)}
.c-l{font-family:var(--mono);font-size:.64rem;color:var(--muted);white-space:nowrap}
dl.meta{margin:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(11rem,1fr));
  gap:.5rem .9rem;border-top:1px solid var(--rule-soft);padding-top:.6rem}
dl.meta>div{display:flex;flex-direction:column;gap:.1rem;min-width:0}
dl.meta dt{font-family:var(--mono);font-size:.6rem;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}
dl.meta dd{margin:0;font-size:.85rem;font-weight:500;color:var(--ink);line-height:1.35}
dl.meta dd.vacant{color:var(--critical);font-weight:600}
.panel{background:var(--surface);border:1px solid var(--rule);padding:1.15rem 1.3rem 1.25rem;
  display:flex;flex-direction:column;gap:.75rem}
.panel h2{font-family:var(--display);font-weight:700;font-size:1.12rem;letter-spacing:-.015em;margin:0}
ul.lines{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:.6rem}
ul.lines>li{position:relative;padding-left:1.35rem;font-size:.9rem;color:var(--ink-2);line-height:1.5}
ul.lines>li::before{content:"";position:absolute;left:0;top:.5em;width:.45rem;height:.45rem;
  background:var(--accent-mid)}
ul.lines>li.crit::before{background:var(--critical)}
ul.lines>li.warn::before{background:var(--warn)}
ul.lines b{color:var(--ink);font-weight:600}
code{font-family:var(--mono);font-size:.84em;background:var(--surface-2);padding:.06em .32em;color:var(--ink-2)}
footer{border-top:1px solid var(--rule);padding-top:1rem;font-family:var(--mono);font-size:.68rem;
  line-height:1.75;color:var(--muted)}
@media (max-width:36rem){
  .action{grid-template-columns:1fr}
  .a-num{text-align:left;padding:.7rem 1rem 0}
  .a-body{padding:.5rem 1rem 1rem}
  .sheet{padding:2rem 1rem 3.5rem}}
""" % {"light": LIGHT_TOKENS, "dark": DARK_TOKENS}


def _kpi_tiles(kpis: Sequence[Kpi]) -> str:
    out = []
    for k in kpis:
        cls = "" if k.severity == "ok" else f" {k.severity}"
        out.append(
            f'<div class="kpi{cls}"><span class="k-label">{escape(k.label)}</span>'
            f'<span class="k-val">{escape(k.display)}</span>'
            f'<span class="k-ctx">{escape(k.context)}</span>'
            f'<span class="k-badge">{escape(k.badge)}</span></div>')
    return f'<div class="kpi-grid">{"".join(out)}</div>'


def _action(a: Action) -> str:
    chips = "".join(
        f'<li><span class="c-n {c.severity}">{escape(c.value)}</span>'
        f'<span class="c-l">{escape(c.label)}</span></li>' for c in a.chips)
    owner_cls = ' class="vacant"' if a.owner_vacant else ""
    return (
        f'<article class="action {a.severity}"><div class="a-num">{a.rank:02d}</div>'
        f'<div class="a-body"><h3>{escape(a.title)}</h3>'
        f'<ul class="chips">{chips}</ul>'
        f'<dl class="meta">'
        f'<div><dt>Owner</dt><dd{owner_cls}>{escape(a.owner)}</dd></div>'
        f'<div><dt>By</dt><dd>{escape(a.due)}</dd></div>'
        f'<div><dt>Do</dt><dd>{escape(a.do)}</dd></div>'
        f'<div><dt>Effect</dt><dd>{escape(a.effect)}</dd></div>'
        f'</dl></div></article>')


def _notes(notes: Sequence[Note]) -> str:
    return "".join(f'<li class="{n.severity}">{n.text}</li>' for n in notes)


def _legend(labels: Sequence[str]) -> str:
    slots = ["s1", "s2"]
    parts = [f'<span><i class="swatch" style="background: var(--{slots[i]})"></i> {escape(l)}</span>'
             for i, l in enumerate(labels)]
    parts.append("<span>— — 12-mo median</span>")
    return f'<div class="legend">{"".join(parts)}</div>'


def _demand_window(f: Facts, back: int = 20):
    months = [f.month - i for i in range(back - 1, -1, -1)]
    values = [int(f.demand.get(m, 0)) for m in months]
    split = 0
    for i in range(3, len(values)):
        base = sorted(values[:i])[len(values[:i]) // 2]
        if base and values[i] > 2 * base:
            split = i
            break
    return [m.strftime("%b'%y") for m in months], values, split


def render(f: Facts, ex: Exports, kpis: Sequence[Kpi], actions: Sequence[Action],
           watch: Sequence[Note], caveats: Sequence[Note]) -> str:
    month_labels = [m.strftime("%b'%y") for m in f.months]
    comp_labels = [m.strftime("%b'%y") for m in f.completion_months]

    bug_series = [Series(l, v, s) for (l, v), s in zip(f.bug_rate.items(), ["s1", "s2"])]
    comp_series = [Series(l, v, s) for (l, v), s in zip(f.completion.items(), ["s1", "s2"])]

    bug_vals = [v for s in bug_series for v in s.values if v is not None]
    bug_max = max(90.0, (int(max(bug_vals) / 10) + 1) * 10) if bug_vals else 90.0
    comp_vals = [v for s in comp_series for v in s.values if v is not None]
    comp_min = min(70.0, (int(min(comp_vals) / 10)) * 10) if comp_vals else 70.0

    bug_svg = line_chart(
        month_labels, bug_series, y_min=0, y_max=bug_max,
        ticks=[0, 20, 40, 60, 80], median=f.bug_median,
        median_label=f"12-mo median {f.bug_median}%",
        aria=("Bug rate by month for each stream. " +
              "; ".join(f"{s.label} ranges "
                        f"{min(v for v in s.values if v is not None):.0f} to "
                        f"{max(v for v in s.values if v is not None):.0f} percent"
                        for s in bug_series if any(v is not None for v in s.values))))
    comp_svg = line_chart(
        comp_labels, comp_series, y_min=comp_min, y_max=100,
        ticks=[t for t in (70, 80, 90, 100) if t >= comp_min],
        median=f.completion_median, median_label=f"12-mo median {f.completion_median}%",
        footnote=f"Axis starts at {comp_min:g}%. Ends {fmt_month(f.completion_months[-1]) if f.completion_months else ''}"
                 f" — later cohorts not yet mature.",
        aria="Work item completion rate by creation month for cohorts at least "
             f"{config.COHORT_MATURITY_DAYS} days old, by stream.")

    dm, dv, split = _demand_window(f)
    growth = ""
    if split:
        pre = sum(dv[:split]) / split
        post = sum(dv[split:]) / (len(dv) - split)
        growth = (f"Before {dm[split]} — avg {pre:.0f}/mo · since — avg {post:.0f}/mo "
                  f"({post / pre:.1f}× on the same {f.technicians} technicians)")
    demand_svg = bar_chart(dm, dv, split=split, split_label=f"{dm[split]} — intake steps up" if split else "",
                           caption="Tickets created per month",
                           aria="Monthly ticket volume showing a step change in intake.")

    bands = []
    for band in BAND_ORDER:
        items = [a for a in actions if a.band == band]
        if not items:
            continue
        due = items[0].due
        inner = "".join(_action(a) for a in items)
        if band == "week":
            inner += (f'<figure class="chart"><figcaption>'
                      f'<span class="chart-title">Intake stepped up; headcount did not</span>'
                      f'<span class="chart-sub">{escape(growth)}</span></figcaption>'
                      f'<div class="chart-scroll">{demand_svg}</div></figure>')
        bands.append(
            f'<section class="band"><div class="band-head"><h2>{BAND_LABELS[band]}</h2>'
            f'<span class="band-meta">{len(items)} action{"s" if len(items) != 1 else ""} · by {escape(due)}</span>'
            f'</div>{inner}</section>')

    feed_line = " · ".join(
        f"{fd.name}, {fd.as_of:%d %b %Y} ({fd.rows:,} rows)" if fd.as_of else f"{fd.name} (undated)"
        for fd in ex.feeds)
    # `fd.days_old or 99` would be wrong: a feed refreshed today has days_old == 0,
    # which is falsy, and would be read as 99 days stale.
    ages = [99 if fd.days_old is None else fd.days_old for fd in ex.feeds]
    fresh = (f"all {len(ex.feeds)} feeds current" if all(a <= 7 for a in ages)
             else " · ".join(f"{fd.name} {fd.days_old}d" for fd in ex.feeds if fd.days_old is not None))

    return f"""<title>Delivery Risk Brief</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}">
<style>{CSS}</style>
<div class="sheet">
  <header class="masthead">
    <div class="eyebrow">Executive brief · DevOps &amp; Data Visualization</div>
    <h1>Delivery Risk Brief</h1>
    <div class="dateline">{f.run:%d %B %Y} · {len(kpis)} KPIs · {len(actions)} actions · {escape(fresh)}</div>
  </header>

  <section class="stack-section" aria-label="Operating KPIs">
    <div class="section-head"><h2>Operating KPIs</h2>
      <p>{fmt_month(f.month)}, the last complete month. {len(kpis)} measures the current exports actually
         support. Thresholds are proposals — the source defines none.</p></div>
    {_kpi_tiles(kpis)}
  </section>

  <section class="stack-section" aria-label="Trends">
    <div class="section-head"><h2>Where the two streams diverge</h2>
      <p>{" against ".join(config.STREAMS)} — the only two streams the data can separate.</p></div>
    <div class="chart-grid">
      <figure class="chart"><figcaption>
        <span class="chart-title">Bug rate by stream</span>
        <span class="chart-sub">Bugs as a share of items raised each month.</span></figcaption>
        <div class="chart-scroll">{bug_svg}</div>
        {_legend(list(f.bug_rate))}
      </figure>
      <figure class="chart"><figcaption>
        <span class="chart-title">Completion by stream</span>
        <span class="chart-sub">Share of each month's items now closed, cohorts matured {config.COHORT_MATURITY_DAYS} days.</span></figcaption>
        <div class="chart-scroll">{comp_svg}</div>
        {_legend(list(f.completion))}
      </figure>
    </div>
  </section>

  {"".join(bands)}

  <section class="panel">
    <h2>Watch, don't act yet</h2>
    <ul class="lines">{_notes(watch)}</ul>
  </section>

  <section class="panel">
    <h2>Confidence in this brief</h2>
    <ul class="lines">{_notes(caveats)}</ul>
  </section>

  <footer>
    Sources — {escape(feed_line)}<br>
    Actions, priority order and KPI thresholds are model-generated from these exports ·
    generated {f.run:%d %b %Y} by digest_agent
  </footer>
</div>
"""
