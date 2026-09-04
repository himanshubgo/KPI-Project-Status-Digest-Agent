"""Front end for the Zoho - KPI/Status Digest Agent.

A small local Flask app: drop in any mix of Zoho exports, run the agent, read
the brief. Deliberately local -- the agent is Python and has to execute, which
a static page cannot do.

    python run_webapp.py        # then open http://127.0.0.1:5000

Branding: whatever image sits at webapp/static/logo.(svg|png|jpg|webp) appears
twice -- as a normal image in this app's own page headers (index, summary),
and embedded as a self-contained data: URI in the generated brief's own
masthead, so the mark travels with the report wherever it's viewed or
downloaded. DIGEST_ORG_NAME supplies a text wordmark on the app's pages when
no image is set. Neither is bundled -- an organisation's logo is theirs to
supply, not something to reproduce from a screenshot.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import shutil
import traceback
import uuid
from datetime import date, datetime
from pathlib import Path

from flask import (Flask, Response, abort, jsonify, redirect, render_template,
                   request, url_for)
from werkzeug.utils import secure_filename

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from digest_agent import config, pipeline, sources  # noqa: E402

BASE = Path(__file__).resolve().parent
RUNS = BASE.parent / "runs"
ALLOWED = {".xlsx", ".xls", ".xlsm", ".csv"}
MAX_UPLOAD_MB = 250

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

ORG_NAME = os.environ.get("DIGEST_ORG_NAME", "")


def _logo_path() -> Path | None:
    for name in ("logo.svg", "logo.png", "logo.jpg", "logo.webp"):
        p = BASE / "static" / name
        if p.exists():
            return p
    return None


def _logo_url() -> str | None:
    """For pages rendered by this app (index, result) -- a normal static URL."""
    p = _logo_path()
    return url_for("static", filename=p.name) if p else None


def _logo_data_uri() -> str | None:
    """For the generated brief itself -- a self-contained data: URI, so the
    logo travels with the report wherever it ends up (downloaded, embedded, or
    later republished as a standalone artifact) with no link back to this
    server or its static folder."""
    p = _logo_path()
    if not p:
        return None
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode('ascii')}"


@app.context_processor
def inject_branding():
    return {"org_name": ORG_NAME, "logo_url": _logo_url(),
            "max_upload_mb": MAX_UPLOAD_MB,
            "allowed_ext": ", ".join(sorted(ALLOWED))}


def _brand_brief(html: str) -> str:
    """Embed the organisation's logo into the report's own masthead. Applied
    to every rendering of the brief (in-app, embedded, downloaded) so the
    brand is part of the document itself, not just this app's chrome."""
    uri = _logo_data_uri()
    marker = '<header class="masthead">'
    if not uri or marker not in html:
        return html
    style = ('<style>.sheet{position:relative}.brandmark-logo{position:absolute;'
             'top:2.5rem;right:1.5rem;max-height:2.6rem;max-width:11rem;'
             'object-fit:contain}@media (max-width:40rem){.brandmark-logo{display:none}}'
             '</style>')
    img = f'<img class="brandmark-logo" src="{uri}" alt="{ORG_NAME or "Organisation"} logo">'
    return html.replace(marker, style + img + marker, 1)


def _inject_toolbar(html: str, run_id: str) -> str:
    """Overlay the in-app toolbar (Run another / Delete run) onto a generated
    brief. Used only for the page opened inside this app -- the downloaded
    copy and the iframe preview on the summary page stay the plain, portable
    report render.py wrote, with no links back into this server."""
    bar = render_template("_toolbar.html", run_id=run_id)
    marker = '<div class="sheet">'
    if marker not in html:
        return bar + html
    return html.replace(marker, bar + marker, 1)


def _run_dir(run_id: str) -> Path:
    """Resolve a run directory, refusing anything that escapes RUNS."""
    if not run_id or any(c in run_id for c in "/\\.") or len(run_id) > 40:
        abort(404)
    path = (RUNS / run_id).resolve()
    if not str(path).startswith(str(RUNS.resolve())) or not path.is_dir():
        abort(404)
    return path


