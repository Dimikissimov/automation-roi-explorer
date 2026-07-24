# Automation ROI Explorer

![CI](https://github.com/Dimitres-Kisimov/automation-roi-explorer/actions/workflows/ci.yml/badge.svg)

Every back-office team has a queue of manual processes they could automate and not enough budget to do all of them. The interesting question isn't "can we automate this" — it's "which one first, and is it actually worth it?" This tool puts numbers on that: hours saved, euros saved, payback period, and 3-year ROI for each candidate, so the backlog gets ranked by value instead of by whoever asked loudest.

I built it for the analytics side of the automation roles I've been applying to. Anyone can wire up an automation; being able to argue *which* one to build first, with the math shown, felt like the more useful thing to demonstrate.

There are two halves and they share one calculation. A stdlib-only Python package with a CLI, and a browser dashboard that runs the same math so you can drag a slider and watch the business case move in real time.

## The dashboard, and why the charts are hand-drawn

The dashboard is a single offline HTML file. Open it, adjust a process's sliders (volume, minutes per task, wage, coverage, build and running cost) and the KPIs, charts, and ranked backlog all recompute instantly. No server, no CDN, no internet.

The one decision I'm glad I made: the bar chart and the payback chart are drawn by hand on a `<canvas>` element. I could have pulled in Chart.js or D3, but that's a dependency, a CDN request, and a chunk of the "offline" promise gone. Drawing the bars, axes, tooltips, and the light/dark theming myself was more code, but the whole thing stays a single file you can double-click. The JavaScript `compute()` mirrors the Python `compute()` line for line, which is what keeps the dashboard and the CLI from ever disagreeing.

## Running it

The dashboard needs nothing installed — just open `web/index.html` (`start web/index.html` on Windows, `open web/index.html` on macOS).

The CLI is standard-library Python:

```
python -m roi_model                       # ranked backlog from the seed data
python -m roi_model --sort payback_months # rank by fastest payback
python -m roi_model --csv my_processes.csv
python -m roi_model --export-json out.json --export-csv out.csv
```

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

Tests:

```
pip install pytest ruff
pytest -q
ruff check .
```

## Read this before trusting a number

The model is intentionally simple, and every assumption is out in the open and adjustable — that's the design, not a corner cut.

- The five seeded processes and their figures are synthetic. Swap in your own before deciding anything.
- Savings assume freed hours turn into real money (redeployed staff, avoided hires, less overtime). If the freed time just evaporates, treat the "saving" as capacity, not cash.
- Volumes, wages, and per-task times are held flat across three years. No ramp-up or seasonality.
- `coverage` is a single number for the share of volume the automation truly handles end to end. Real automations have a messy tail; be honest here.
- Costs exclude change management, risk, and the maintenance tail. NPV uses a flat 8% discount rate (`DISCOUNT_RATE`).
- Processes are scored independently — no shared platform costs, no one automation unlocking another.

Use it to structure and compare the decision, then apply judgement.

## Layout

```
roi_model/            stdlib-only package: model.py (the math), data_load.py, cli.py
web/index.html        offline dashboard, mirrors the Python math
tests/                pytest suite with hand-computable fixtures
```

## What I'd do next

Model dependencies between processes — right now each one is scored in isolation, but in practice a shared platform cost or one automation unlocking another changes the ranking, and that's the part the current model can't see.

---

MIT © 2026 Dimitres Kisimov. Seed data is synthetic.
