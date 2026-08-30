"""Action Deck workflows for explaining and exporting retrieval results."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from astraeus.analysis.explanation import get_scientific_explanation
from astraeus.analysis.reporting import generate_academic_report
from astraeus.dashboard.services.mcmc_retrieval import MCMCRetrievalResult


PARAM_NAMES = ["radius_ratio", "inclination_deg", "u1", "u2"]


def build_retrieval_summary(result: MCMCRetrievalResult) -> dict[str, Any]:
    """Build the retrieval payload used by explanation and report generation."""

    sort_idx = np.argsort(result.folded_time)
    residuals = result.folded_flux[sort_idx] - result.theoretical_flux[sort_idx]
    rms = np.sqrt(np.mean(residuals**2))
    median_params = result.median_params

    return {
        "params": {
            name: float(value)
            for name, value in zip(PARAM_NAMES, median_params)
        },
        "uncertainties": {
            name: {
                "lower_bound": float(result.percentiles[index, 0]),
                "upper_bound": float(result.percentiles[index, 2]),
                "minus_error": float(median_params[index] - result.percentiles[index, 0]),
                "plus_error": float(result.percentiles[index, 2] - median_params[index]),
            }
            for index, name in enumerate(PARAM_NAMES)
        },
        "residuals": {
            "rms": float(rms),
            "mean": float(np.mean(residuals)),
            "std": float(np.std(residuals)),
        },
    }


def explain_retrieval(
    retrieval_summary: dict[str, Any],
    provider: str,
    model_name: str,
    api_key: str,
) -> dict[str, str]:
    """Generate a scientific explanation for a retrieval summary."""

    return get_scientific_explanation(
        retrieval_summary["params"],
        retrieval_summary["uncertainties"],
        retrieval_summary["residuals"],
        provider=provider,
        model_name=model_name,
        api_key=api_key,
    )


def export_retrieval_report(
    retrieval_summary: dict[str, Any],
    explanation: dict[str, str],
    output_format: str,
) -> str:
    """Generate a report artifact and return its path.

    Audit fix C4 (2026-08-21): this previously imported a nonexistent
    ``generate_report``, so importing the module raised ImportError and the
    export workflow could never run. It now adapts the retrieval summary to
    the ``generate_academic_report`` payload schema (star_id + candidates)
    and writes the resulting PDF under ``outputs/reports/``.
    """

    fmt = output_format.lower()
    if fmt != "pdf":
        raise ValueError(f"Unsupported report format: '{output_format}' (only 'pdf')")

    params = retrieval_summary.get("params", {})
    residuals = retrieval_summary.get("residuals", {})
    # The retrieval summary carries fit parameters (radius_ratio, ...) but no
    # orbital period; report the quantities it actually has and zero the rest
    # so the report table renders instead of formatting None.
    candidate = {
        "candidate_id": "retrieval_1",
        "planet_id": "retrieval_1",
        "period": 0.0,
        "snr": float(residuals.get("rms", 0.0)),
        "depth": float(params.get("radius_ratio", 0.0)) ** 2,
        "epoch": 0.0,
    }
    metrics_payload = {
        "star_id": "MCMC Retrieval",
        "candidates": [candidate],
        "discussion": dict(explanation),
    }

    pdf_buffer = generate_academic_report(metrics_payload, figures={})
    out_dir = Path("outputs") / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"retrieval_report_{stamp}.pdf"
    out_path.write_bytes(pdf_buffer.getvalue())
    return str(out_path)