@app.get("/")
def index():
    recent = []
    if RUNS.exists():
        for d in sorted(RUNS.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:6]:
            meta = d / "summary.json"
            if not meta.exists():
                continue
            try:
                s = json.loads(meta.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            recent.append({"id": d.name, "when": s.get("generated", ""),
                           "as_of": s.get("as_of", ""),
                           "actions": s.get("counts", {}).get("actions", 0),
                           "crit": s.get("counts", {}).get("crit", 0)})
    return render_template("index.html", recent=recent, today=date.today().isoformat())


@app.post("/run")
def run():
    files = [f for f in request.files.getlist("files") if f and f.filename]
    if not files:
        return jsonify(error="No files received. Add at least one export."), 400

    rejected = [f.filename for f in files if Path(f.filename).suffix.lower() not in ALLOWED]
    if rejected:
        return jsonify(error=f"Unsupported file type: {', '.join(rejected)}. "
                             f"Accepted: {', '.join(sorted(ALLOWED))}."), 400

    run_id = uuid.uuid4().hex[:12]
    work = RUNS / run_id
    (work / "data").mkdir(parents=True, exist_ok=True)

    saved = []
    for f in files:
        name = secure_filename(f.filename) or f"upload_{len(saved)}.xlsx"
        f.save(work / "data" / name)
        saved.append(name)

    raw_date = (request.form.get("as_of") or "").strip()
    try:
        run_date = date.fromisoformat(raw_date) if raw_date else date.today()
    except ValueError:
        run_date = date.today()

    try:
        res = pipeline.run(work / "data", run_date, work / "brief.html", track_state=False)
    except sources.FeedNotFound as exc:
        found = _describe(work / "data")
        shutil.rmtree(work, ignore_errors=True)
        missing = str(exc)
        label = {"projects": "Zoho Projects", "timesheet": "Zoho Sprints / timesheet",
                 "tickets": "Zoho Service Desk"}.get(missing, missing)
        return jsonify(
            error=f"Couldn't find the {label} export among the files you uploaded.",
            detail=("Sheets are identified by their column names, not filenames, so a renamed "
                    "file is fine — but the columns have to be there."),
            found=found), 422
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        app.logger.error(traceback.format_exc())
        return jsonify(error="The agent failed while reading those files.",
                       detail="Full traceback is in the server console."), 500

    # The summary is persisted now rather than recomputed when the page is
    # opened: re-running the agent to redraw a header would cost another minute.
    (work / "summary.json").write_text(json.dumps(_summary(res, saved), default=str, indent=1),
                                       encoding="utf-8")
    return jsonify(ok=True, redirect=url_for("brief", run_id=run_id))


def _summary(res: pipeline.RunResult, uploads: list[str]) -> dict:
    return {
        "as_of": res.run_date.isoformat(),
        "generated": datetime.now().strftime("%d %b %Y, %H:%M"),
        "uploads": uploads,
        "feeds": [{"name": f.name, "rows": f.rows, "sheet": f.sheet, "file": f.path_name,
                   "as_of": f.as_of.isoformat() if f.as_of else None,
                   "days_old": f.days_old, "freshness": f.freshness} for f in res.feeds],
        "kpis": [{"label": k.label, "display": k.display, "context": k.context,
                  "badge": k.badge, "severity": k.severity} for k in res.kpis],
        "actions": [{"rank": a.rank, "band": a.band, "title": a.title, "owner": a.owner,
                     "owner_vacant": a.owner_vacant, "due": a.due,
                     "severity": a.severity, "change": res.changes.get(a.id, "")}
                    for a in res.actions],
        "counts": {"kpis": len(res.kpis), "actions": len(res.actions),
                   "watch": len(res.watch), "caveats": len(res.caveats),
                   "crit": sum(1 for k in res.kpis if k.severity == "crit")},
    }


def _describe(data_dir: Path) -> list[dict]:
    """What the agent actually saw -- shown when a feed can't be identified."""
    out = []
    for c in sources._candidates(data_dir):
        scores = {feed: len(sig & c.columns) for feed, sig in config.SHEET_SIGNATURES.items()}
        best = max(scores, key=scores.get)
        out.append({"file": c.path.name, "sheet": c.sheet or "(csv)",
                    "columns": len(c.columns),
                    "closest": best if scores[best] else "—",
                    "score": scores[best]})
    return out


@app.get("/runs/<run_id>")
def result(run_id: str):
    work = _run_dir(run_id)
    if not (work / "brief.html").exists() or not (work / "summary.json").exists():
        abort(404)
    summary = json.loads((work / "summary.json").read_text(encoding="utf-8"))
    return render_template("result.html", run_id=run_id, s=summary)


@app.get("/runs/<run_id>/brief")
def brief(run_id: str):
    work = _run_dir(run_id)
    path = work / "brief.html"
    if not path.exists():
        abort(404)
    html = _brand_brief(path.read_text(encoding="utf-8"))
    # ?embed=1 is used by the summary page's iframe preview: a fixed toolbar
    # pinned to the top of a small embedded frame would sit on top of the
    # report rather than above it, so the embed gets the branded page without
    # the toolbar rather than without the logo too.
    if request.args.get("embed"):
        return Response(html, mimetype="text/html")
    return Response(_inject_toolbar(html, run_id), mimetype="text/html")


@app.get("/runs/<run_id>/download")
def download(run_id: str):
    work = _run_dir(run_id)
    branded = _brand_brief((work / "brief.html").read_text(encoding="utf-8"))
    return Response(branded, mimetype="text/html", headers={
        "Content-Disposition": f'attachment; filename="delivery_risk_brief_{run_id}.html"'})


@app.post("/runs/<run_id>/delete")
def delete(run_id: str):
    shutil.rmtree(_run_dir(run_id), ignore_errors=True)
    return redirect(url_for("index"))


@app.errorhandler(413)
def too_large(_):
    return jsonify(error=f"Those files exceed the {MAX_UPLOAD_MB}MB limit for a single run."), 413


if __name__ == "__main__":
    app.run(debug=True)
