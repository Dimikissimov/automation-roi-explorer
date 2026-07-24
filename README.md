# Automation ROI Explorer

**Should we automate this process? Put a number on it — live.**

![Python](https://img.shields.io/badge/python-3.10%20%7C%203.12-3776AB?logo=python&logoColor=white)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![No dependencies](https://img.shields.io/badge/deps-none%20(stdlib%20only)-blueviolet)
![Offline](https://img.shields.io/badge/dashboard-offline%20%C2%B7%20no%20CDN-informational)

> Every back-office team has a queue of manual processes and a finite budget to
> automate them. The real question is never *"can we automate this?"* but
> *"which one first, and is it worth it?"* This tool answers that quantitatively —
> hours saved, euros saved, payback period, and 3-year ROI for each candidate —
> so the automation backlog is ranked by business value, not by whoever shouts loudest.

It has **two halves that share one calculation model**: a dependency-free Python
package with a CLI, and an interactive browser dashboard that mirrors the exact same
math so you can drag a slider and watch the business case move.

---

## Run in 30 seconds

**The dashboard** (no install, no server, no internet):

```
# just open the file in any browser
web/index.html
```

Double-click `web/index.html` (or `start web/index.html` on Windows /
`open web/index.html` on macOS). Adjust any process's sliders — annual volume,
minutes per task, wage, coverage, build and running cost — and the KPIs, charts,
and ranked backlog recompute instantly. Fully offline, zero dependencies, no CDN.

**The CLI** (standard-library Python, nothing to `pip install`):

```
python -m roi_model                       # ranked backlog from the seed data
python -m roi_model --sort payback_months # rank by fastest payback instead
python -m roi_model --csv my_processes.csv
python -m roi_model --export-json out.json --export-csv out.csv
```

Example output:

```
Automation backlog — ranked by net_benefit_3y (5 processes)

Process                         Hrs/yr    Net EUR/yr   Payback mo    3y ROI %        NPV 3y
-------------------------------------------------------------------------------------------
Invoice matching (3-way)         5,950       171,300          2.8       769.3       401,457
RFQ email triage                 2,800        84,800          3.5       582.2       193,538
Returns processing               2,700        72,900          4.9       408.4       157,870
Product-data cleanup             1,350        34,800          6.2       320.0        71,683
Supplier onboarding                660        19,500         13.5       111.3        28,253

Portfolio total: 13,460 hours/yr, 383,300 EUR/yr net saving
```

Run the tests:

```
pip install pytest ruff   # dev tooling only
pytest -q
ruff check .
```

---

## Screenshot

![Dashboard screenshot placeholder — sliders on the left, KPI tiles across the top, a "net € saved per process" bar chart, a payback chart, and a sortable automation-backlog table](docs/screenshot.png)

*(Placeholder — open `web/index.html` to see it live.)*

---

## What it demonstrates

- **Data modelling** — a clean, typed domain model (`ProcessInput` → `ProcessResult`)
  with the ROI math isolated in one pure function, easy to test and reason about.
- **Business / ROI analysis** — payback, net benefit, ROI %, and discounted NPV over a
  3-year horizon: the numbers a team actually uses to sequence an automation backlog.
- **Interactive data-viz from scratch** — bar and payback charts drawn by hand on the
  HTML Canvas (no Chart.js, no D3, no CDN), with tooltips, live recompute, a sortable
  table, and light/dark theming.
- **One model, two front ends, kept in sync** — the JavaScript `compute()` mirrors the
  Python `compute()` line for line, so the dashboard and the CLI never disagree.
- **Testing & tooling** — a `pytest` suite with hand-computable fixtures and edge cases,
  `ruff` linting, and a GitHub Actions matrix (3.10 / 3.12) that also smoke-tests the CLI
  and validates the JSON/CSV exports.

---

## Limitations & assumptions (read before trusting a number)

The model is deliberately simple and **every assumption is explicit and adjustable** —
that is the point, not a shortcut:

- **Synthetic data.** The five seeded processes and all their figures are illustrative,
  not from any real company. Replace them with your own estimates before deciding anything.
- **Labour value = time × wage.** It assumes freed hours convert to real savings
  (redeployed staff, avoided hires, or reduced overtime). If freed time just disappears,
  the "saving" is soft — treat it as capacity, not cash.
- **Steady state.** Volumes, wages, and per-task times are held constant across the
  3-year horizon; no ramp-up, seasonality, or volume growth is modelled.
- **Coverage is a single number.** Real automations handle a messy long tail; `coverage`
  is your honest estimate of the share of volume the automation truly handles end-to-end.
- **Costs are estimates.** Build and running costs exclude change-management, risk, and
  the maintenance tail. NPV uses a flat 8% discount rate (edit `DISCOUNT_RATE`).
- **No option value or dependencies.** Processes are scored independently; the tool does
  not model shared platform costs or one automation unlocking another.

Use it to *structure and compare* the decision, then apply judgement.

---

## Project layout

```
roi_model/            # stdlib-only Python package (the calculation model)
  model.py            #   ROI math: compute(), rank(), dataclasses
  data_load.py        #   CSV loader
  cli.py              #   python -m roi_model — ranked table + CSV/JSON export
  data/processes.csv  #   seeded B2B-distribution processes
web/index.html        # offline interactive dashboard (mirrors the Python math)
tests/                # pytest suite
.github/workflows/    # CI: ruff + pytest (3.10 & 3.12) + CLI + export validation
```

---

## About this project — Dimitres Kisimov

Built to show the **analytical, decision-support side** of a Data & AI automation role:
not just building automations, but quantifying *which* ones are worth building.

It maps directly onto the Würth **"Data & AI — (Agentic) Automation with Low-code
Platforms"** brief — and equally onto a **Data & AI Analytics** role: interactive
dashboards, KPI design, and decision support that turns raw process assumptions into a
ranked, defensible business case.

Skills on show:

- Translating a fuzzy business question ("what should we automate?") into an explicit,
  testable model.
- Financial literacy: payback, ROI, and discounted NPV done correctly and transparently.
- From-scratch interactive data visualisation (Canvas, no libraries) and clean KPI/dashboard UX.
- Disciplined engineering: pure functions, typed data, a real test suite, linting, and CI.
- Honest communication of assumptions and limitations.

**License:** MIT © 2026 Dimitres Kisimov · **Data:** synthetic (see [CREDITS.md](CREDITS.md)).
