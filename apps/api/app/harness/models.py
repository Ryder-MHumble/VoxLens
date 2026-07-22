from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


OperatorStatus = Literal["queued", "running", "completed", "resumed", "skipped", "blocked", "failed"]


class OperatorRecord(BaseModel):
    name: str
    version: str = "1"
    status: OperatorStatus = "queued"
    attempts: int = Field(default=0, ge=0)
    startedAt: str = ""
    completedAt: str = ""
    message: str = ""
    inputHash: str = ""
    outputHash: str = ""


class HarnessManifest(BaseModel):
    schemaVersion: Literal[1] = 1
    runId: str
    createdAt: str
    updatedAt: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    operators: dict[str, OperatorRecord] = Field(default_factory=dict)


class HarnessCheckpoint(BaseModel):
    schemaVersion: Literal[1] = 1
    operator: str
    version: str
    inputHash: str
    outputHash: str
    committedAt: str
    payload: Any = None
