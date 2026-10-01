import { test, expect, type APIRequestContext } from "@playwright/test";
import { readFile, mkdir } from "node:fs/promises";
const description =
  "Minimize mass of a 40 by 20 mm rectangular cantilever, thickness 2 to 8 mm, clamped root, 100 N transverse tip force, nominal aluminium E=70000 MPa and density=.0027 g/mm3. Stress <=100 MPa and deflection <=.5 mm. Analytic static screen only.";
async function status(request: APIRequestContext, id: string) {
  return (await request.get(`/api/v2/experiments/${id}`)).json();
}
async function mutate(
  request: APIRequestContext,
  id: string,
  action: string,
  payload = {},
) {
  const row = await status(request, id);
  const r = await request.post(`/api/v2/experiments/${id}/${action}`, {
    data: {
      actor: row.actor,
      revision: row.revision,
      operation_id: crypto.randomUUID(),
      ...payload,
    },
  });
  expect(r.ok(), await r.text()).toBeTruthy();
  return r.json();
}
async function waitJob(
  request: APIRequestContext,
  id: string,
  job: { id: string },
) {
  await expect
    .poll(
      async () =>
        (await request.get(`/api/v2/experiments/${id}/jobs/${job.id}`))
          .json()
          .then((x) => x.status),
      { timeout: 120000 },
    )
    .toBe("completed");
  return (await request.get(`/api/v2/experiments/${id}/jobs/${job.id}`)).json();
}

