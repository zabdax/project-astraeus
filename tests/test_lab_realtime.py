import time
import pytest
import numpy as np
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from astraeus.core.sensitivity_engine import get_model_curve

def test_performance_get_model_curve():
    """
    Performance Assert: The backend function get_model_curve must execute 
    and return a valid result in < 100ms.
    We test this by calling it directly 50 times to simulate rapid 
    parameter changes from a slider.
    """
    params = {'period': 1.0, 't0': 0.0, 'rp_rs': 0.1, 'a_rs': 15.0, 'inc': 90.0}
    time_array = np.linspace(-0.15, 0.15, 600)
    
    execution_times = []
    
    # Simulate 50 parameter updates
    for i in range(50):
        params['rp_rs'] = 0.05 + (i * 0.002)
        params['inc'] = 85.0 + (i * 0.05)
        
        start_time = time.perf_counter()
        flux = get_model_curve(params, time_array)
        end_time = time.perf_counter()
        
        duration_ms = (end_time - start_time) * 1000.0
        execution_times.append(duration_ms)
        
        # Valid result check
        assert flux is not None, "get_model_curve returned an invalid result"
        assert len(flux) == len(time_array), "Returned flux array length mismatch"
        
    max_duration_ms = max(execution_times)
    # The requirement is execution in < 100ms
    assert max_duration_ms < 100.0, f"Backend execution took {max_duration_ms:.2f}ms, exceeding the 100ms limit."

def test_ui_sync_slider_events():
    """
    Load Test & UI Sync: Use unittest.mock to simulate 50 slider events (Radius/Inclination)
    and ensure that every movement triggers a redraw of the plotly chart in the Center Panel 
    without triggering a full page reload.
    """
    at = AppTest.from_file("app.py", default_timeout=120)
    
    # Patch the function specifically in the lab module namespace to track calls
    with patch('ui.pages.lab.get_model_curve', wraps=get_model_curve) as mock_get_model_curve:
        at.run()
        
        # Navigate to Lab page
        lab_btn = None
        for btn in at.sidebar.get("button"):
            if "Lab" in btn.label:
                lab_btn = btn
                break
                
        assert lab_btn is not None, "Lab navigation button not found"
        lab_btn.click().run()
        
        assert at.session_state.current_route == "Lab", "Did not route to Lab"
        
        # Reset the mock to ignore the initial page load renders
        mock_get_model_curve.reset_mock()
        
        # Locate Radius and Inclination sliders
        radius_slider = None
        inc_slider = None
        for slider in at.get("slider"):
            if "Radius" in slider.label:
                radius_slider = slider
            elif "Inclination" in slider.label:
                inc_slider = slider
                
        assert radius_slider is not None, "Radius slider not found"
        assert inc_slider is not None, "Inclination slider not found"
        
        events_to_simulate = 50
        
        # Simulate 50 rapid slider events
        for i in range(events_to_simulate):
            if i % 2 == 0:
                # Change Radius
                radius_slider.set_value(0.05 + (i * 0.002)).run()
            else:
                # Change Inclination
                inc_slider.set_value(85.0 + (i * 0.05)).run()
                
            # UI Sync Assert: Every slider event must redraw the plotly chart without full page reload
            assert len(at.get("plotly_chart")) > 0, f"Plotly chart failed to redraw on event {i}"
            
        # Verify that the backend was called exactly the number of times we triggered a slider.
        # This confirms that Streamlit handled the events interactively rather than crashing 
        # or doing a hard reload that would reset the mock/state.
        assert mock_get_model_curve.call_count == events_to_simulate, \
            f"Expected {events_to_simulate} backend calls, got {mock_get_model_curve.call_count}"
