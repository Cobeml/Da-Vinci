# VTOL surface-tool experiment results

**Screening range:** 70.9 km baseline → 76.0 km with dimensional controls (**7.3%**) and 74.4 km with surface tools (**5.0%**). These use one frozen evaluator; the previous VTOL study is a separate comparison.

**Verified range:** 71.2 km baseline, 77.2 km dimensional controls, 74.4 km surface tools. Verified gains over the baseline are **8.4% for dimensional controls** and **4.4% for surface tools**. The surface-tool arm changes verified range by **-3.7% relative to the control**.

No new-tool design passed all promotion gates. The experiment is published at `/vtol-tools`; the previous validated study remains on the homepage.

| Verified design | Range est. (km) | Max speed est. (m/s) | Payload capacity est. (kg) | Endurance est. (min) | Mass (kg) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 71.2 | 19.00 | 0.816 | 87.0 | 3.87 |
| Dimensional controls | 77.2 | 19.00 | 0.816 | 97.5 | 3.86 |
| Surface tools | 74.4 | 17.00 | 0.816 | 94.0 | 3.98 |

| Iteration | Dimensional range est. (km) | Result | Surface-tool range est. (km) | Result |
| --- | ---: | --- | ---: | --- |
| 1 | 70.9 | passed | 70.9 | passed |
| 2 | 70.9 | passed | 76.7 | failed |
| 3 | 0.0 | failed | 72.4 | passed |
| 4 | 72.3 | passed | 72.6 | passed |
| 5 | 72.4 | passed | 72.7 | passed |
| 6 | 72.6 | passed | 72.8 | passed |
| 7 | 74.6 | passed | 72.5 | passed |
| 8 | 75.4 | passed | 72.3 | passed |
| 9 | 76.0 | passed | 72.8 | passed |
| 10 | 75.9 | passed | 72.6 | passed |
| 11 | 76.0 | passed | 72.8 | passed |
| 12 | 76.0 | passed | 74.4 | passed |

- **Best dimensional design, iteration 12:** Reduced shell thickness from 1.25 to 1.20 mm while retaining the 2.50 m wing, 125 mm tail chord and 32.5 mm spar.
- **Best surface-tool design, iteration 12:** Increased washout from −1.00° to −1.25°, reduced spar wall thickness from 1.05 to 1.00 mm and reduced tail span from 620 to 580 mm. Retained the seed root section and the optimized tip section.

The dimensional winner increases span from 2.30 to 2.50 m, narrows the body from 170 to 140 mm and lowers its height from 180 to 150 mm. The surface-tool winner also reaches 2.50 m span, changes the tip CST section, increases middle-wing chord by 4% and adds 0.2° middle-station twist; the root section stays unchanged. Its screening mass is 3.98 kg versus 3.86 kg for the dimensional winner. These are observed design differences, not an isolated causal attribution of the range gap.

24 scored entries, including the shared baseline in each arm. 42 non-submission tool calls, 7 returned errors, and 14,757 reported successful section-optimizer evaluations. Recorded API accounting: **$11.00 / $60**, including both pilot attempts. Numerical solver time is separate from API accounting.

## Integration assessment

The tools are usable in the agent workflow, but this run does not demonstrate a range advantage over dimensional editing. Keep them available for geometry exploration; do not describe the package as a proven performance improvement. A useful next experiment would derive section-optimizer conditions from current aircraft trim, include whole-aircraft mass and speed penalties, and choose parent designs that retain the required speed and payload. Those changes need a new matched campaign; they were not retroactively applied here.

The three-task pilot passed after a fairing repair; the first failed pilot remains archived. Range refinement requires ≤2% change between nonlinear resolutions, plus XFOIL consistency. A promoted winner also needs ≥5% range over baseline and control, ≥95% of baseline speed and payload, and an adverse-case advantage.

All six selected revisions and the common baseline passed refinement and XFOIL consistency. The best surface-tool revision still misses the promotion criteria: its verified range is below the dimensional control, its baseline range gain is below 5%, and its 17 m/s speed is below the 18.05 m/s retention threshold.

Implementation checks passed: 31 unit tests, three CAD/solver integration tests, the production build, and browser coverage of the new experiment and three existing galleries. A final browser rerun checked all 24 models, tool disclosures, STEP access, filtering, responsive layout and the homepage promotion decision. The Tailscale demo endpoint returned HTTP 200.

These are engineering estimates, not flight measurements. The study compares a complete tool package with dimensional controls, not equal numerical compute or an isolated causal effect of recursive improvement.

Evaluator: `surface-87b20bc696d38cff`. [Full exported evidence](../../web/data/surface-gallery.json) · [Methods and reproduction](vtol-surface-tools.md).
