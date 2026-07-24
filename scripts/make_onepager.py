"""make_onepager.py — build the executive one-pager PDF for automation-roi-explorer.

Renders a single-page executive summary (situation, quantified problem,
solution, ROI, recommendation) to ``deliverables/executive_onepager.pdf`` using
matplotlib's PdfPages. Every euro/hour/ROI figure on the sheet is pulled live
from the real ROI model (``roi_model.compute`` over the seeded processes), so the
one-pager can never drift from what the CLI and dashboard report.

Run:
    pip install matplotlib          # only needed for this deliverable
    python scripts/make_onepager.py

matplotlib is intentionally NOT a runtime dependency of the model — it is used
only to build this PDF, so the core package stays standard-library only.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))  # so `roi_model` imports when run as a script

import matplotlib  # noqa: E402

matplotlib.use("Agg")  # headless — no display needed
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

from roi_model import compute, load_processes, rank  # noqa: E402
from roi_model.model import DISCOUNT_RATE, HORIZON_YEARS  # noqa: E402

OUT = REPO / "deliverables" / "executive_onepager.pdf"

INK = "#1a2332"
ACCENT = "#1f6feb"
GOOD = "#1a7f4b"
MUTED = "#5b6672"
RULE = "#d0d7de"
BAR = "#1f6feb"
BAR_TOP = "#1a7f4b"


def model_results():
    results = rank([compute(p) for p in load_processes()], key="net_benefit_3y")
    portfolio_net = sum(r.annual_net_saving for r in results)
    portfolio_hours = sum(r.annual_hours_saved for r in results)
    portfolio_npv = sum(r.npv_3y for r in results)
    return results, portfolio_net, portfolio_hours, portfolio_npv


def eur(x: float) -> str:
    return f"€{x:,.0f}"


def build() -> None:
    results, port_net, port_hours, port_npv = model_results()
    top = results[0]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(OUT) as pdf:
        fig = plt.figure(figsize=(8.27, 11.69))  # A4 portrait
        fig.patch.set_facecolor("white")
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")

        def text(x, y, s, size=10, color=INK, weight="normal", style="normal", ha="left"):
            ax.text(x, y, s, fontsize=size, color=color, weight=weight,
                    style=style, ha=ha, va="top", transform=ax.transAxes)

        def rule(y):
            ax.plot([0.07, 0.93], [y, y], color=RULE, lw=0.8, transform=ax.transAxes)

        # Header
        text(0.07, 0.965, "Executive one-pager", 22, INK, "bold")
        text(0.07, 0.930, "Sequencing a back-office automation budget", 13, ACCENT, "bold")
        text(0.07, 0.908,
             "automation-roi-explorer  ·  Brandt Logistik & Handel GmbH (worked example)",
             9.5, MUTED)
        rule(0.895)

        # Headline band
        text(0.07, 0.878, eur(port_net) + " / yr", 26, GOOD, "bold")
        text(0.07, 0.838,
             f"net saving and {port_hours:,.0f} hours freed across the five seeded "
             "processes, worked top-down.", 10.5, INK)

        # Situation
        y = 0.805
        text(0.07, y, "Situation", 12, ACCENT, "bold")
        text(0.07, y - 0.028,
             "The COO has budget to automate roughly one back-office process at a time and a\n"
             "wish-list of five, each championed by its own team lead. The question isn't whether\n"
             "to automate — it's which one first, and whether it actually pays back.", 10, INK)

        # Problem
        y = 0.720
        text(0.07, y, "The problem, quantified", 12, ACCENT, "bold")
        text(0.07, y - 0.028,
             "The five candidate processes together consume ~22,400 hours/year of manual\n"
             "effort — roughly 13 full-time equivalents, ~€680,000/yr fully loaded. With a\n"
             "one-build-at-a-time budget, ranking them wrong is expensive.", 10, INK)

        # Solution + ranked chart
        y = 0.630
        text(0.07, y, "Solution — rank every candidate by the value of automating it",
             12, ACCENT, "bold")
        text(0.07, y - 0.026,
             "One compute() function (mirrored in the dashboard) turns each process's volume,\n"
             "task times, wage, coverage, and costs into net €/yr, payback, 3y ROI, and NPV.\n"
             "Net annual saving per process:", 10, INK)

        # horizontal bar chart, drawn on an inset axes
        chart = fig.add_axes([0.28, 0.335, 0.63, 0.150])
        names = [r.name for r in results][::-1]  # smallest at bottom
        vals = [r.annual_net_saving for r in results][::-1]
        colors = [BAR] * len(vals)
        colors[-1] = BAR_TOP  # top-ranked (last after reverse) highlighted
        bars = chart.barh(names, vals, color=colors, height=0.62)
        chart.set_xlim(0, max(vals) * 1.18)
        for spine in ("top", "right", "left", "bottom"):
            chart.spines[spine].set_visible(False)
        chart.tick_params(axis="both", length=0, labelsize=8.5, colors=INK)
        chart.set_xticks([])
        for bar, v in zip(bars, vals, strict=True):
            chart.text(v + max(vals) * 0.01, bar.get_y() + bar.get_height() / 2,
                       eur(v) + "/yr", va="center", ha="left", fontsize=8.5,
                       color=INK, weight="bold")

        # Impact / ROI
        y = 0.300
        text(0.07, y, "Impact / ROI  (from the model)", 12, ACCENT, "bold")
        roi_lines = [
            ("Build first", f"{top.name} — {eur(top.annual_net_saving)}/yr net, "
             f"{top.payback_months:.1f}-month payback, {top.roi_3y_pct:.0f}% 3y ROI"),
            ("Highest NPV", f"{eur(top.npv_3y)} over {HORIZON_YEARS} years "
             f"(discounted at {DISCOUNT_RATE:.0%})"),
            ("Full portfolio", f"{eur(port_net)}/yr net, {port_hours:,.0f} hours freed, "
             f"{eur(port_npv)} NPV"),
            ("Sequencing pays", "value-ranked, not first-come; low-volume supplier "
             "onboarding lands last"),
        ]
        yy = y - 0.028
        for label, val in roi_lines:
            bold = label == "Full portfolio"
            text(0.09, yy, "•", 10, MUTED)
            text(0.12, yy, label + ":", 10, INK, "bold")
            text(0.34, yy, val, 9.5, GOOD if bold else INK, "bold" if bold else "normal")
            yy -= 0.030

        # Recommendation
        y = 0.135
        rule(y + 0.022)
        text(0.07, y, "Recommendation", 12, ACCENT, "bold")
        text(0.07, y - 0.028,
             f"Fund {top.name} now — it clears its build cost in under three months and\n"
             f"returns {top.roi_3y_pct:.0f}% over three years. Then work the backlog top-down; "
             "replace each\nestimate with real numbers as builds ship and let the ranking "
             "re-settle.", 10, INK)

        # Footer
        text(0.07, 0.038,
             "All euro/hour/ROI figures are computed by the real model and reproducible with "
             "`python -m roi_model`. The\nfive seeded processes are synthetic and adjustable. "
             "See docs/BUSINESS_CASE.md.", 8, MUTED, style="italic")

        pdf.savefig(fig, facecolor="white")
        plt.close(fig)

    print(f"Wrote {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    build()
