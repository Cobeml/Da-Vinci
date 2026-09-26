"""Capture archived, hash-verified CAD through the real Next.js viewer. No model calls."""

import argparse
import json
from urllib.parse import urlencode
from zipfile import ZipFile

from playwright.sync_api import expect, sync_playwright

from scripts.demo_evidence import DEST, VALIDATION, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:3215")
    args = parser.parse_args()
    assets = DEST / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    archives, blobs = {}, {}
    for name in ("replay", "live1", "live3"):
        with ZipFile(VALIDATION / f"{name}.zip") as z:
            archives[name] = {k: json.loads(z.read(k + ".json")) for k in (
                "run", "candidates", "evaluations", "assemblies", "releases", "tools",
                "champions", "events", "memories"
            )}
            for item in json.loads(z.read("artifact-manifest.json")):
                data = z.read(f"artifacts/{item['_id']}/{item['name']}")
                assert sha(data) == item["sha256"]
                blobs[item["_id"]] = (data, item["media_type"])
    manifest = []
    evidence = json.loads((DEST / "evidence.json").read_text())
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1440, "height": 1040}, device_scale_factor=1)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        selected = {"archive": "live3"}
        loaded = set()

        def route_api(route):
            path = route.request.url.split("/api/", 1)[1].split("?", 1)[0]
            data = archives[selected["archive"]]
            if path == "workbench":
                state = {k: data[k] for k in (
                    "candidates", "evaluations", "assemblies", "releases", "tools", "champions", "events"
                )}
                # Pin the assembly to round zero, independent of current database ordering.
                state["assemblies"] = sorted(state["assemblies"], key=lambda a: a["round"])
                state.update(runs=[data["run"]], active_release_id=evidence["release"]["_id"],
                             memory_count=len(data["memories"]), storage="atlas", live_available=True)
                route.fulfill(json=state)
            elif path.startswith("artifacts/"):
                artifact_id = path.split("/", 1)[1]
                body, mime = blobs[artifact_id]
                loaded.add(artifact_id)
                route.fulfill(body=body, content_type=mime)
            elif path.endswith("/events"):
                route.fulfill(body="", content_type="text/event-stream")
            else:
                route.fulfill(status=404, json={"detail": "Not part of archived screenshot session"})

        page.route("**/api/**", route_api)
        shots = [
            ("live3", "structural", 0, "Isometric view", "mount-iso"),
            ("live3", "structural", 0, "Top view", "mount-top"),
            ("replay", "structural", 0, "Isometric view", "mount-before"),
            ("live3", "aerodynamic", 0, "Isometric view", "wing-iso"),
            ("live3", "aerodynamic", 0, "Side view", "wing-detail"),
            ("replay", "aerodynamic", 0, "Isometric view", "wing-before"),
            ("live3", None, 0, "Isometric view", "assembly"),
        ]
        for archive, subsystem, round_number, camera, filename in shots:
            selected["archive"] = archive
            data = archives[archive]
            if subsystem:
                candidate = next(c for c in data["candidates"]
                                 if c["subsystem"] == subsystem and c["round"] == round_number)
                record = next(e for e in data["evaluations"] if e["candidate_id"] == candidate["_id"])
                target = "?" + urlencode({"candidate": candidate["_id"]})
                artifact_id = record["artifacts"]["model.glb"]
                subject_id = candidate["_id"]
            else:
                record = next(a for a in data["assemblies"] if a["round"] == round_number)
                target, subject_id = "", record["_id"]
                artifact_id = record["artifacts"]["assembly.glb"]
            loaded.clear()
            page.goto(args.url + "/" + target, wait_until="domcontentloaded", timeout=60000)
            expect(page.locator(".viewport-label")).to_contain_text("EVALUATED CAD GEOMETRY", timeout=60000)
            expect(page.get_by_test_id("cad-canvas")).to_have_attribute("data-geometry-ready", "true")
            page.get_by_role("button", name=camera, exact=True).click()
            page.wait_for_timeout(1200)
            page.get_by_test_id("cad-canvas").hover()
            for _ in range(12):
                page.mouse.wheel(0, -100)
                page.wait_for_timeout(35)
            page.wait_for_timeout(700)
            assert artifact_id in loaded, "Expected archive geometry was not loaded"
            path = assets / (filename + ".png")
            page.get_by_test_id("cad-canvas").screenshot(path=str(path))
            manifest.append({"file": "assets/" + path.name, "subject_id": subject_id,
                             "geometry_artifact_id": artifact_id, "camera": camera,
                             "zoom_wheel_delta": -100, "zoom_wheel_events": 12,
                             "sha256": sha(path.read_bytes()), "archive": archive,
                             "capture_method": "Real workbench viewer with hash-verified archive responses"})
            if filename == "assembly":
                page.screenshot(path=str(assets / "workbench.png"), full_page=True)
                manifest.append({**manifest[-1], "file": "assets/workbench.png",
                                 "sha256": sha((assets / "workbench.png").read_bytes())})
            print("Captured " + filename, flush=True)
        assert not errors, errors
        browser.close()
    (DEST / "screenshots.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
