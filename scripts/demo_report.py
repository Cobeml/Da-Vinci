"""Render the offline Quarto report from checked-in evidence; needs no credentials."""

import base64
import html
import json
import subprocess
from pathlib import Path

from scripts.demo_evidence import DEST, ROOT, sha


def metric(evaluation, key, scale=1):
    return evaluation["metrics"][key]["value"] * scale


def svg_chart(path, title, rows):
    """Small standalone comparison figure, with numeric labels and independent scales."""
    height = 85 + len(rows) * 105
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 850 {height}" role="img" '
             f'aria-label="{html.escape(title)}">',
             f'<rect width="850" height="{height}" rx="16" fill="#f0efe7"/>',
             '<g font-family="sans-serif" fill="#172d25">',
             f'<text x="28" y="36" font-size="21" font-weight="bold">{html.escape(title)}</text>',
             '<text x="28" y="60" font-size="13">Baseline / earlier = clay · Promoted / later = green</text>']
    for i, (label, a, b, unit) in enumerate(rows):
        y = 95 + i * 105
        parts.append(f'<text x="28" y="{y}" font-size="15">{html.escape(label)}</text>')
        maximum = max(a, b, 0.00001)
        for offset, value, color in ((12, a, "#b97553"), (39, b, "#246b50")):
            width = 560 * value / maximum
            parts.append(f'<rect x="28" y="{y + offset}" width="{width:.2f}" height="19" '
                         f'rx="3" fill="{color}"/>')
            parts.append(f'<text x="{40 + width:.2f}" y="{y + offset + 15}" font-size="14">'
                         f'{value:.4g} {html.escape(unit)}</text>')
    parts.append('</g></svg>')
    path.write_text("\n".join(parts))


