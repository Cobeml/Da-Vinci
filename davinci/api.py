import asyncio
import io
import json
import secrets
import zipfile

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse

from davinci.config import Settings
from davinci.engine import Engine
from davinci.models import RunRequest


def create_app(settings=None):
    settings = settings or Settings()
    engine = Engine(settings)

    def authorize(request: Request):
        if settings.davinci_api_token:
            supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
            if not secrets.compare_digest(supplied, settings.davinci_api_token):
                raise HTTPException(401, "Invalid API token")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") != settings.davinci_web_url.rstrip("/"):
                raise HTTPException(403, "Unexpected request origin")

    app = FastAPI(title="Da Vinci CAD Harness", version="0.1.0", dependencies=[Depends(authorize)])
    app.state.engine = engine

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "storage": engine.store.backend,
            "mode": settings.davinci_mode,
            "live_available": bool(settings.openai_api_key),
            "cad_available": engine.runner.available(),
            "atlas_configured": bool(settings.mongodb_uri),
        }

    @app.get("/api/workbench")
    def workbench():
        runs = engine.store.list("runs", limit=20, reverse=True)
        return {
            "runs": runs,
            "candidates": engine.store.list("candidates", limit=100, reverse=True),
            "evaluations": engine.store.list("evaluations", limit=100, reverse=True),
            "events": engine.store.list("events", limit=100, reverse=True),
            "tools": [{k: v for k, v in t.items() if k != "source"} for t in engine.store.list("tools")],
            "releases": engine.store.list("releases", limit=30, reverse=True),
            "champions": engine.store.list("champions", limit=50, reverse=True),
            "assemblies": engine.store.list("assemblies", limit=50, reverse=True),
            "active_release_id": engine.improvements.active()["_id"],
            "memory_count": len(engine.store.list("memories", limit=10000)),
            "storage": engine.store.backend,
            "live_available": bool(settings.openai_api_key),
        }

    @app.post("/api/projects/{project_id}/runs", status_code=201)
    def start(project_id: str, request: RunRequest):
        if project_id != "uas-demo":
            raise HTTPException(404, "Unknown project")
        if not engine.runner.available():
            raise HTTPException(
                503, "CAD image unavailable. Run docker compose --profile build build cad-image."
            )
        try:
            return engine.start(request)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        run = engine.store.get("runs", run_id)
        if not run:
            raise HTTPException(404, "Run not found")
        return run

    @app.post("/api/runs/{run_id}/stop")
    def stop(run_id: str):
        result = engine.stop(run_id)
        if not result:
            raise HTTPException(409, "Run is not active")
        return result

    @app.get("/api/runs/{run_id}/events")
    async def stream(run_id: str, request: Request):
        async def events():
            seen = set()
            last = request.headers.get("last-event-id")
            initial = engine.store.list("events", {"run_id": run_id}, limit=10000)
            if last:
                for item in initial:
                    seen.add(item["_id"])
                    if item["_id"] == last:
                        break
            while not await request.is_disconnected():
                for item in engine.store.list("events", {"run_id": run_id}, limit=10000):
                    if item["_id"] not in seen:
                        seen.add(item["_id"])
                        yield f"id: {item['_id']}\ndata: {json.dumps(item)}\n\n"
                yield ": heartbeat\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/candidates/{id}")
    def candidate(id: str):
        item = engine.store.get("candidates", id)
        if not item:
            raise HTTPException(404, "Candidate not found")
        return {**item, "evaluations": engine.store.list("evaluations", {"candidate_id": id})}

    @app.get("/api/artifacts/{id}")
    def artifact(id: str):
        info = engine.store.get("artifacts", id)
        if not info:
            raise HTTPException(404, "Artifact not found")
        return Response(
            engine.artifacts.read(id),
            media_type=info["media_type"],
            headers={
                "Content-Disposition": f'inline; filename="{info["name"]}"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.get("/api/releases/active/ui", response_class=HTMLResponse)
    def ui_note():
        release = engine.improvements.active()
        content = (
            engine.artifacts.read(release["ui_artifact_id"]).decode()
            if release.get("ui_artifact_id")
            else '<div style="color:#a5ada7;font:12px monospace;padding:12px">BASELINE POLICY · Geometry screening active</div>'
        )
        return HTMLResponse(
            content,
            headers={
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
                "Cache-Control": "no-store",
            },
        )

    @app.get("/api/projects/{id}/champions")
    def champions(id: str):
        rows = engine.store.list("champions", {"project_id": id})
        frontier = [
            a
            for a in rows
            if not any(
                b["mass_kg"] <= a["mass_kg"]
                and b["induced_drag_n"] <= a["induced_drag_n"]
                and (b["mass_kg"] < a["mass_kg"] or b["induced_drag_n"] < a["induced_drag_n"])
                for b in rows
            )
        ]
        return {"frontier": frontier, "champion": min(rows, key=lambda r: r["objective"]) if rows else None}

    @app.get("/api/runs/{id}/bundle")
    def bundle(id: str):
        run = engine.store.get("runs", id)
        if not run:
            raise HTTPException(404, "Run not found")
        buffer = io.BytesIO()
        collections = (
            "candidates",
            "evaluations",
            "assemblies",
            "agent_states",
            "events",
            "champions",
            "tools",
            "releases",
            "memories",
        )
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("run.json", json.dumps(run, indent=2))
            archive.writestr(
                "specification.json",
                json.dumps(engine.store.get("specifications", run["specification_id"]), indent=2),
            )
            artifact_ids = set()
            for name in collections:
                rows = engine.store.list(name, {"run_id": id}, limit=10000)
                archive.writestr(name + ".json", json.dumps(rows, indent=2))
                for row in rows:
                    artifact_ids.update(row.get("artifacts", {}).values())
                    for field in ("source_bundle_artifact_id", "bundle_artifact_id", "ui_artifact_id"):
                        if row.get(field):
                            artifact_ids.add(row[field])
            for artifact_id in artifact_ids:
                info = engine.store.get("artifacts", artifact_id)
                archive.writestr(
                    f"artifacts/{artifact_id}/{info['name']}", engine.artifacts.read(artifact_id)
                )
        return Response(
            buffer.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{id}.zip"'},
        )

    @app.post("/api/candidates/{id}/inspect")
    def inspect(id: str, tasks: BackgroundTasks):
        candidate = engine.store.get("candidates", id)
        if not candidate:
            raise HTTPException(404, "Candidate not found")
        from davinci.browser import inspect_candidate

        tasks.add_task(inspect_candidate, settings, id)
        return {"status": "scheduled", "candidate_id": id}

    return app


app = create_app()
