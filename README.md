# Project Status Digest Agent

Reads the Zoho **Projects**, **Sprints/timesheet** and **Service Desk** exports from
`data/` and produces an executive delivery brief: a KPI board, two stream trend
charts, a ranked action list, and the data-quality caveats that qualify all of it.

## Run — web app

```
pip install pandas openpyxl flask
python run_webapp.py
```

Open <http://127.0.0.1:5000>, drop in any mix of exports, press **Run
assessment**. You get the brief plus a summary of which feed each sheet was
matched to. Binds to localhost only unless you pass `--host`.

Uploads and generated briefs are written to `runs/<id>/` — one folder per run,
removable from the result page. Add your logo per
[`webapp/static/LOGO.md`](webapp/static/LOGO.md).

## Run — command line

```
pip install pandas openpyxl
python -m digest_agent
```

Options:

| flag | meaning |
|---|---|
| `--date YYYY-MM-DD` | run as at a given date (default: today) — useful for reproducing a past brief |
| `--data PATH` | folder holding the exports (default `data/`) |
| `--out FILE` | output path (default `exec_brief_<date>.html`) |
| `--quiet` | suppress the console summary |

The console summary reports each feed's row count, the sheet actually used, its
age, and whether each action is new, changed or unchanged since the last run
(tracked in `state/last_run.json`).

## Dropping in new exports

Put the new files in `data/` (CLI) or upload them (web app). Nothing needs
renaming:

- **Every sheet in every uploaded file is identified by its column signature**
  (`config.SHEET_SIGNATURES`), never by filename or sheet name; the filename is
  only a tie-breaker. This matters — during the assessment the service desk
  export was replaced under a filename describing a *different date*, and its
  sheet was renamed in the same swap. The web app also sanitises uploaded
  filenames, so names cannot be relied on at all.
- **Only headers are read during discovery.** The timesheet workbook is 21MB
  and far too large to load speculatively.
- **Timestamps are parsed against a list of formats** (`sources.DATE_FORMATS`),
  because the exports mix `MM-DD-YYYY`, `DD/Mon/YYYY` and native datetimes.
- **`.csv` is accepted too**, treated as a single unnamed sheet.

If a feed can't be identified, the web app says which one is missing and shows a
table of every sheet it did see, with the closest-matching feed and how many
signature columns matched — so you can tell a wrong export from an incomplete
one.

## What to change when reviewing

Everything arguable lives in `config.py`:

- `TARGETS` — **the source exports define no KPI targets at all.** Every
  threshold there is a proposal pending sign-off, and the brief says so next to
  the board. Agreeing these is the single highest-value change.
- `STREAMS` — the two-stream split. There is no Scrum/Kanban field in the
  current data, so this is a Project Group split (project delivery vs
  maintenance).
- `COHORT_MATURITY_DAYS`, `DORMANT_DAYS`, `PACE_TOLERANCE_PCT`,
  `STALE_UNASSIGNED_DAYS` — measurement windows.
- `SERIES_COLOURS` — validated for colour-vision deficiency and contrast in
  both light and dark themes. Re-validate if changed.

## Two measurement decisions worth knowing

**Completion uses matured cohorts.** A month's items count only once that month
is at least 60 days old. Measured sooner, the newest month reads
catastrophically low purely because its work has not had time to close — August
2026 reads 50.9% raw against a true run rate near 96%.

**"Dormant" is only asserted where it can be.** Projects and timesheets join on
project name alone and match about 40% of the time, so for an unmatched project
the absence of logged hours is evidence of nothing. Those projects are reported
as unverified rather than dormant.

## Layout

```
digest_agent/
  config.py     thresholds, stream split, proposed targets, series colours
  sources.py    discovers + normalises the three feeds by column signature
  analysis.py   computes every fact the brief needs
  kpis.py       KPI tiles + severity against targets
  actions.py    action board + watch list (each gated on a trigger)
  quality.py    data-quality caveats
  charts.py     inline SVG line + bar charts
  render.py     assembles the brief HTML
  state.py      run-to-run change tracking
  pipeline.py   single run() used by both front ends
  cli.py        command-line entry point
webapp/
  app.py        Flask routes: upload, run, result, download, delete
  templates/    base / index / result
  static/       app.css, plus your logo (see static/LOGO.md)
run_webapp.py   starts the web app
runs/           one folder per web run: uploads, brief.html, summary.json
prototype/      superseded first-pass modules, kept for reference
```

Actions are **gated on measured conditions**, not templated: if the unowned
ticket queue clears, action 01 stops appearing. The same is true of every
caveat.

## Known gaps

- **No Zoho Print export exists.** Nothing in the brief reflects it, and the
  brief does not define what it should contribute.
- **The service desk export carries 136 tickets dated in the future**, 130 of
  them already marked Finished, plus 453 with a due date before their creation
  date. Future-dated rows are excluded and everything is anchored on the run
  date, but the export is not yet a trustworthy system of record. This is
  surfaced as an action, not silently patched.
- **No delivery channel is wired up.** The agent writes an HTML file; posting it
  to Slack or email is a decision for after the assessment.
