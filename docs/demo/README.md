# Quarto demo

The checked-in Quarto source, JSON evidence, generated includes, SVG plots and PNG captures are sufficient to rebuild the standalone report without Atlas credentials or model calls.

```bash
.venv/bin/python -m scripts.demo_report
```

Output: `runtime/demo/index.html`. Quarto 1.8.21 is installed on the demo host. You can also run `quarto render docs/demo/index.qmd` to produce `docs/demo/index.html` directly. The wrapper refreshes calculated figures and puts the output in the runtime directory. Embedded JSON downloads preserve the underlying evidence. Links to the live app require Tailscale and a running application; the report itself works offline.

## Refresh evidence explicitly

```bash
# Requires the existing runtime/validation/{replay,live1,live3}.zip and report.json.
# Verifies archive artifact hashes and extracts an allowlisted evidence snapshot.
.venv/bin/python -m scripts.demo_evidence

# Also performs eight paired baseline/promoted CadQuery evaluations in Docker.
# No Engine, Atlas connection, environment file or model calls are used.
.venv/bin/python -m scripts.demo_evidence --compare

# Requires the local Next.js app; intercepts API requests with verified exports.
# This captures the real viewer without contacting Atlas or calling inspection APIs.
.venv/bin/python -m scripts.demo_capture

.venv/bin/python -m scripts.demo_report
```

The controlled experiment pins the archive's Docker image digest. Restore/rebuild that pinned CAD environment before refreshing if the image changes. Do not interpret the small, known-failure comparison as held-out generalization. All chart calculations derive from saved evaluation documents; the fixed report narrative corresponds to the September 26 validation cohort.

## Laptop access

```bash
# Start application + two workers when they are not already running.
bash scripts/dev.sh --production
```

In another terminal:

```bash
bash scripts/demo_access.sh up
bash scripts/demo_access.sh status
```

| Surface | MagicDNS URL | Tailscale IP alternative |
|---|---|---|
| Report | http://computer:8085 | http://100.99.98.39:8085 |
| Workbench | http://computer:8086 | http://100.99.98.39:8086 |

These HTTP listeners bind **only to the workstation's Tailscale IPv4 interface**, carried over the encrypted tailnet. The initial Tailscale Serve setup required an unavailable sudo password, so a user-owned Node server serves the one HTML file and transparently forwards workbench connections to loopback port 3215. No daemon configuration change, HTTPS certificate setup or Funnel is used. `.env`, source directories and the backend port are not published. Tailnet access policies still apply.

Listeners run as the transient **`da-vinci-demo.service` user service**, with restart-on-failure. This survives launching-terminal cleanup without sudo. After a **host reboot**, restart the app with `bash scripts/dev.sh --production`, then run `bash scripts/demo_access.sh up` in another terminal. Neither is installed as a boot service. Keep the computer awake during the presentation. If the report works but the app does not, check the application processes first. If neither URL opens on the laptop, confirm both devices are connected to the same tailnet and its access policy permits ports 8085 and 8086. Use the IP alternative to isolate DNS problems. Listener logs are in `runtime/demo/server.log`; startup refuses occupied ports and never broadens the bind address.

To remove only the demo's listeners:

```bash
bash scripts/demo_access.sh down
```

## Five-minute walkthrough

1. Show the assembly and the two agents.
2. Trace candidates through Atlas triggers, evaluation and reflection.
3. Show the controlled 2/4 → 4/4 feasibility comparison, including the mass tradeoff.
4. Explain actual tool creation, policy edits, persisted reuse and rejected patches.
5. Open the app, rotate CAD, inspect a candidate and show Memory / Tools / Archive.

Use replay for a zero-inference interactive run. Keep recorded live Astra results distinct from replay fixtures. The application's existing budget and live-run controls remain in force.

## Verify the demo

```bash
# Offline browser checks: images, tabs, embedded JSON downloads, 390/1280/1440px layout.
.venv/bin/python -m scripts.demo_verify

# Also create one two-round replay via the private address; no model calls.
# Checks CAD downloads, Origin handling, event streaming and completed evaluations.
.venv/bin/python -m scripts.demo_verify --remote http://100.99.98.39:8086
```

The remote check preserves an already-active run by refusing to start another. Its result is written to `runtime/demo/remote-check.json`. A test from the host does not prove laptop access; confirm both URLs on the second device as well.

## Verified on September 26, 2026

- The controlled Docker comparison completed all eight evaluations: baseline 2/4 feasible, promoted 4/4 feasible, with both passing controls preserved.
- The standalone report passed offline Chromium checks for all images, tabs, three embedded JSON downloads and 390/1280/1440px layouts, with no external resource requests or browser errors.
- The private workbench passed geometry rendering, camera/navigation interactions, a real STEP download, same-origin admission, cross-origin rejection and event streaming.
- Tailnet replay `run-23a0aa9b826544d7` completed two rounds and four evaluations with an accepted assembly and no model calls.
- The user confirmed **both URLs open from the Tailscale-connected laptop** after the listener was moved to the user service manager.

These access checks do not alter the frozen report's historical Astra results or claim new paid-model validation.

### Keep the application running after the terminal or agent session ends

The report/proxy service and application service are separate. Build the frontend, stop any foreground `scripts/dev.sh` stack, then run:

```bash
bash scripts/app_service.sh up
bash scripts/demo_access.sh up
```

`da-vinci-workbench.service` supervises the Next.js/API/worker stack on localhost. The existing demo proxy exposes it only on the configured Tailscale address. Logs go to `runtime/demo/workbench.log`. Use `bash scripts/app_service.sh status` or `down` to inspect/stop this application service. These user services survive terminal closure; rerun the `up` commands after a host reboot. After rebuilding the frontend, stop/start the application service to load the new snapshot.
