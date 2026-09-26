"""Persistent screenshot/action loop against the local CAD workbench."""

import base64
import json
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright

from davinci.engine import Engine
from davinci.models import document


def inspect_candidate(settings, candidate_id):
    engine = Engine(settings)
    candidate = engine.store.get("candidates", candidate_id)
    run = engine.store.get("runs", candidate["run_id"])
    captures = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--enable-unsafe-swiftshader"])
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
            # Only this workbench origin is visited. Model tools cannot navigate elsewhere.
            page.goto(
                settings.davinci_web_url + "/?" + urlencode({"candidate": candidate_id}),
                wait_until="networkidle",
                timeout=60000,
            )
            page.get_by_test_id("cad-canvas").wait_for()
            inputs = []
            provider = engine.provider(run)
            for step in range(4):
                screenshot = page.screenshot()
                artifact = engine.artifacts.put(screenshot, f"inspection-{step}.png", "image/png")
                captures.append(artifact)
                if run["mode"] == "replay":
                    page.get_by_role(
                        "button",
                        name=["Top view", "Side view", "Isometric view", "Top view"][step],
                        exact=True,
                    ).click()
                    page.wait_for_timeout(400)
                    continue
                inputs.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": "Inspect this CAD candidate. Select another view if useful, or finish with a short visual observation. Numeric scores come from the evaluator.",
                            },
                            {
                                "type": "input_image",
                                "image_url": "data:image/png;base64," + base64.b64encode(screenshot).decode(),
                                "detail": "original",
                            },
                        ],
                    }
                )
                response = provider._response(
                    input=inputs,
                    instructions="Inspect geometry through the workbench UI. Use set_view to change views. Do not claim numerical clearance from a screenshot.",
                    tools=[
                        {
                            "type": "function",
                            "name": "set_view",
                            "description": "Click a CAD workbench camera button.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "view": {
                                        "type": "string",
                                        "enum": ["Top view", "Side view", "Isometric view"],
                                    }
                                },
                                "required": ["view"],
                                "additionalProperties": False,
                            },
                        }
                    ],
                )
                inputs.extend(item.model_dump(exclude_none=True) for item in response.output)
                calls = [item for item in response.output if item.type == "function_call"]
                if not calls:
                    engine.store.event(
                        run["_id"],
                        "visual_observation",
                        response.output_text[:3000],
                        candidate_id=candidate_id,
                    )
                    break
                for call in calls:
                    args = json.loads(call.arguments)
                    if call.name != "set_view" or args.get("view") not in (
                        "Top view",
                        "Side view",
                        "Isometric view",
                    ):
                        raise ValueError("Unsupported browser action")
                    page.get_by_role("button", name=args["view"], exact=True).click()
                    page.wait_for_timeout(400)
                    inputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": "View changed; screenshot follows.",
                        }
                    )
            browser.close()
        engine.store.insert(
            "inspections",
            document(
                "inspection",
                run_id=run["_id"],
                candidate_id=candidate_id,
                artifacts=captures,
                mode=run["mode"],
            ),
        )
        engine.store.event(
            run["_id"],
            "inspection_completed",
            "Browser inspection archived",
            candidate_id=candidate_id,
            screenshots=captures,
        )
    except Exception as exc:
        engine.store.event(run["_id"], "inspection_failed", str(exc)[:1000], candidate_id=candidate_id)
