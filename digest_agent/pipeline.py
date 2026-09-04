"""One place that runs the whole thing, used by both the CLI and the web app."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from . import actions as actions_mod
from . import config, kpis, quality, render, sources, state
from .analysis import Facts, analyse
from .models import Action, Feed, Kpi, Note


@dataclass
class RunResult:
    run_date: date
    html: str
    feeds: list[Feed]
    kpis: list[Kpi]
    actions: list[Action]
    watch: list[Note]
    caveats: list[Note]
    facts: Facts
    changes: dict[str, str] = field(default_factory=dict)
    out_path: Optional[Path] = None

    @property
    def headline(self) -> list[Kpi]:
        return [k for k in self.kpis if k.severity == "crit"][:4]


def run(data_dir: Path | None = None, run_date: date | None = None,
        out_path: Path | None = None, *, track_state: bool = True) -> RunResult:
    run_date = run_date or config.today()
    ex = sources.load(data_dir or config.DATA_DIR, run_date)
    facts = analyse(ex, run_date)
    board = kpis.build(facts)
    acts = actions_mod.build(facts)
    watch = actions_mod.build_watch(facts)
    caveats = quality.build(facts, ex)

    previous = state.load() if track_state else {}
    html = render.render(facts, ex, board, acts, watch, caveats)
    changes = {a.id: state.change_note(a, previous) for a in acts}

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
    if track_state:
        state.save(acts)

    return RunResult(run_date=run_date, html=html, feeds=ex.feeds, kpis=board,
                     actions=acts, watch=watch, caveats=caveats, facts=facts,
                     changes=changes, out_path=out_path)
