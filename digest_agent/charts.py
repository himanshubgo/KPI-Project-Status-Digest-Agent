"""SVG chart builders.

Charts are plain inline SVG so the published page needs no charting library and
no network fetch. Colours come from CSS custom properties, so both themes are
handled by the same markup.
"""

from __future__ import annotations

from html import escape
from typing import Optional, Sequence

from .models import Series

X0, X1 = 48.0, 560.0
Y0, Y1 = 30.0, 240.0
LABEL_X = 568.0


def _xs(n: int) -> list[float]:
    if n <= 1:
        return [X0]
    step = (X1 - X0) / (n - 1)
    return [X0 + i * step for i in range(n)]


def _tick_labels(months: Sequence[str], n: int, want: int = 4) -> list[tuple[float, str]]:
    xs = _xs(n)
    if n <= want:
        idx = list(range(n))
    else:
        step = max(1, (n - 1) // (want - 1))
        idx = list(range(0, n - 1, step))
        if idx[-1] != n - 1:
            idx.append(n - 1)
        while len(idx) > want + 1:
            idx.pop(-2)
    return [(xs[i], months[i]) for i in idx]


def line_chart(months: Sequence[str], series: Sequence[Series], *,
               y_min: float, y_max: float, ticks: Sequence[float],
               median: Optional[float] = None, median_label: str = "",
               unit: str = "%", footnote: str = "", aria: str = "") -> str:
    n = len(months)
    xs = _xs(n)
    span = (y_max - y_min) or 1.0

    def y(v: float) -> float:
        return Y1 - (v - y_min) / span * (Y1 - Y0)

    parts = [f'<svg viewBox="0 0 660 300" role="img" aria-label="{escape(aria)}">']

    grid = [t for t in ticks if t > y_min]
    parts.append('<g stroke="var(--rule-soft)" stroke-width="1">')
    for t in grid:
        parts.append(f'<line x1="{X0}" y1="{y(t):.1f}" x2="{X1}" y2="{y(t):.1f}"></line>')
    parts.append("</g>")
    parts.append(f'<line x1="{X0}" y1="{Y1}" x2="{X1}" y2="{Y1}" stroke="var(--rule)" stroke-width="1"></line>')

    parts.append('<g font-family="IBM Plex Mono, monospace" font-size="10" fill="var(--muted)" text-anchor="end">')
    for t in ticks:
        parts.append(f'<text x="{X0 - 8}" y="{y(t) + 3.5:.1f}">{t:g}{unit}</text>')
    parts.append("</g>")

    if median is not None:
        parts.append(f'<line x1="{X0}" y1="{y(median):.1f}" x2="{X1}" y2="{y(median):.1f}" '
                     f'stroke="var(--muted)" stroke-width="1" stroke-dasharray="4 4"></line>')
        parts.append(f'<text x="{X0 + 4}" y="{y(median) - 5:.1f}" font-family="IBM Plex Mono, monospace" '
                     f'font-size="9" fill="var(--muted)">{escape(median_label)}</text>')

    # lines first, then markers, so markers sit on top of every stroke
    for s in reversed(list(series)):
        pts = " ".join(f"{xs[i]:.1f},{y(v):.1f}" for i, v in enumerate(s.values) if v is not None)
        if pts:
            parts.append(f'<polyline fill="none" stroke="var(--{s.colour_slot})" stroke-width="2" '
                         f'stroke-linejoin="round" stroke-linecap="round" points="{pts}"></polyline>')
    for s in reversed(list(series)):
        parts.append(f'<g fill="var(--{s.colour_slot})" stroke="var(--surface)" stroke-width="2">')
        for i, v in enumerate(s.values):
            if v is not None:
                parts.append(f'<circle cx="{xs[i]:.1f}" cy="{y(v):.1f}" r="4"></circle>')
        parts.append("</g>")

    # direct label on each series' final point
    for s in series:
        last = next(((i, v) for i, v in reversed(list(enumerate(s.values))) if v is not None), None)
        if last:
            i, v = last
            parts.append(f'<text x="{LABEL_X}" y="{y(v) + 3.5:.1f}" font-family="IBM Plex Mono, monospace" '
                         f'font-size="10" fill="var(--ink)">{v:g}{unit} {escape(s.label)}</text>')

    parts.append('<g font-family="IBM Plex Mono, monospace" font-size="10" fill="var(--muted)" text-anchor="middle">')
    for x, lab in _tick_labels(months, n):
        parts.append(f'<text x="{x:.1f}" y="260">{escape(lab)}</text>')
    parts.append("</g>")
    if footnote:
        parts.append(f'<text x="{X0}" y="282" font-family="IBM Plex Mono, monospace" font-size="9" '
                     f'fill="var(--muted)">{escape(footnote)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def bar_chart(months: Sequence[str], values: Sequence[float], *, split: int = 0,
              split_label: str = "", aria: str = "", caption: str = "") -> str:
    """Monthly volume. Bars before `split` are drawn in the muted tone."""
    n = len(values)
    top = max(values) if values else 1
    y_max = (int(top / 50) + 1) * 50
    bx0, bx1, by0, by1 = 48.0, 686.0, 33.0, 250.0
    slot = (bx1 - bx0) / n
    bw = min(26.0, slot * 0.78)

    def y(v):
        return by1 - v / y_max * (by1 - by0)

    parts = [f'<svg viewBox="0 0 700 296" role="img" aria-label="{escape(aria)}">']
    ticks = [t for t in range(0, y_max + 1, 50)]
    parts.append('<g stroke="var(--rule-soft)" stroke-width="1">')
    for t in ticks[1:]:
        parts.append(f'<line x1="{bx0}" y1="{y(t):.1f}" x2="{bx1}" y2="{y(t):.1f}"></line>')
    parts.append("</g>")
    parts.append(f'<line x1="{bx0}" y1="{by1}" x2="{bx1}" y2="{by1}" stroke="var(--rule)" stroke-width="1"></line>')
    parts.append('<g font-family="IBM Plex Mono, monospace" font-size="10" fill="var(--muted)" text-anchor="end">')
    for t in ticks:
        parts.append(f'<text x="{bx0 - 8}" y="{y(t) + 3.5:.1f}">{t}</text>')
    parts.append("</g>")

    for i, v in enumerate(values):
        x = bx0 + i * slot + (slot - bw) / 2
        fill = "var(--accent)" if i >= split else "var(--accent-mid)"
        parts.append(f'<rect x="{x:.1f}" y="{y(v):.1f}" width="{bw:.1f}" height="{by1 - y(v):.1f}" '
                     f'rx="3" fill="{fill}"></rect>')

    if 0 < split < n:
        sx = bx0 + split * slot - (slot - bw) / 2
        parts.append(f'<line x1="{sx:.1f}" y1="{by0 + 7}" x2="{sx:.1f}" y2="{by1}" stroke="var(--critical)" '
                     f'stroke-width="1" stroke-dasharray="3 3"></line>')
        parts.append(f'<text x="{sx - 5:.1f}" y="{by0 + 29}" font-family="IBM Plex Mono, monospace" '
                     f'font-size="10" fill="var(--critical)" text-anchor="end">{escape(split_label)}</text>')

    peak = max(range(n), key=lambda i: values[i])
    for i in {peak, n - 1}:
        x = bx0 + i * slot + slot / 2
        parts.append(f'<text x="{x:.1f}" y="{y(values[i]) - 5:.1f}" font-family="IBM Plex Mono, monospace" '
                     f'font-size="10" fill="var(--ink)" text-anchor="middle" font-weight="500">{values[i]:g}</text>')

    parts.append('<g font-family="IBM Plex Mono, monospace" font-size="10" fill="var(--muted)" text-anchor="middle">')
    step = max(1, n // 6)
    for i in range(0, n, step):
        parts.append(f'<text x="{bx0 + i * slot + slot / 2:.1f}" y="268">{escape(months[i])}</text>')
    parts.append("</g>")
    if caption:
        parts.append(f'<text x="{bx0}" y="288" font-family="IBM Plex Mono, monospace" font-size="10" '
                     f'fill="var(--muted)">{escape(caption)}</text>')
    parts.append("</svg>")
    return "".join(parts)
