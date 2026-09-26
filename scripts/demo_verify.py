"""Check the standalone report offline and optionally exercise tailnet replay."""

import argparse
import json
import time

from playwright.sync_api import expect, sync_playwright

from scripts.demo_evidence import DEST, ROOT


def offline(browser):
    context = browser.new_context(offline=True, viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    errors, external = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda r: external.append(r.url) if r.url.startswith(("http:", "https:")) else None)
    page.goto((ROOT / "runtime/demo/index.html").as_uri(), wait_until="load")
    expect(page.locator("#measured-improvement > h2")).to_be_visible()
    assert page.locator("img").evaluate_all("imgs => imgs.every(i => i.complete && i.naturalWidth > 0)")
    assert "2/4 to 4/4" in page.locator("body").inner_text()
    assert page.locator("a[download]").count() == 3
    # Check downloaded payloads without relying on live paths or servers.
    for anchor in page.locator("a[download]").all():
        text = anchor.get_attribute("href")
        assert text.startswith("data:application/json;base64,")
    for name in ("Sensor mount", "Aerodynamic surface", "Shared assembly", "Workbench"):
        page.get_by_role("tab", name=name, exact=True).click()
        expect(page.get_by_role("tab", name=name, exact=True)).to_have_attribute("aria-selected", "true")
    page.evaluate("window.scrollTo(0,0)")
    page.screenshot(path=str(ROOT / "runtime/demo/report-desktop.png"))
    page.locator("#measured-improvement > h2").scroll_into_view_if_needed()
    page.screenshot(path=str(ROOT / "runtime/demo/report-results.png"))
    for width in (390, 1280):
        page.set_viewport_size({"width": width, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), f"Overflow at {width}px"
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate("window.scrollTo(0,0)")
    page.screenshot(path=str(ROOT / "runtime/demo/report-mobile.png"))
    assert not errors, errors
    assert not external, external
    context.close()
    print("PASS: standalone offline report, all images, tabs, JSON downloads, responsive layout, no external requests")


def remote(browser, origin):
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    page.goto(origin, wait_until="domcontentloaded", timeout=60000)
    expect(page.locator(".viewport-label")).to_contain_text("EVALUATED CAD GEOMETRY", timeout=90000)
    expect(page.get_by_test_id("cad-canvas")).to_have_attribute("data-geometry-ready", "true", timeout=60000)
    for name in ("Top view", "Side view", "Isometric view"):
        page.get_by_role("button", name=name, exact=True).click()
    for name in ("Memory", "Tools", "Archive", "Workbench"):
        page.get_by_role("button", name=name, exact=True).click()
    href = page.get_by_role("link", name="Export STEP", exact=True).get_attribute("href")
    artifact = context.request.get(origin + href, timeout=60000)
    assert artifact.ok and b"ISO-10303-21" in artifact.body()
    bad = context.request.post(origin + "/api/projects/uas-demo/runs", headers={"Origin": "http://example.invalid"},
                               data={"mode": "replay", "rounds": 2, "budget_usd": 1}, timeout=60000)
    assert bad.status == 403
    state = context.request.get(origin + "/api/workbench", timeout=60000).json()
    assert not any(r["status"] in ("running", "queued") for r in state["runs"]), "Existing active run; preserve it"
    response = context.request.post(origin + "/api/projects/uas-demo/runs", headers={"Origin": origin},
                                    data={"mode": "replay", "rounds": 2, "budget_usd": 1}, timeout=60000)
    assert response.status == 201, f"Replay admission HTTP {response.status}"
    run_id = response.json()["_id"]
    print("Started zero-inference tailnet replay " + run_id, flush=True)
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        run = context.request.get(origin + "/api/runs/" + run_id, timeout=60000).json()
        if run["status"] != "running":
            assert run["status"] == "completed", run["status"]
            break
        page.wait_for_timeout(2000)
    else:
        raise AssertionError("Tailnet replay did not complete within four minutes")
    state = context.request.get(origin + "/api/workbench", timeout=60000).json()
    evaluations = [e for e in state["evaluations"] if e["run_id"] == run_id]
    assert len(evaluations) == 4
    assert any(a["run_id"] == run_id and a["outcome"] == "passed" for a in state["assemblies"])
    # Validate event-stream delivery without waiting for the stream to close.
    streamed = page.evaluate("""async (runId) => {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 60000);
      try {
        const response = await fetch('/api/runs/' + runId + '/events', {signal: controller.signal});
        const reader = response.body.getReader(); const {value} = await reader.read();
        await reader.cancel();
        return response.ok && new TextDecoder().decode(value).includes('data:');
      } finally {clearTimeout(timeout); controller.abort();}
    }""", run_id)
    assert streamed
    page.screenshot(path=str(ROOT / "runtime/demo/tailnet-workbench.png"), full_page=True)
    (ROOT / "runtime/demo/remote-check.json").write_text(json.dumps({
        "origin": origin, "run_id": run_id, "mode": "replay", "evaluations": len(evaluations),
        "completed": True, "step_download": True, "same_origin": True,
        "cross_origin_rejected": True, "event_stream": True,
    }, indent=2) + "\n")
    print("PASS: tailnet CAD/navigation/STEP, origin checks, four-evaluation replay and event streaming")
    context.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", help="Also create one zero-inference two-round replay at this workbench origin")
    args = parser.parse_args()
    comparison = json.loads((DEST / "comparison.json").read_text())
    assert comparison["model_calls"] == 0
    assert len(comparison["results"]) == 8
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--enable-unsafe-swiftshader"])
        offline(browser)
        if args.remote:
            remote(browser, args.remote.rstrip("/"))
        browser.close()


if __name__ == "__main__":
    main()
