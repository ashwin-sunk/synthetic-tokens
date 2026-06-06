"""
FastAPI REST service wrapping synthetic_pii_generator.py.

Endpoints:
    GET  /health     — liveness check
    GET  /entities   — list supported entity types
    POST /detect     — detect PII entities in text
    POST /anonymize  — replace PII with synthetic tokens
    POST /both       — detect and anonymize in one call
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from synthetic_pii_generator import (
    ALL_ENTITIES,
    anonymize_text,
    build_pipeline,
    detect_pii,
)

# ---------------------------------------------------------------------------
# App state
# ---------------------------------------------------------------------------

_state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    analyzer, anonymizer, operators = build_pipeline()
    _state["analyzer"] = analyzer
    _state["anonymizer"] = anonymizer
    _state["operators"] = operators
    yield
    _state.clear()


app = FastAPI(
    title="Synthetic PII API",
    description="Detect and anonymize PII/PHI/PCI using GLiNER + Presidio + Faker.",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class TextRequest(BaseModel):
    text: str


class DetectedEntity(BaseModel):
    entity_type: str
    start: int
    end: int
    score: float
    value: str


class DetectResponse(BaseModel):
    entities: list[DetectedEntity]
    count: int


class AnonymizeResponse(BaseModel):
    anonymized_text: str


class BothResponse(BaseModel):
    entities: list[DetectedEntity]
    count: int
    anonymized_text: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_detected(text: str, results: list) -> list[DetectedEntity]:
    return [
        DetectedEntity(
            entity_type=r.entity_type,
            start=r.start,
            end=r.end,
            score=round(r.score, 4),
            value=text[r.start : r.end],
        )
        for r in sorted(results, key=lambda x: x.start)
    ]


def _pipeline():
    if not _state:
        raise HTTPException(status_code=503, detail="Pipeline not ready.")
    return _state["analyzer"], _state["anonymizer"], _state["operators"]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health", summary="Liveness check")
def health():
    ready = bool(_state)
    return {"status": "ok" if ready else "initializing", "pipeline_ready": ready}


@app.get("/entities", summary="List supported entity types")
def entities():
    return {"entities": ALL_ENTITIES, "count": len(ALL_ENTITIES)}


@app.post("/detect", response_model=DetectResponse, summary="Detect PII entities")
def detect(req: TextRequest):
    analyzer, _, _ = _pipeline()
    results = detect_pii(req.text, analyzer)
    return DetectResponse(
        entities=_to_detected(req.text, results),
        count=len(results),
    )


@app.post("/anonymize", response_model=AnonymizeResponse, summary="Anonymize PII with synthetic tokens")
def anonymize(req: TextRequest):
    analyzer, anonymizer, operators = _pipeline()
    anon_text, _ = anonymize_text(req.text, analyzer, anonymizer, operators)
    return AnonymizeResponse(anonymized_text=anon_text)


@app.post("/both", response_model=BothResponse, summary="Detect and anonymize in one call")
def both(req: TextRequest):
    analyzer, anonymizer, operators = _pipeline()
    anon_text, results = anonymize_text(req.text, analyzer, anonymizer, operators)
    return BothResponse(
        entities=_to_detected(req.text, results),
        count=len(results),
        anonymized_text=anon_text,
    )
