# Business case — sequencing a back-office automation budget

*Worked example. The company is fictional and the five seeded processes are
synthetic (and labelled as such). Every euro, hour, payback, ROI, and NPV figure
below is produced by this repository's real `compute()` — reproduce them with
`python -m roi_model`.*

## Situation

**Brandt Logistik & Handel GmbH** is a mid-size distributor. Its COO has a
one-line mandate from the board: *start automating the back office this year*.
Operations has handed up a wish-list of manual processes — invoice matching, RFQ
triage, returns, product-data cleanup, supplier onboarding — and every team lead
is sure theirs should go first.

The budget funds roughly one build at a time. So the real question is not "can we
automate these" — it is **"which one first, and is it actually worth it?"** The
COO needs the backlog ranked by value, with the math shown, not by whoever
lobbied hardest.

## Problem, quantified

The five candidate processes and their manual load (from
[`roi_model/data/processes.csv`](../roi_model/data/processes.csv)):

| Process | Volume/yr | Min/task | Manual h/yr | Wage €/h | Manual labour €/yr |
|---|---:|---:|---:|---:|---:|
| Invoice matching (3-way) | 120,000 | 4 | 8,000 | 30 | 240,000 |
| RFQ email triage | 48,000 | 6 | 4,800 | 32 | 153,600 |
| Returns processing | 36,000 | 8 | 4,800 | 29 | 139,200 |
| Product-data cleanup | 15,000 | 12 | 3,000 | 28 | 84,000 |
| Supplier onboarding | 2,400 | 45 | 1,800 | 35 | 63,000 |
| **Total** | | | **22,400** | | **679,800** |

- Manual h/yr = volume × minutes ÷ 60. Example (invoice matching): 120,000 × 4 ÷ 60 = **8,000 h**.
- **~22,400 hours/year** of manual back-office effort — roughly **13 full-time
  equivalents** at ~1,700 productive hours each — costing **~€680,000/yr**
  fully-loaded across these five processes alone.
- The constraint: the automation budget can fund about one build at a time, so
  the sequencing decision is worth real money if it is wrong.

## Solution

`automation-roi-explorer` puts numbers on each candidate and ranks the backlog.
One `compute()` function is the single source of truth (the browser dashboard
mirrors it line-for-line in JavaScript), turning each process's assumptions —
volume, minutes before/after, wage, the `coverage` fraction the automation truly
handles end-to-end, build cost, running cost — into hours saved, net €/yr,
payback, 3-year ROI, and discounted NPV.

Worked example, **Invoice matching (3-way)**, the exact arithmetic the model runs:

- automated volume = 120,000 × 0.85 coverage = **102,000**
- minutes saved/task = 4 − 0.5 = **3.5**
- hours saved/yr = 102,000 × 3.5 ÷ 60 = **5,950 h**
- gross saving = 5,950 × €30 = **€178,500**
- running cost = €600 × 12 = €7,200 → **net saving = €171,300/yr**
- payback = €40,000 build ÷ (€171,300 ÷ 12) = **2.8 months**
- 3-yr net benefit = €171,300 × 3 − €40,000 = **€473,900**
- 3-yr ROI = €473,900 ÷ (€40,000 + €7,200 × 3) = **769%**
- NPV @ 8% = −€40,000 + Σ €171,300 ÷ 1.08ᵗ (t=1..3) = **€401,457**

## Impact / ROI

The model's ranked backlog (`python -m roi_model`, ranked by 3-year net benefit):

| Rank | Process | Hrs/yr | Net €/yr | Payback | 3y ROI | NPV 3y |
|---:|---|---:|---:|---:|---:|---:|
| 1 | Invoice matching (3-way) | 5,950 | 171,300 | 2.8 mo | 769% | 401,457 |
| 2 | RFQ email triage | 2,800 | 84,800 | 3.5 mo | 582% | 193,538 |
| 3 | Returns processing | 2,700 | 72,900 | 4.9 mo | 408% | 157,870 |
| 4 | Product-data cleanup | 1,350 | 34,800 | 6.2 mo | 320% | 71,683 |
| 5 | Supplier onboarding | 660 | 19,500 | 13.5 mo | 111% | 28,253 |
| | **Portfolio** | **13,460** | **383,300** | | | **852,801** |

- **Sequence, not guess:** invoice matching goes first — €171,300/yr net, a
  **2.8-month payback**, and the highest NPV by a wide margin. Supplier
  onboarding, despite being the most painful per task (45 min), lands last: low
  volume caps its payback at 13.5 months.
- **Portfolio prize:** working the backlog top-down frees **13,460 hours/year**
  and **€383,300/yr net** — recovering the automatable share of that ~€680k
  manual spend, at a fraction of the cost.

## Stakeholders & use case

- **COO** — owns the budget and the sequencing decision.
- **Process / team leads** — supply real volumes, times, and honest `coverage`.
- **Finance** — sets the discount rate (8% here) and validates payback/NPV.
- **Automation / RPA lead** — delivers builds in the ranked order.

Numbered workflow:

1. Each team lead enters their process's assumptions (volume, minutes
   before/after, wage, coverage, build and running cost).
2. `compute()` turns each into hours saved, net €/yr, payback, 3y ROI, and NPV.
3. `rank()` orders the backlog by 3-year net benefit (or `--sort payback_months`
   for a cash-conservative view).
4. The COO reads the top of the list, commits budget to #1, and schedules the rest.
5. On the dashboard, a lead drags a slider (e.g. lowers coverage to be honest
   about the messy tail) and watches the ranking and payback move in real time.
6. After each build ships, real numbers replace the estimates and the backlog
   re-ranks.

## Deliverable

- This repository: the stdlib `roi_model` package/CLI and the offline dashboard.
- [`deliverables/executive_onepager.pdf`](../deliverables/executive_onepager.pdf)
  — a one-page executive summary generated by
  [`scripts/make_onepager.py`](../scripts/make_onepager.py), which draws its
  numbers **directly from the ROI model output**.

---

*Honesty notes: all euro/hour/ROI figures are computed by the real model and are
reproducible. The five seeded processes and their inputs are synthetic — swap in
your own before deciding anything. Savings assume freed hours become real money
(redeployed staff, avoided hires, less overtime); volumes and wages are held flat
over three years; NPV uses a flat 8% discount rate; costs exclude change
management, risk, and the maintenance tail; processes are scored independently.*
