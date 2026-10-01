"use client";
import { useEffect, useState } from "react";
import AdvancedRunForm from "./AdvancedRunForm";
import type { Config, Connection } from "./types";
import s from "./workspace.module.css";

export default function RunForm({
  initial,
  onClose,
  onStarted,
}: {
  initial?: Config;
  onClose: () => void;
  onStarted: (id: string) => void;
}) {
  const [route, setRoute] = useState<"managed" | "external" | "advanced">(
    initial ? "advanced" : "managed",
  );
  const [connection, setConnection] = useState<Connection>();
  const [name, setName] = useState(""),
    [slug, setSlug] = useState("");
  const [description, setDescription] = useState(""),
    [image, setImage] = useState("da-vinci-cad:local");
  const [budget, setBudget] = useState(10),
    [iterations, setIterations] = useState(4);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [operation] = useState(() => crypto.randomUUID());
  useEffect(() => {
    fetch("/api/v2/workspace/connection")
      .then((r) => r.json())
      .then(setConnection)
      .catch(() => setError("Cannot connect to the workspace service."));
  }, []);
  if (route === "advanced")
    return (
      <AdvancedRunForm
        initial={initial}
        onClose={onClose}
        onStarted={onStarted}
      />
    );
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body: Record<string, unknown> = {
        object: { slug, name },
        description,
        driver: route,
        actor: route === "external" ? "coding-agent" : "user",
        operation_id: operation,
      };
      if (route === "managed") {
        const response = await fetch(
          `/api/v2/runtimes/resolve?image=${encodeURIComponent(image)}`,
        );
        const runtime = await response.json();
        if (!response.ok) throw Error(runtime.detail);
        body.runtime = {
          image: runtime.image,
          solver: "Configured recipe runtime",
          provenance: `User-selected local image ${image}`,
        };
        body.budget_usd = budget;
        body.policy = {
          max_candidates: iterations,
          min_candidates: Math.min(2, iterations),
        };
      }
      const response = await fetch(
        route === "managed"
          ? "/api/v2/managed-experiments"
          : "/api/v2/experiments",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
      );
      const result = await response.json();
      if (!response.ok)
        throw Error(
          typeof result.detail === "string"
            ? result.detail
            : JSON.stringify(result.detail),
        );
      onStarted(result.object_id);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className={s.overlay}>
      <section
        className={s.dialog}
        role="dialog"
        aria-modal="true"
        aria-label="New object"
      >
        <div className={s.sectionHeading}>
          <h2>New object</h2>
          <button className={s.quiet} onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className={s.actions} aria-label="Choose a driver">
          <button
            type="button"
            className={s.quiet}
            aria-pressed={route === "managed"}
            onClick={() => setRoute("managed")}
          >
            Built-in agent
          </button>
          <button
            type="button"
            className={s.quiet}
            aria-pressed={route === "external"}
            onClick={() => setRoute("external")}
          >
            External agent
          </button>
          <button
            type="button"
            className={s.quiet}
            onClick={() => setRoute("advanced")}
          >
            Advanced YAML / custom task
          </button>
        </div>
        <p>
          {route === "managed"
            ? "Describe the request. The built-in agent defines and verifies tests before generating designs."
            : "Your coding agent supplies reasoning and CAD. Da Vinci runs the tests and preserves evidence. No model key is required."}
        </p>
        {route === "managed" && (
          <p className={s.muted}>
            Automatic test authoring currently supports rectangular cantilever
            screening. Unsupported physics stops before design generation.{" "}
            <a href="/docs/managed-requests/">Scope and setup</a>
          </p>
        )}
        {route === "managed" && connection && !connection.managed_available && (
          <p role="status" className={s.error}>
            Configure OPENAI_API_KEY on the server and restart the service.
            Credentials are never entered in this browser.
          </p>
        )}
        <form onSubmit={submit}>
          <div className={s.fields}>
            <label>
              Object name
              <input
                required
                maxLength={100}
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  setSlug(
                    e.target.value
                      .toLowerCase()
                      .replace(/[^a-z0-9]+/g, "-")
                      .replace(/^-|-$/g, "")
                      .slice(0, 64),
                  );
                }}
              />
            </label>
            <label>
              Object ID
              <input
                required
                pattern="[a-z][a-z0-9-]{0,63}"
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
              />
            </label>
          </div>
          <label>
            Engineering request
            <textarea
              required
              maxLength={12000}
              rows={5}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe the part, loads, material, fixed interfaces, acceptance limits and objective."
            />
          </label>
          {route === "managed" && (
            <>
              <label>
                Installed solver image
                <input
                  required
                  value={image}
                  onChange={(e) => setImage(e.target.value)}
                />
              </label>
              <div className={s.fields}>
                <label>
                  Candidate limit
                  <input
                    required
                    type="number"
                    min={1}
                    max={20}
                    value={iterations}
                    onChange={(e) => setIterations(Number(e.target.value))}
                  />
                </label>
                <label>
                  API budget (USD)
                  <input
                    required
                    type="number"
                    min={0.01}
                    max={1000}
                    step="any"
                    value={budget}
                    onChange={(e) => setBudget(Number(e.target.value))}
                  />
                </label>
              </div>
            </>
          )}
          {error && (
            <p role="alert" className={s.error}>
              {error}
            </p>
          )}
          <button
            className={s.button}
            disabled={
              busy || (route === "managed" && !connection?.managed_available)
            }
          >
            {busy
              ? "Opening…"
              : route === "managed"
                ? "Start managed request"
                : "Open external experiment"}
          </button>
        </form>
      </section>
    </div>
  );
}
