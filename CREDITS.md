# Credits

**automation-roi-explorer** — created and maintained by **Dimitres Kisimov** (2026).

## Data

All process data is **synthetic**. The five seeded candidates (RFQ email triage,
invoice matching, product-data cleanup, returns processing, supplier onboarding)
and every number attached to them — volumes, task minutes, wages, build and
running costs — are illustrative figures chosen to represent a plausible B2B
distribution back office. They are **not** drawn from any real company, customer,
or confidential source, and should be replaced with your own estimates before
using the tool for a real decision.

## Tools and standards

- Core model: **Python standard library only** (no third-party runtime deps).
- Dashboard: **vanilla JavaScript + HTML Canvas**, no frameworks, no CDNs, fully offline.
- Tests: [pytest](https://pytest.org).
- Linting: [ruff](https://docs.astral.sh/ruff/).
- Continuous integration: GitHub Actions.

## License

Released under the MIT License — see [LICENSE](LICENSE).
