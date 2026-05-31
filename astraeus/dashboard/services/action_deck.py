"""Action Deck workflows for explaining and exporting retrieval results."""

from __future__ import annotations

from typing import Any

import numpy as np

from astraeus.analysis.explanation import get_scientific_explanation
from astraeus.analysis.reporting import generate_report
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
    """Generate a report artifact and return its path."""

    return generate_report(
        data_summary=retrieval_summary["params"],
        figures_paths=[],
        discussion_text=explanation,
        output_format=output_format.lower(),
    )
