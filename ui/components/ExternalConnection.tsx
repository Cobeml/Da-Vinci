"use client";
import { useEffect, useState } from "react";
import type { Connection } from "./types";
import s from "./workspace.module.css";
const quote = (v: string) => "'" + v.replaceAll("'", "'\\''") + "'";
export default function ExternalConnection({
  experimentId,
}: {
  experimentId?: string;
}) {
  const [connection, setConnection] = useState<Connection>(),
    [copied, setCopied] = useState("");
  useEffect(() => {
    fetch("/api/v2/workspace/connection")
      .then((r) => r.json())
      .then(setConnection)
      .catch(() => {});
  }, []);
  if (!connection) return null;
  const base = `davinci --workspace ${quote(connection.workspace)}`;
  const commands = [
    `${base} service ensure`,
    `${base} external instructions`,
    `${base} external schemas`,
    ...(experimentId
      ? [
          `${base} external status ${quote(experimentId)}`,
          `${base} external validate-plan ${quote(experimentId)}`,
          `${base} memory search 'relevant engineering failures' --experiment ${quote(experimentId)}`,
        ]
      : []),
  ];
  return (
    <details className={s.panel}>
      <summary>External agent connection and commands</summary>
      <p>
        Workspace: <code>{connection.workspace}</code>
        <br />
        Local API: <code>{connection.base_url}</code> · {connection.storage}
      </p>
      <p>
        No model key is needed. Give your coding agent the workspace path and{" "}
        <a href="/api/v2/instructions">public instructions</a>.{" "}
        <a href="/docs/external-agents/">Complete walkthrough</a>
      </p>
      {commands.map((command) => (
        <div className={s.command} key={command}>
          <pre>{command}</pre>
          <button
            className={s.quiet}
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(command);
                setCopied(command);
              } catch {
                setCopied("");
              }
            }}
          >
            {copied === command ? "Copied" : "Copy command"}
          </button>
        </div>
      ))}
    </details>
  );
}
