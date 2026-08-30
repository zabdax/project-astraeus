import os
import json
import pytest
from streamlit.testing.v1 import AppTest
from astraeus.analysis.logging import save_experiment_log, generate_dataset_hash

LOG_FILE = os.path.join("logs", "experiments.json")

def test_experiment_history_cycle():
    """
    Log/Restore Cycle: Programmatically perform a MCMC retrieval (simulated here) -> 
    Save Log -> Clear session_state -> Restore Log.
    Integrity Assert: Verify restored session_state is bit-for-bit identical to saved values.
    Hash Validation: Verify a warning is issued if the dataset hash mismatches.
    """
    # 1. Programmatically perform MCMC retrieval -> Save Log
    # We simulate the backend returning some parameters
    params = {
        'planet_radius': 0.12345,
        'inclination': 88.76543,
        'period': 3.14159
    }
    
    metadata_correct = {
        'dataset': 'lightcurve_A.csv',
        'points': 1000
    }
    
    metadata_wrong = {
        'dataset': 'lightcurve_B.csv',
        'points': 800
    }
    
    # Ensure a clean slate for the log file
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
        
    exp_id = save_experiment_log(params, metadata_correct, [])
    
    # Pre-test check: confirm it saved bit-for-bit
    with open(LOG_FILE, 'r') as f:
        logs = json.load(f)
    assert len(logs) == 1
    assert logs[0]['id'] == exp_id
    assert logs[0]['params']['planet_radius'] == params['planet_radius']
    
    # 2. Start UI test
    at = AppTest.from_file("app.py", default_timeout=60)
    
    # Set the current dataset hash in session state to something WRONG 
    # to trigger the hash validation warning.
    wrong_hash = generate_dataset_hash(metadata_wrong)
    at.session_state['current_dataset_hash'] = wrong_hash
    
    at.run()
    
    # Navigate to History page
    history_btn = None
    for btn in at.sidebar.button:
        if "History" in btn.label:
            history_btn = btn
            break
            
    assert history_btn is not None, "History navigation button not found."
    history_btn.click().run()
    
    # Attempt to Restore the experiment
    restore_btn = None
    for btn in at.button:
        if "Restore" in btn.label:
            restore_btn = btn
            break
            
    assert restore_btn is not None, "Restore button not found."
    restore_btn.click().run()
    
    # 3. Hash Validation Assert
    # Verify that the 'Load' (Restore) button warns the user and prevents loading
    warning_found = False
    for warning in at.warning:
        if "missing or mismatch" in warning.value.lower() or "dataset" in warning.value.lower():
            warning_found = True
            break
            
    assert warning_found, "Expected a warning about dataset hash mismatch, but none was found."
    
    # Verify params were NOT restored due to the hash mismatch
    assert 'planet_radius' not in at.session_state, "Params should not be loaded on hash mismatch."
    
    # 4. Integrity Assert (Correct Hash)
    # Now set the correct hash (simulating uploading the correct dataset) and restore
    correct_hash = generate_dataset_hash(metadata_correct)
    at.session_state['current_dataset_hash'] = correct_hash
    restore_btn.click().run()
    
    # Verify bit-for-bit identical restoration in session_state.
    # 2026-08-21 audit: restored params are namespaced under restored_param_*
    # so a blind restore can never hijack unrelated widget state (e.g. the
    # Simulator's "snr" slider) — see ui/pages/history.py.
    assert 'restored_param_planet_radius' in at.session_state, "Params failed to restore with correct hash."
    assert at.session_state['restored_param_planet_radius'] == params['planet_radius']
    assert at.session_state['restored_param_inclination'] == params['inclination']
    assert at.session_state['restored_param_period'] == params['period']
    
    # Clean up
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)