def generate():
    evidence = json.loads((DEST / "evidence.json").read_text())
    comparison = json.loads((DEST / "comparison.json").read_text())
    release = evidence["release"]
    assert comparison["release_files_sha256"][release["_id"]] == sha(
        json.dumps(release["files"], sort_keys=True).encode()
    ), "Comparison was built from different release files; refresh it explicitly"
    shots = json.loads((DEST / "screenshots.json").read_text())
    for shot in shots:
        assert sha((DEST / shot["file"]).read_bytes()) == shot["sha256"]
    results = comparison["results"]
    arms = {arm: [x for x in results if x["arm"] == arm] for arm in ("baseline", "promoted")}
    assert all(len(items) == 4 for items in arms.values())
    passed = {arm: sum(x["evaluation"]["outcome"] == "passed" for x in items)
              for arm, items in arms.items()}
    pairs = {}
    for before, after in zip(arms["baseline"], arms["promoted"], strict=True):
        for key in ("candidate_id", "source_sha256", "input_parameters"):
            assert before[key] == after[key], f"Unpaired comparison: {key}"
        pairs[(before["subsystem"], before["case"])] = (before, after)
    structural = [x["evaluation"] for x in pairs[("structural", "failure")]]
    aero = [x["evaluation"] for x in pairs[("aerodynamic", "failure")]]
    assets = DEST / "assets"
    svg_chart(assets / "controlled.svg", "Same proposals. Different orchestration release.", [
        ("Feasible cases / four fixed inputs", passed["baseline"], passed["promoted"], "of 4"),
        ("Thin mount: screened deflection", *[metric(e, "deflection_mm") for e in structural], "mm"),
        ("Thin mount: screened bending stress", *[metric(e, "bending_stress_pa", 1e-6) for e in structural], "MPa"),
        ("Control surface: measured hinge clearance", *[metric(e, "hinge_gap_mm") for e in aero], "mm"),
    ])
    replay = evidence["runs"]["replay"]["evaluations"]

    def row(run, subsystem, round_number):
        return next(x for x in evidence["runs"][run]["evaluations"]
                    if x["subsystem"] == subsystem and x["round"] == round_number)

    live_before, live_after = row("live1", "aerodynamic", 0), row("live3", "aerodynamic", 0)
    drag_delta = 100 * (1 - metric(live_after, "induced_drag_n") / metric(live_before, "induced_drag_n"))
    mass_delta = 100 * (metric(live_after, "mass_kg") / metric(live_before, "mass_kg") - 1)
    svg_chart(assets / "live.svg", "Observed live-run tradeoff · not a causal ablation", [
        ("Screened induced drag", metric(live_before, "induced_drag_n"), metric(live_after, "induced_drag_n"), "N"),
        ("Wing mass", metric(live_before, "mass_kg", 1000), metric(live_after, "mass_kg", 1000), "g"),
        ("Wing span", metric(live_before, "span_mm"), metric(live_after, "span_mm"), "mm"),
    ])
    body = [
        f"The controlled comparison changed feasibility from **{passed['baseline']}/4 to {passed['promoted']}/4** "
        "on the four archived inputs. Two are known failure cases and two are passing controls. "
        "This is an in-sample regression demonstration of the promoted release, not an estimate of performance on unseen designs.",
        "![Paired evaluation with a fixed CAD source, specification and Docker image. Each row has its own scale.](assets/controlled.svg)",
        "| Fixed input | Baseline result | Promoted result | Parameter intervention |",
        "|---|---|---|---|",
    ]
    for (subsystem, case), (before, after) in pairs.items():
        key = "thickness_mm" if subsystem == "structural" else "hinge_gap_mm"
        body.append(f"| {subsystem.title()} {case} | {before['evaluation']['outcome']} | "
                    f"{after['evaluation']['outcome']} | {key}: "
                    f"{before['adapted_parameters'][key]:g} → {after['adapted_parameters'][key]:g} mm |")
    body += ["", "**Engineering tradeoff.** The thin mount becomes thicker and heavier: "
             f"{metric(structural[0], 'mass_kg', 1000):.2f} → {metric(structural[1], 'mass_kg', 1000):.2f} g. "
             "That change fixes thickness and deflection violations. The hinge adjustment fixes clearance and travel collision; "
             "it does not establish a drag benefit. Passing controls retain their original parameters.",
             "", "### Iteration gains and live results", "",
             "The deterministic replay demonstrates recovery followed by optimization:", "",
             "| Comparison | Earlier | Later | Meaning |", "|---|---:|---:|---|"]
    m1, m2 = row("replay", "structural", 1), row("replay", "structural", 2)
    a0, a3 = row("replay", "aerodynamic", 0), row("replay", "aerodynamic", 3)
    body += [
        f"| Passing mount mass, replay rounds 2 → 3 | {metric(m1, 'mass_kg', 1000):.2f} g | "
        f"{metric(m2, 'mass_kg', 1000):.2f} g | {100*(1-metric(m2,'mass_kg')/metric(m1,'mass_kg')):.1f}% lighter |",
        f"| Screened wing drag, replay rounds 1 → 4 | {metric(a0,'induced_drag_n'):.4f} N | "
        f"{metric(a3,'induced_drag_n'):.4f} N | {100*(1-metric(a3,'induced_drag_n')/metric(a0,'induced_drag_n')):.1f}% lower; span and mass increase |",
        "", "Replay geometry choices are scripted fixtures. They demonstrate the loop but are not autonomous Astra discoveries.",
        "", "![Both live runs passed their geometric checks; the later run uses a longer wing.](assets/live.svg)",
        f"The later live run has **{drag_delta:.1f}% lower induced-drag screening** and **{mass_delta:.1f}% greater wing mass**. "
        "Both the release and available context differ between these runs, so this comparison is observational. "
        "The controlled experiment above isolates the saved release's adaptation behavior; it does not attribute this drag change to that release.",
        "", "### Validation ledger", "", "| Recorded run | Evaluations | Passing | Accepted assemblies |", "|---|---:|---:|---:|",
    ]
    for name, run in evidence["runs"].items():
        evaluations = run["evaluations"]
        body.append(f"| {name} | {len(evaluations)} | {sum(e['outcome']=='passed' for e in evaluations)} | "
                    f"{sum(a['outcome']=='passed' for a in run['assemblies'])} |")
    body += ["", "A separate live2 attempt failed before evaluation because a trigger used the wrong handler. "
             "It remains in the historical ledger and its spend is included below. The handler was corrected and invalid-job quarantine added.",
             "", f"Recorded validation spend: **${evidence['checks']['budget']['spent_usd']:.4f}** "
             "(application usage ledger, not a billing invoice; earlier credential probes excluded). "
             "The demo comparison and screenshot capture make **zero model calls**.",
             "", "Existing acceptance: **19 Python/API tests + 7 Docker/CAD tests + 4 Atlas browser tests**. "
             f"Live acceptance timestamp: `{evidence['accepted_at']}`. These are dated verification results, not a live health indicator.",
             "", "<details><summary>Controlled experiment provenance</summary>", "",
             f"Executed: `{comparison['created_at']}`. Eight real CadQuery evaluations; fixed sources, inputs, specification and image. "
             "Only the archived orchestration/policy release changes between paired arms.", "",
             f"Image: `{comparison['runtime_image_digest']}`", "",
             f"Promoted release: `{evidence['release']['_id']}`. Source commit: `{evidence['release']['source_commit']}`.",
             "", "</details>"]
    (DEST / "_results.qmd").write_text("\n\n".join(body[:2]) + "\n\n" + "\n".join(body[2:]) + "\n")
    release = evidence["release"]
    details = ["<details><summary>Read the actual promoted orchestration and policy</summary>", "",
               "```python", release["files"]["orchestrator.py"].rstrip(), "```", "",
               "```json", release["files"]["policy.json"].rstrip(), "```", "", "</details>", "",
               "### Download the evidence", "",
               "These embedded JSON downloads work offline and contain the data behind the figures, "
               "source/version identifiers, and screenshot provenance.", ""]
    for name in ("evidence.json", "comparison.json", "screenshots.json"):
        encoded = base64.b64encode((DEST / name).read_bytes()).decode()
        details.append(f'<a class="evidence-download" download="{name}" '
                       f'href="data:application/json;base64,{encoded}">{name}</a>')
    details += ["", "<details><summary>Screenshot subjects and artifact identifiers</summary>", "",
                "| Image | Subject | Camera |", "|---|---|---|"]
    for shot in shots:
        details.append(f"| {Path(shot['file']).stem} | `{shot['subject_id']}` | {shot['camera']} |")
    details += ["", "All screenshots use the real current workbench viewer with API responses replayed from hash-verified "
                "exports. They depict archived evaluated CAD, not reference previews or a claim of current database state.",
                "", "</details>"]
    (DEST / "_provenance.qmd").write_text("\n".join(details) + "\n")
    assert len(replay) == 8


def main():
    generate()
    subprocess.run(["quarto", "render", "index.qmd"], cwd=DEST, check=True)
    output = ROOT / "runtime/demo"
    output.mkdir(parents=True, exist_ok=True)
    (DEST / "index.html").replace(output / "index.html")
    print(f"Standalone demo: {output / 'index.html'}")


if __name__ == "__main__":
    main()
