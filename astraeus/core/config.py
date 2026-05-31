import json
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

def load_config(filepath: str = "config.json") -> Dict[str, Any]:
    """Loads configuration from a JSON file and validates essential keys."""
    if not os.path.exists(filepath):
        logger.warning(f"Configuration file not found at {filepath}")
        return {}
        
    try:
        with open(filepath, "r") as f:
            config = json.load(f)
            
        validate_config(config)
        return config
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse config.json: {e}")
        return {}

def validate_config(config: Dict[str, Any]) -> None:
    """Validates the presence of required keys in the configuration."""
    required_keys = ["llm_provider", "llm_model", "api_keys"]
    
    missing_keys = [key for key in required_keys if key not in config]
    
    if missing_keys:
        logger.warning(f"config.json is missing required keys: {missing_keys}")
    else:
        logger.info("config.json validated successfully.")
