from __future__ import annotations

from app.agents.coordinator import run_agentic_research
from app.models import ResearchReport, ResearchRequest


def run_research(request: ResearchRequest) -> ResearchReport:
    return run_agentic_research(request)
