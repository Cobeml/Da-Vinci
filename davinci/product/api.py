import asyncio
import json
import threading
from contextlib import asynccontextmanager
from importlib.resources import files
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from davinci.product.engine import Engine
from davinci.product.tasks import builtin, template_config


class Submission(BaseModel):
    yaml: str = Field(max_length=100000)


def create_app(workspace: Path, *, engine=None, run_worker=True):
    engine = engine or Engine(workspace)

    @asynccontextmanager
    async def lifespan(app):
        thread = None
        if run_worker:
            engine.recover()
            thread = threading.Thread(target=engine.work, name="davinci-worker", daemon=True)
            thread.start()
        yield
        engine.shutdown.set()
        if thread:
            await asyncio.to_thread(thread.join, 15)

    app = FastAPI(title="Da Vinci workspace", version="0.2.0", lifespan=lifespan)
    app.state.engine = engine

    @app.middleware("http")
    async def local_boundary(request, call_next):
        # Bind only to loopback and reject DNS rebinding/cross-origin writes.
        allowed = {f"127.0.0.1:{engine.options.port}", f"localhost:{engine.options.port}", "testserver"}
        host = request.headers.get("host", "")
        if host not in allowed:
            return JSONResponse({"detail": "Unexpected host"}, status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and origin not in {f"http://{h}" for h in allowed}:
                return JSONResponse({"detail": "Unexpected origin"}, status_code=403)
            if not request.headers.get("content-type", "").startswith("application/json"):
                return JSONResponse({"detail": "JSON request required"}, status_code=415)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(ValueError)
    async def bad_value(request, exc):
        message = "Invalid configuration: " + str(exc) if isinstance(exc, ValidationError) else str(exc)
        return JSONResponse({"detail": message[:3000]}, status_code=422)

    @app.exception_handler(FileNotFoundError)
    async def missing_file(request, exc):
        return JSONResponse(
            {"detail": "Task resource not found. Check the task directory and manifest files."},
            status_code=422,
        )

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({"detail": "Record not found"}, status_code=404)

    @app.get("/api/v1/health")
    def health():
        return {
            "status": "ok",
            "storage": engine.store.backend,
            "live_available": bool(engine.credentials.openai_api_key),
            "model": engine.options.model,
        }

    @app.get("/api/v1/tasks")
    def tasks():
        return [
            {
                **{k: builtin(n)[k] for k in ("name", "metrics", "parameters_schema")},
                "id": n,
                "yaml": yaml.safe_dump(template_config(n), sort_keys=False),
            }
            for n in ("sensor", "gripper", "vtol")
        ] + [
            {
                "id": "custom",
                "name": "Custom Python task",
                "metrics": {},
                "yaml": yaml.safe_dump(template_config("custom"), sort_keys=False),
            }
        ]

    @app.post("/api/v1/validate")
    def validate(body: Submission):
        config, task = engine.validate(body.yaml)
        return {"config": config.model_dump(), "task_version": task["version"], "metrics": task["metrics"]}

    @app.get("/api/v1/objects")
    def objects():
        result = []
        for obj in engine.store.list("objects", limit=10000, reverse=True):
            detail = engine.detail(obj["_id"])
            latest = detail["runs"][0] if detail["runs"] else None
            candidates = [c for c in detail["designs"] if latest and c["run_id"] == latest["_id"]]
            best = next((c for c in candidates if c["_id"] == latest["best_id"]), None) if latest else None
            preview = best or next(
                (c for c in reversed(candidates) if c.get("artifacts", {}).get("model.glb")), None
            )
            baseline = next(
                (
                    c
                    for c in candidates
                    if c["iteration"] == 0 and c.get("evaluation") and c["evaluation"]["outcome"] == "passed"
                ),
                None,
            )
            improvement = None
            if best and baseline:
                metric = latest["config"]["objective"]["metric"]
                initial = baseline["evaluation"]["metrics"][metric]["value"]
                value = best["evaluation"]["metrics"][metric]["value"]
                if initial:
                    improvement = (
                        100
                        * (value - initial)
                        / abs(initial)
                        * (-1 if latest["config"]["objective"]["direction"] == "minimize" else 1)
                    )
            result.append(
                {
                    **obj,
                    "run": latest,
                    "preview": preview,
                    "iteration_count": len(detail["designs"]),
                    "improvement_percent": improvement,
                }
            )
        return result

    @app.get("/api/v1/objects/{object_id}")
    def detail(object_id: str):
        return engine.detail(object_id)

    @app.post("/api/v1/runs", status_code=201)
    def start(body: Submission):
        try:
            result = engine.start(body.yaml)
            return {"id": result["_id"], "object_id": result["object_id"], "status": result["status"]}
        except ValueError as exc:
            if "Another run" in str(exc):
                raise HTTPException(409, str(exc)) from exc
            raise

    @app.get("/api/v1/runs/{run_id}")
    def run(run_id: str):
        result = engine.store.get("runs", run_id)
        if not result:
            raise KeyError(run_id)
        return {k: v for k, v in result.items() if k != "task"}

    @app.post("/api/v1/runs/{run_id}/stop")
    def stop(run_id: str):
        return {"status": engine.stop(run_id)["status"]}

    @app.post("/api/v1/runs/{run_id}/resume")
    def resume(run_id: str):
        return {"status": engine.resume(run_id)["status"]}

    @app.get("/api/v1/runs/{run_id}/yaml")
    def resolved_yaml(run_id: str):
        data = run(run_id)
        return Response(
            yaml.safe_dump(data["config"], sort_keys=False),
            media_type="application/yaml",
            headers={"Content-Disposition": 'attachment; filename="run.yaml"'},
        )

    @app.get("/api/v1/runs/{run_id}/events")
    async def events(run_id: str, request: Request):
        run(run_id)

        async def stream():
            seen = set()
            while not await request.is_disconnected():
                for row in engine.store.list("events", {"run_id": run_id}, limit=10000):
                    if row["_id"] not in seen:
                        seen.add(row["_id"])
                        yield f"id: {row['_id']}\ndata: {json.dumps(row)}\n\n"
                yield ": heartbeat\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/v1/candidates/{candidate_id}")
    def candidate(candidate_id: str):
        c = engine.store.get("candidates", candidate_id)
        if not c:
            raise KeyError(candidate_id)
        return {**c, "evaluation": engine.store.get("evaluations", "evaluation-" + candidate_id)}

    @app.get("/api/v1/artifacts/{artifact_id}")
    def artifact(artifact_id: str):
        record = engine.store.get("artifacts", artifact_id)
        if not record:
            raise KeyError(artifact_id)
        return Response(
            engine.artifacts.read(artifact_id),
            media_type=record["media_type"],
            headers={"Content-Disposition": f'inline; filename="{record["name"]}"'},
        )

    ui = Path(str(files("davinci.product").joinpath("static")))

    @app.get("/{path:path}")
    def static(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Unknown API route")
        path = path or "index.html"
        target = (ui / path).resolve()
        if not target.is_relative_to(ui.resolve()):
            raise HTTPException(404)
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file() and not Path(path).suffix:
            target = ui / path / "index.html"
        if not target.is_file():
            raise HTTPException(
                404, "UI unavailable. Source developers: run npm run build:ui before building the wheel."
            )
        return FileResponse(target)

    return app