test("external authoring, native CAD, shared viewing, continuation and handoff", async ({
  page,
  request,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "+ New object" }).click();
  await page
    .getByRole("button", { name: "External agent", exact: true })
    .click();
  await page.getByLabel("Object name", { exact: true }).fill("External beam");
  await page.getByLabel("Engineering request").fill(description);
  await page.getByRole("button", { name: "Open external experiment" }).click();
  await expect(page).toHaveURL(/id=external-beam/);
  await expect(
    page.getByText("Waiting on external agent", { exact: true }),
  ).toBeVisible();
  await page
    .getByText("External agent connection and commands", { exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Copy command" }).first(),
  ).toBeVisible();
  const row = (
      await (
        await request.get("/api/v2/workspace/objects/external-beam")
      ).json()
    ).runs[0].experiment,
    id = row._id;
  const directory = "davinci/product/resources/external/";
  const plan = JSON.parse(await readFile(directory + "plan.json", "utf8"));
  const source = await readFile(directory + "build.py", "utf8"),
    evaluate = await readFile(directory + "evaluate.py", "utf8");
  const runtime = JSON.parse(
    await readFile(directory + "runtime.json", "utf8"),
  );
  runtime.image = (
    await (
      await request.get("/api/v2/runtimes/resolve?image=da-vinci-cad:local")
    ).json()
  ).image;
  await mutate(request, id, "plan", {
    plan,
    runtime,
    evaluator: {
      resources: { "evaluate.py": evaluate },
      provenance: "Packaged independently checked beam example",
    },
  });
  const candidate = (t: number) => ({
    title: `External ${t} mm beam`,
    source,
    parameters: { thickness: t },
  });
  for (const t of [4, 2]) {
    const built = await waitJob(
      request,
      id,
      await mutate(request, id, "reference-builds", {
        reference: {
          candidate: candidate(t),
          provenance: "Closed-form fixture",
        },
      }),
    );
    const values: Record<string, number> = {
      mass_g: 40 * 20 * t * 0.0027,
      stress_mpa: (6 * 100 * 40) / (20 * t * t),
      deflection_mm: (4 * 100 * 40 ** 3) / (70000 * 20 * t ** 3),
    };
    await waitJob(
      request,
      id,
      await mutate(request, id, "verify", {
        verification: {
          test_id: "beam",
          fixture_artifact: built.fixture_artifacts[0],
          expected_status: t === 4 ? "pass" : "physical_failure",
          reference_metrics: Object.fromEntries(
            Object.entries(values).map(([k, v]) => [
              k,
              {
                value: v,
                unit: plan.tests[0].metrics[k],
                dimension: "reference",
              },
            ]),
          ),
          tolerances: Object.fromEntries(
            Object.keys(values).map((k) => [k, 0.0001]),
          ),
          provenance: "Independent closed-form values",
        },
      }),
    );
  }
  await mutate(request, id, "freeze");
  for (const t of [2, 4]) {
    await mutate(request, id, "candidates", { candidate: candidate(t) });
    await waitJob(request, id, await mutate(request, id, "evaluate"));
    await mutate(request, id, "reflections", {
      lesson: "Measured beam screening; no fatigue validation",
    });
  }
  await mutate(request, id, "finalize");
  await expect(
    page.getByRole("region", { name: "Final report" }),
  ).toBeVisible();
  await expect(page.getByTestId("iteration-card")).toHaveCount(2);
  await expect(
    page.getByText("Physical failure", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Accepted under stated tests", { exact: true }).first(),
  ).toBeVisible();
  await page
    .getByLabel("CAD model", { exact: true })
    .first()
    .scrollIntoViewIfNeeded();
  await expect(
    page.locator("[data-geometry-ready=true]").first(),
  ).toBeVisible();
  await mkdir("runtime/product-screenshots", { recursive: true });
  await page.screenshot({
    path: "runtime/product-screenshots/external.png",
    fullPage: true,
  });
  const suite = (await status(request, id)).suite_id;
  await page
    .getByLabel("Continuation seed")
    .selectOption({ label: "External 4 mm beam · 2" });
  await page
    .getByRole("button", { name: "Start continuation", exact: true })
    .click();
  await expect(
    page.getByText("Waiting on external agent", { exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId("iteration-card")).toHaveCount(1);
  await page.getByLabel("Next driver").selectOption("managed");
  await page.getByLabel("New candidate limit").fill("2");
  await page
    .getByLabel("Handoff reason / continuation focus")
    .fill("Continue this frozen test suite with the built-in agent");
  await page.getByRole("button", { name: "Hand off this experiment" }).click();
  await expect(page.getByRole("region", { name: "Final report" })).toBeVisible({
    timeout: 120000,
  });
  const detail = await (
    await request.get("/api/v2/workspace/objects/external-beam")
  ).json();
  expect(detail.runs[0].experiment.driver).toBe("managed");
  expect(detail.runs[0].experiment.suite_id).toBe(suite);
  expect(detail.runs[0].experiment.handoffs).toHaveLength(1);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("managed description, genuine clarification, native iterations and report", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "+ New object" }).click();
  await page
    .getByRole("button", { name: "Built-in agent", exact: true })
    .click();
  await page.getByLabel("Object name", { exact: true }).fill("Managed beam");
  await page
    .getByLabel("Engineering request")
    .fill(
      description.replace("100 N transverse tip force", "force unspecified"),
    );
  await page.getByLabel("Candidate limit", { exact: true }).fill("2");
  await page.getByRole("button", { name: "Start managed request" }).click();
  await expect(page.getByRole("region", { name: "Clarification" })).toBeVisible(
    { timeout: 30000 },
  );
  await page
    .getByLabel("What transverse tip force in newtons must it carry?")
    .fill("100 N");
  await page
    .getByRole("button", { name: "Submit engineering answers" })
    .click();
  await expect(page.getByRole("region", { name: "Final report" })).toBeVisible({
    timeout: 120000,
  });
  await expect(page.getByRole("region", { name: "Test plan" })).toContainText(
    "Frozen suite",
  );
  await expect(
    page.getByText("Critical coverage: complete", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Capabilities" }),
  ).toContainText("analytic");
  await expect(page.getByTestId("iteration-card")).toHaveCount(3);
  await expect(
    page.getByText("Final evidence: complete", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "runtime/product-screenshots/managed.png",
    fullPage: true,
  });
});

test("missing solver is visible and cannot claim acceptance", async ({
  page,
  request,
}) => {
  const response = await request.post("/api/v2/managed-experiments", {
    data: {
      object: { slug: "missing-solver", name: "Missing solver" },
      description,
      actor: "user",
      operation_id: "missing-solver",
      runtime: {
        image: "sha256:" + "a".repeat(64),
        solver: "Missing test solver",
        provenance: "Explicit missing-runtime check",
      },
    },
  });
  expect(response.status()).toBe(202);
  const id = (await response.json())._id;
  await expect
    .poll(async () => (await status(request, id)).managed.status, {
      timeout: 30000,
    })
    .toBe("blocked");
  await page.goto("/object/?id=missing-solver");
  await expect(
    page.getByRole("region", { name: "Capabilities" }),
  ).toContainText("unavailable");
  await expect(page.getByTestId("iteration-card")).toHaveCount(0);
  await expect(
    page.getByText("Accepted under stated tests", { exact: true }),
  ).toHaveCount(0);
});
