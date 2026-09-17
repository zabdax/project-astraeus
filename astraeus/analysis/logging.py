"""Experiment ledger: persistence of run records.

Phase 0 changes (PRD v4.1 §4.4 / §15):

* Artifact paths are resolved through :mod:`astraeus.core.paths` so the
  ledger no longer depends on the process CWD. ``LOG_FILE`` remains
  available as a module attribute for backwards compatibility, but it
  is now a resolved absolute path rather than a CWD-relative string.
* ``datetime.utcnow()`` (deprecated since Python 3.12) replaced with
  timezone-aware ``datetime.now(timezone.utc)``.
* The three ``print()`` calls on the error paths replaced with
  ``logging``; a corrupt-ledger warning is exactly the kind of
  scientific-adjacent event a caller needs to observe.

NOTE (Phase 1): the dataset hash here is ``sha256(metadata)`` and does
NOT identify the dataset -- identical metadata with different cadences
collide.  PRD §5 flags this; the canonical typed ``Dataset`` boundary
and an array-covering hash belong to Phase 1 and are deliberately out of
scope here.
"""

import json
import os
import uuid
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

from astraeus.core.paths import artifact_path, ensure_dir

logger = logging.getLogger("astraeus.analysis.logging")

# Resolved once at import; CWD-independent. Kept as a module-level
# attribute because several historical callers read ``logging.LOG_FILE``
# directly.
LOG_FILE = str(artifact_path("logs", "experiments.json"))


def _now_iso() -> str:
    """Timezone-aware UTC timestamp, replacing deprecated utcnow()."""
    return datetime.now(timezone.utc).isoformat()


def generate_dataset_hash(metadata: Dict[str, Any]) -> str:
    """Generate a hash for the dataset based on metadata."""
    dataset_info = metadata.get("dataset", metadata)
    dataset_str = json.dumps(dataset_info, sort_keys=True, default=str)
    return hashlib.sha256(dataset_str.encode("utf-8")).hexdigest()


def save_experiment_log(params: Dict[str, Any], metadata: Dict[str, Any], fig_paths: List[str]) -> str:
    """
    Save the experiment details to the JSON log file.

    Args:
        params (dict): Parameters of the experiment.
        metadata (dict): Metadata associated with the experiment/dataset.
        fig_paths (list): List of paths to saved figures.

    Returns:
        str: The unique UUID of the experiment run.
    """
    log_path = Path(LOG_FILE)
    ensure_dir(log_path.parent)

    exp_uuid = str(uuid.uuid4())
    dataset_hash = generate_dataset_hash(metadata)

    experiment_entry = {
        "id": exp_uuid,
        "timestamp": _now_iso(),
        "dataset_hash": dataset_hash,
        "params": params,
        "metadata": metadata,
        "fig_paths": fig_paths
    }

    # Audit fix M10 (2026-08-21): load_experiment_history returns [] on ANY
    # parse error; blindly appending to that would overwrite a corrupt (but
    # possibly recoverable) log and destroy the entire history.  Back the
    # corrupt file up before writing instead.
    history: List[Dict[str, Any]] = []
    if log_path.exists():
        loaded = None
        read_error = ""
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            loaded = None
            read_error = str(e)
        if isinstance(loaded, list):
            history = loaded
        else:
            timestamp_tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
            backup_path = log_path.with_name(f"{log_path.name}.corrupt-{timestamp_tag}")
            os.replace(log_path, backup_path)
            logger.warning(
                "Experiment log '%s' was unreadable (%s); original backed "
                "up to '%s'.",
                log_path,
                read_error or "content is not a JSON list",
                backup_path,
            )

    history.append(experiment_entry)

    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=4)

    return exp_uuid


def load_experiment_history() -> List[Dict[str, Any]]:
    """
    Load all past experiment runs from the log file.

    Returns:
        list: A list of dictionaries representing past experiment runs.
    """
    log_path = Path(LOG_FILE)
    if not log_path.exists():
        return []

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


class ExperimentLedger:
    def __init__(self, ledger_path: str = None):
        # Phase 0: default ledger location is now CWD-independent.
        self.ledger_path = ledger_path or str(artifact_path("logs", "experiments.json"))
        # Audit fix M10 (2026-08-21): a bare filename has an empty dirname;
        # os.makedirs("") raises FileNotFoundError.
        ledger_dir = os.path.dirname(self.ledger_path)
        if ledger_dir:
            ensure_dir(Path(ledger_dir))

    def log_candidate(
        self,
        target_metadata: Dict[str, Any],
        calculated_period: float,
        signal_confidence: float,
        tracking_statistics: Dict[str, Any],
        data_source: str,
        pipeline_timestamps: Dict[str, str] = None
    ) -> None:
        """
        Automatically packages pipeline properties and securely appends them to
        the local tracking ledger for absolute reproducibility.
        """
        entry = {
            "timestamp_logged": _now_iso(),
            "target_metadata": target_metadata,
            "calculated_period": calculated_period,
            "signal_confidence": signal_confidence,
            "tracking_statistics": tracking_statistics,
            "data_source": data_source,
            "pipeline_timestamps": pipeline_timestamps or {}
        }

        ledger_data = []
        ledger_path = Path(self.ledger_path)
        if ledger_path.exists():
            try:
                with open(ledger_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        ledger_data = json.loads(content)
                        if not isinstance(ledger_data, list):
                            ledger_data = [ledger_data]
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("Could not parse existing ledger '%s': %s.", ledger_path, e)

        ledger_data.append(entry)

        temp_path = ledger_path.with_name(f"{ledger_path.name}.tmp")
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(ledger_data, f, indent=4, ensure_ascii=False)
            os.replace(temp_path, ledger_path)
        except IOError as e:
            logger.error("Failed to append to experiment ledger: %s", e)
            if temp_path.exists():
                os.remove(temp_path)
            raise
