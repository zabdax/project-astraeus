import json
import os
import uuid
import hashlib
from datetime import datetime
from typing import Dict, Any, List

LOG_FILE = os.path.join("logs", "experiments.json")

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
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    
    exp_uuid = str(uuid.uuid4())
    dataset_hash = generate_dataset_hash(metadata)
    
    experiment_entry = {
        "id": exp_uuid,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "dataset_hash": dataset_hash,
        "params": params,
        "metadata": metadata,
        "fig_paths": fig_paths
    }
    
    history = load_experiment_history()
    history.append(experiment_entry)
    
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=4)
        
    return exp_uuid

def load_experiment_history() -> List[Dict[str, Any]]:
    """
    Load all past experiment runs from the log file.
    
    Returns:
        list: A list of dictionaries representing past experiment runs.
    """
    if not os.path.exists(LOG_FILE):
        return []
    
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []

class ExperimentLedger:
    def __init__(self, ledger_path: str = "logs/experiments.json"):
        self.ledger_path = ledger_path
        os.makedirs(os.path.dirname(self.ledger_path), exist_ok=True)

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
            "timestamp_logged": datetime.utcnow().isoformat() + "Z",
            "target_metadata": target_metadata,
            "calculated_period": calculated_period,
            "signal_confidence": signal_confidence,
            "tracking_statistics": tracking_statistics,
            "data_source": data_source,
            "pipeline_timestamps": pipeline_timestamps or {}
        }

        ledger_data = []
        if os.path.exists(self.ledger_path):
            try:
                with open(self.ledger_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        ledger_data = json.loads(content)
                        if not isinstance(ledger_data, list):
                            ledger_data = [ledger_data]
            except (json.JSONDecodeError, IOError) as e:
                print(f"[Warning] Could not parse existing ledger '{self.ledger_path}': {e}.")

        ledger_data.append(entry)

        temp_path = f"{self.ledger_path}.tmp"
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(ledger_data, f, indent=4, ensure_ascii=False)
            os.replace(temp_path, self.ledger_path)
        except IOError as e:
            print(f"[Error] Failed to append to experiment ledger: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise
