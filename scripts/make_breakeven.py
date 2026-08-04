"""make_breakeven.py — build the break-even / margin-of-safety deliverable.

Writes two files for the top-ranked process (the one the model says to build
first), both drawn straight from the real ROI model so they can never drift from
the CLI:

    deliverables/breakeven_margins.csv   per-driver break-even table
    deliverables/breakeven_margins.svg   hand-drawn margin-of-safety chart

The SVG is built by string templating — NO plotting library, no third-party
runtime dependency, matching the rest of the project (the browser charts are
hand-drawn too). Output is deterministic: fixed seed data, no timestamps, no
RNG, so re-running produces byte-identical files.

Run:
    python scripts/make_breakeven.py

Honesty note: the bars are tolerances on the seeded (synthetic) assumptions —
how far each can move before the 3-year case stops paying — not probabilities.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))  # so `roi_model` imports when run as a script

from roi_model import break_even, compute, load_processes, rank  # noqa: E402
from roi_model.breakeven import BreakEvenRow  # noqa: E402
from roi_model.cli import _DRIVER_LABELS, _fmt_input  # noqa: E402

CSV_OUT = REPO / "deliverables" / "breakeven_margins.csv"
SVG_OUT = REPO / "deliverables" / "breakeven_margins.svg"

# Repo palette (shared with the executive one-pager).
INK = "#1a2332"
ACCENT = "#1f6feb"
MUTED = "#5b6672"
RULE = "#d0d7de"
SURFACE = "#ffffff"
ATTENTION = "#b45309"   # reserved status hue for the single most-fragile driver

# Chart geometry (px).
W = 940
PAD_L = 28
X_BAR = 196
BAR_FULL = 430
X_VAL = X_BAR + BAR_FULL + 16
Y0 = 118
ROW_H = 50
BAR_H = 20
AXIS_MAX = 250.0   # % headroom; bars beyond this are capped and labelled


def _top_process():
    """The process the model ranks first (highest 3-year net benefit)."""
    procs = load_processes()
    top_name = rank([compute(p) for p in procs], key="net_benefit_3y")[0].name
    return next(p for p in procs if p.name == top_name)


def _esc(text: str) -> str:
    """Escape the three characters that matter for SVG text content."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write_csv(proc, rows: list[BreakEvenRow]) -> None:
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")  # byte-identical across OSes
        writer.writerow([
            "process", "driver", "worsens_when", "base_value", "breakeven_value",
            "margin_abs", "margin_pct", "base_net_benefit_3y",
        ])
        for r in rows:
            worsens = "falls" if r.direction == "low" else "rises"
            be = "" if r.breakeven_value is None else f"{r.breakeven_value:.6g}"
            m_abs = "" if r.margin_abs is None else f"{r.margin_abs:.6g}"
            m_pct = "" if r.margin_pct is None else f"{r.margin_pct:.2f}"
            writer.writerow([
                proc.name, _DRIVER_LABELS[r.field], worsens,
                f"{r.base_value:.6g}", be, m_abs, m_pct, f"{r.base_net_3y:.2f}",
            ])


def _bar_width(pct: float) -> float:
    """Bar length in px, capped at the axis maximum."""
    return min(pct, AXIS_MAX) / AXIS_MAX * BAR_FULL


