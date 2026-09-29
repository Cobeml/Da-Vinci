# VTOL surface tools — paused beta

Status set on 2026-09-29. Development is deferred because the matched experiment produced mixed performance and exposed a CAD consistency issue. The established VTOL study remains the featured demo.

## What is preserved

- CST section editing, spline lofts, section optimization and nonlinear aerodynamic checks in `sandbox/surface_*.py`, `sandbox/evaluate_surface.py` and `davinci/surface.py`.
- Explicit study commands in `scripts/surface_prepare.py` and `scripts/surface_study.py`, plus CAD and browser tests.
- All 24 designs, STEP/GLB assets, Atlas records, tool evidence and frozen evaluator identifiers for `survey-vtol-cst-v1`.
- [Methods and reproduction](../studies/vtol-surface-tools.md) and [archived results](../studies/vtol-surface-results.md).

The viewer remains available by direct URL at `/vtol-tools`, marked beta and with search indexing disabled. It has no link from the main demo and cannot automatically replace the homepage. This is an unlisted development page, not access control. No new studies run automatically.

## Known issues to address when resuming

1. **Fairing consistency:** surface-arm model 02 passes basic solid validity but fails STEP/reference comparison for both root fairings. An offline diagnostic found reference volume 485,462 mm³ versus imported volume 601,950 mm³ per affected solid, a 13.37 mm centroid difference, and invalid Boolean difference results. Increasing comparison tolerance through 0.001 mm did not resolve it. The precise cause—construction, STEP conversion or geometric calculations—remains unresolved. See the [saved diagnostic](surface-02-geometry-audit.json).
2. **Preview acceptance differs from evaluation:** previews check imported solid validity, while evaluation also checks geometry agreement. Align these checks and explicitly detect invalid comparison operations before accepting previews.
3. **Rejected estimates:** the failed model's 76.66 km screening estimate is diagnostic only. Clearly distinguish rejected estimates in the beta viewer before broader release; do not promote it based on that value.
4. **Whole-aircraft tradeoffs:** the best accepted surface design reached 74.39 km and 17 m/s, compared with 77.21 km and 19 m/s for the dimensional control. Investigate trim-derived section targets, mass/speed penalties and capability-preserving parent selection in a new matched experiment.

## Resume later

Keep the current study and results frozen. First reproduce and repair the fairing issue with regression coverage, then use a new study ID and evaluator version for changed physics or geometry code. Retain matched controls and verification gates. Restoring public links or homepage eligibility requires an explicit release change; a generated `publishable: true` value alone cannot release the beta.

To inspect the saved experiment, open `/vtol-tools`; no API calls are required. Existing reproduction commands remain in the methods document. Do not run paid study commands merely to view the archive.
