"""Copilot endpoint for the ASTRAEUS API layer (P3-G).

Evidence-grounded explanation streaming: the caller posts an
``AnalysisResult`` dict plus a question; the server serializes the
*evidence* (candidates, TLS roll-up, capability snapshot, warnings —
never prose, never a verdict the engine did not compute) and asks the
configured LLM to explain it. The stream is labelled AI-INTERPRETED at
every layer: the UI must render it as interpretation, not measurement.

Honesty rules (PRD §10/§12):
- No provider configured (or provider SDK missing) is a *streamed*
  ``unavailable`` message, never a 500 and never a silent mock. The live
  Streamlit copilot is a hardcoded mock; this endpoint refuses to be one.
- The LLM's numeric claims are unverified prose: the stream carries the
  evidence digest alongside so the UI can show both.
- Engine boundary: ``LLMClient`` is imported lazily inside the request so
  the web stack never pulls the engine at import time.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field


class CopilotRequest(BaseModel):
    """Explain this result. ``provider`` overrides the server default."""

    model_config = ConfigDict(extra="forbid")

    result: dict[str, Any] = Field(..., description="AnalysisResult dict to explain")
    question: str = Field(
        default="Explain these transit-search results for a non-expert.",
        max_length=2000,
    )
    provider: str | None = Field(
        default=None,
        description="openai | anthropic | google | ollama; null = server default",
    )


def _evidence_digest(result: dict[str, Any]) -> str:
    """The grounded facts the LLM may talk about. Deliberately narrow."""
    candidates = result.get("candidates") or []
    lines = [
        f"status={result.get('status')}",
        f"n_candidates={len(candidates)}",
        f"tls={json.dumps(result.get('tls'), default=str)}",
        f"capability={json.dumps(result.get('capability_snapshot'), default=str)}",
        f"warnings={json.dumps(result.get('warnings'), default=str)[:500]}",
    ]
    for cand in candidates[:10]:
        tls = cand.get("tls") or {}
        lines.append(
            "candidate "
            f"{cand.get('candidate_id')}: period_days={cand.get('period_days')} "
            f"snr={cand.get('snr')} depth={cand.get('depth_fraction')} "
            f"tls_outcome={tls.get('outcome')} tls_sde={tls.get('sde')}"
        )
    return "\n".join(lines)


def _sse(payload: dict[str, Any]) -> bytes:
    return ("data: " + json.dumps(payload, default=str) + "\n\n").encode("utf-8")


def build_copilot_router() -> APIRouter:
    from astraeus.api.routes import require_user_dep

    router = APIRouter()

    @router.post(
        "/copilot/explain",
        responses={
            200: {"content": {"text/event-stream": {}}},
            401: {},
            422: {},
        },
        summary="Stream an evidence-grounded explanation (AI-INTERPRETED)",
    )
    async def explain(
        body: CopilotRequest,
        request: Request,
        user=Depends(require_user_dep),
    ) -> StreamingResponse:
        _ = user

        async def generate() -> AsyncIterator[bytes]:
            digest = _evidence_digest(body.result)
            yield _sse({"kind": "evidence", "digest": digest})
            try:
                text = await asyncio.wait_for(
                    asyncio.to_thread(_explain_sync, body, digest),
                    timeout=180.0,
                )
            except asyncio.TimeoutError:
                yield _sse({"kind": "error", "error_kind": "timeout", "detail": "LLM call timed out"})
                return
            yield _sse({"kind": "text", "delta": text})
            yield _sse({"kind": "done"})

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router


def _explain_sync(body: CopilotRequest, digest: str) -> str:
    """Blocking LLM call (runs in a thread). Returns prose or an honest
    unavailable marker the route streams verbatim."""
    import os

    from astraeus.core.llm_gateway import LLMClient

    provider = (body.provider or os.environ.get("ASTRAEUS_COPILOT_PROVIDER") or "").strip().lower()
    if not provider or provider == "none":
        return (
            "UNAVAILABLE: no copilot provider is configured. Set "
            "ASTRAEUS_COPILOT_PROVIDER (openai | anthropic | google | ollama) "
            "and the matching API key on the server, or a provider in "
            "Settings → Copilot keys. Nothing was sent anywhere."
        )
    try:
        client = LLMClient(provider=provider)
        answer = client.generate_response(body.question, context=digest)
    except Exception as exc:  # fail honest, never mock
        return f"UNAVAILABLE: copilot call failed ({type(exc).__name__}: {exc}). Nothing was inferred."
    if isinstance(answer, str) and answer.startswith("Error:"):
        # The gateway's own missing-SDK signal — surface it, don't launder it.
        return f"UNAVAILABLE: {answer}"
    return str(answer)