def write_svg(proc, rows: list[BreakEvenRow]) -> None:
    reachable = [r for r in rows if r.margin_pct is not None]
    n = len(rows)
    plot_bottom = Y0 + n * ROW_H
    height = plot_bottom + 96

    p: list[str] = []
    p.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" '
        f'viewBox="0 0 {W} {height}" font-family="Segoe UI, Helvetica, Arial, sans-serif">'
    )
    p.append(f'<rect width="{W}" height="{height}" fill="{SURFACE}"/>')

    # Header.
    p.append(f'<text x="{PAD_L}" y="44" font-size="21" font-weight="700" '
             f'fill="{INK}">Margin of safety &#8212; {_esc(proc.name)}</text>')
    p.append(f'<text x="{PAD_L}" y="70" font-size="12.5" fill="{MUTED}">'
             'How far each assumption can move before the 3-year case stops paying back. '
             'Longer bar = more headroom;</text>')
    p.append(f'<text x="{PAD_L}" y="88" font-size="12.5" fill="{MUTED}">'
             'the shortest bar is the assumption the decision is most fragile to. '
             f'Axis capped at {AXIS_MAX:.0f}%; longer bars labelled with the true value.</text>')

    # Gridlines + axis ticks (recessive, drawn behind the bars).
    for tick in (0, 50, 100, 150, 200, 250):
        x = X_BAR + tick / AXIS_MAX * BAR_FULL
        p.append(f'<line x1="{x:.1f}" y1="{Y0 - 8}" x2="{x:.1f}" y2="{plot_bottom + 2}" '
                 f'stroke="{RULE}" stroke-width="1"/>')
        label = f"{tick}%" if tick == 0 else f"{tick}"
        p.append(f'<text x="{x:.1f}" y="{plot_bottom + 20}" font-size="10.5" '
                 f'fill="{MUTED}" text-anchor="middle">{label}</text>')
    p.append(f'<text x="{X_BAR + BAR_FULL / 2:.1f}" y="{plot_bottom + 38}" font-size="10.5" '
             f'fill="{MUTED}" text-anchor="middle" font-style="italic">'
             'headroom before break-even (% of base value)</text>')

    # One row per driver, tightest margin first (rows already sorted that way).
    for i, r in enumerate(rows):
        row_top = Y0 + i * ROW_H
        bar_y = row_top + 8
        is_tightest = reachable and r is reachable[0]
        color = ATTENTION if is_tightest else ACCENT

        p.append(f'<text x="{PAD_L}" y="{row_top + 16}" font-size="12.5" '
                 f'font-weight="600" fill="{INK}">{_esc(_DRIVER_LABELS[r.field])}</text>')

        if r.margin_pct is None:
            p.append(f'<text x="{PAD_L}" y="{row_top + 32}" font-size="10.5" '
                     f'fill="{MUTED}">no break-even (survives to floor)</text>')
            p.append(f'<line x1="{X_BAR}" y1="{bar_y + BAR_H / 2}" x2="{X_BAR + BAR_FULL}" '
                     f'y2="{bar_y + BAR_H / 2}" stroke="{RULE}" stroke-width="1" '
                     'stroke-dasharray="3 4"/>')
            p.append(f'<text x="{X_VAL}" y="{bar_y + BAR_H / 2 + 4}" font-size="11.5" '
                     f'fill="{MUTED}">unbreakable on its own</text>')
            continue

        verb = "drop" if r.direction == "low" else "rise"
        base_txt = _fmt_input(r.field, r.base_value)
        be_txt = _fmt_input(r.field, r.breakeven_value)
        p.append(f'<text x="{PAD_L}" y="{row_top + 32}" font-size="10.5" '
                 f'fill="{MUTED}">{_esc(base_txt)} &#8594; {_esc(be_txt)}</text>')

        width = _bar_width(r.margin_pct)
        p.append(f'<rect x="{X_BAR}" y="{bar_y}" width="{width:.1f}" height="{BAR_H}" '
                 f'rx="3" fill="{color}"/>')
        if r.margin_pct > AXIS_MAX:  # capped: mark the clipped end
            tip = X_BAR + BAR_FULL
            p.append(f'<path d="M{tip - 8:.1f} {bar_y + 3} L{tip - 2:.1f} {bar_y + BAR_H / 2} '
                     f'L{tip - 8:.1f} {bar_y + BAR_H - 3}" fill="none" '
                     f'stroke="{SURFACE}" stroke-width="2"/>')

        value_txt = f"{r.margin_pct:,.0f}% {verb}"
        tag = "  ▲ tightest margin" if is_tightest else ""
        p.append(f'<text x="{X_VAL}" y="{bar_y + BAR_H / 2 + 4}" font-size="11.5" '
                 f'font-weight="{"700" if is_tightest else "400"}" '
                 f'fill="{ATTENTION if is_tightest else INK}">'
                 f'{_esc(value_txt)}{_esc(tag)}</text>')

    # Footer: the read + the honesty caveat.
    base = compute(proc)
    foot_y = plot_bottom + 60
    if reachable:
        t = reachable[0]
        move = "falls to" if t.direction == "low" else "rises to"
        read = (f"Read: most fragile to {_DRIVER_LABELS[t.field]} — the case breaks even "
                f"when it {move} {_fmt_input(t.field, t.breakeven_value)} "
                f"(a {t.margin_pct:,.0f}% move from {_fmt_input(t.field, t.base_value)}). "
                f"Base 3-year net benefit {base.net_benefit_3y:,.0f} EUR.")
        p.append(f'<text x="{PAD_L}" y="{foot_y}" font-size="11.5" font-weight="600" '
                 f'fill="{INK}">{_esc(read)}</text>')
    p.append(f'<text x="{PAD_L}" y="{foot_y + 20}" font-size="10.5" fill="{MUTED}">'
             'Margins are tolerances on synthetic, illustrative assumptions, not probabilities. '
             'Generated by the real ROI model &#8212; reproduce with '
             '`python -m roi_model --breakeven`.</text>')

    p.append('</svg>')
    SVG_OUT.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n" pins LF on every OS so the committed file is byte-identical.
    SVG_OUT.write_text("\n".join(p) + "\n", encoding="utf-8", newline="\n")


def build() -> None:
    proc = _top_process()
    rows = break_even(proc)
    write_csv(proc, rows)
    write_svg(proc, rows)
    print(f"Wrote {CSV_OUT.relative_to(REPO)}")
    print(f"Wrote {SVG_OUT.relative_to(REPO)}")


if __name__ == "__main__":
    build()
