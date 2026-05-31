import os
import pytest
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest
from astraeus.analysis.detection import detect_transit_candidate

def test_noise_injection():
    """
    Feed the backend a lightcurve with non-periodic noise.
    Assert that candidate_found (or is_candidate) is False.
    """
    time = np.linspace(0, 10, 500)
    # Random noise with no periodic signal
    np.random.seed(42)
    flux = 1.0 + np.random.normal(0, 0.01, 500)
    
    results = detect_transit_candidate(time, flux, threshold=5.0)
    
    # The prompt refers to 'candidate_found', backend uses 'is_candidate'
    # We will assert that the candidate was not found.
    assert results.get('is_candidate', results.get('candidate_found')) is False, "Expected no candidate to be found for pure noise"


def test_signal_recovery():
    """
    Feed the backend a clean lightcurve with a known period.
    Assert confidence_score > 0.8 and period matches ground truth within 0.05 days.
    """
    time = np.linspace(0, 20, 1000)
    flux = np.ones_like(time)
    
    # Inject a transit signal: period = 3.14 days, duration = 0.1 days, depth = 0.02
    period_true = 3.14
    duration = 0.1
    depth = 0.02
    
    # Simple box transit injection
    phases = (time % period_true)
    transit_mask = (phases < duration / 2) | (phases > period_true - duration / 2)
    flux[transit_mask] -= depth
    
    # Add minimal noise
    np.random.seed(42)
    flux += np.random.normal(0, 0.001, len(time))
    
    results = detect_transit_candidate(time, flux, threshold=5.0)
    
    assert results['confidence_score'] > 0.8, f"Expected confidence > 0.8, got {results['confidence_score']}"
    assert abs(results['period'] - period_true) <= 0.05, f"Expected period ~{period_true}, got {results['period']}"


def test_panel_routing():
    """
    Ensure the backend returns a JSON object and verify that the UI correctly unpacks 
    this object, rendering the plot in the Center and metrics in the Right (Asset) Panel.
    """
    # Create a dummy CSV file with a signal
    test_csv = "dummy_detective.csv"
    time = np.linspace(0, 10, 200)
    flux = np.ones_like(time)
    phases = (time % 2.5)
    flux[phases < 0.1] -= 0.05
    df = pd.DataFrame({'time': time, 'flux': flux})
    df.to_csv(test_csv, index=False)
    
    try:
        from unittest.mock import patch
        with patch("ui.pages.detective.st.file_uploader", return_value=test_csv):
            at = AppTest.from_file("app.py", default_timeout=60)
            at.run()
            
            assert not at.exception, f"App failed to load: {at.exception}"
            
            # Navigate to Detective page
            detective_btn = None
            for btn in at.sidebar.get("button"):
                if "Detective" in btn.label:
                    detective_btn = btn
                    break
                    
            assert detective_btn is not None, "Detective navigation button not found"
            detective_btn.click().run()
            
            run_btn = None
            for btn in at.get("button"):
                if "Run Detection" in btn.label:
                    run_btn = btn
                    break
                    
            assert run_btn is not None, "Run Detection button not found"
            run_btn.click().run()
            
            # Verify Center Panel (Plot)
            subheaders = [sh.value for sh in at.get("subheader")]
            assert "BLS Periodogram" in subheaders, "Center panel plot title (BLS Periodogram) not found"
            assert len(at.get("plotly_chart")) > 0, "Expected a plotly chart to be rendered in the center panel"
            
            # Verify Right (Asset) Panel (Metrics)
            assert "Detection Report" in subheaders, "Right panel title (Detection Report) not found"
            
            # In the right panel, we should have a JSON element containing the results
            assert len(at.get("json")) > 0, "Expected a JSON rendering of metrics in the right panel"
            
            json_content = str(at.get("json")[0].value).lower()
            # Verify the JSON component actually unpacks backend metrics like period and depth
            assert 'period' in json_content or 'confidence_score' in json_content, "Expected backend metrics to be rendered as JSON"

    finally:
        if os.path.exists(test_csv):
            os.remove(test_csv)
