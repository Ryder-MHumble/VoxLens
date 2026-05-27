from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv

from app.brand import brand_payload
from app.capabilities import capabilities_payload
from app.models import ResearchRequest
from app.sample_data import demo_report
from app.services.research_service import run_research
from app.services.research_stream import stream_research
from app.services.run_queue import RunManager

load_dotenv()

app = FastAPI(title="VoxLens API", version="0.1.0")
run_manager = RunManager()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:8090",
        "http://127.0.0.1:8090",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    await run_manager.start()


@app.on_event("shutdown")
async def shutdown() -> None:
    await run_manager.stop()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "product": "VoxLens"}


@app.get("/api/brand")
def get_brand(lang: str = "zh"):
    return brand_payload("en" if lang == "en" else "zh")


@app.get("/api/capabilities")
def get_capabilities():
    return capabilities_payload()


@app.get("/api/demo-report")
def get_demo_report(lang: str = "zh"):
    return demo_report("en" if lang == "en" else "zh")


@app.post("/api/research")
def research(request: ResearchRequest):
    return run_research(request)


@app.post("/api/research/stream")
def research_stream(request: ResearchRequest):
    return StreamingResponse(
        stream_research(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/runs", status_code=202)
async def create_run(request: ResearchRequest):
    return await run_manager.create_run(request)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    return run_manager.get_run(run_id)


@app.get("/api/runs/{run_id}/report")
def get_run_report(run_id: str):
    record = run_manager.get_run(run_id)
    if not record.report:
        return {"runId": run_id, "status": record.status, "report": None}
    return record.report


@app.get("/api/runs/{run_id}/events")
async def stream_run_events(run_id: str):
    run_manager.get_run(run_id)
    return StreamingResponse(
        run_manager.stream_events(run_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
