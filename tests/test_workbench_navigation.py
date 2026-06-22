import os
import pytest
from streamlit.testing.v1 import AppTest
from unittest.mock import patch

def test_workbench_navigation_persistence():
    """
    Test that navigates between pages and ensures state and right-panel assets persist.
    """
    test_csv = "dummy_nav_test.csv"
    with open(test_csv, "w") as f:
        f.write("time,flux\n0.0,1.0\n1.0,0.99\n2.0,1.0\n")
        
    try:
        # Patch the file uploader before the app runs
        with patch("ui.pages.detective.st.file_uploader", return_value=test_csv):
            at = AppTest.from_file("app.py", default_timeout=60)
            at.run()
        
            assert not at.exception, f"App failed to load: {at.exception}"
        
            # 1. Simulator: change a setting (SNR)
            # The default route is Simulation. We change the SNR slider.
            # We find the slider that sets SNR. In simulator.py, it's the first slider.
            snr_slider = None
            for slider in at.get("slider"):
                if "Signal-to-Noise" in slider.label:
                    snr_slider = slider
                    break
            
            assert snr_slider is not None, "Could not find SNR slider in Simulator."
            snr_slider.set_value(123).run()
            
            # Verify session state updated
            assert at.session_state.snr == 123, "Failed to update SNR in session state."
            
            # 2. Navigate to Detective
            detective_btn = None
            for btn in at.sidebar.get("button"):
                if "Detective" in btn.label:
                    detective_btn = btn
                    break
                    
            assert detective_btn is not None, "Detective navigation button not found."
            detective_btn.click().run()
            
            assert at.session_state.current_route == "Detective", "Navigation to Detective failed."
            
            # 3. Run Detection (button is labelled 'Analyze Telemetry & Verify Harmonics'
            # in ui/pages/detective.py:327 and :464; the test was previously
            # keyed on the older 'Run Detection' label).
            run_btn = None
            for btn in at.get("button"):
                if "Analyze Telemetry & Verify Harmonics" in btn.label:
                    run_btn = btn
                    break

            assert run_btn is not None, "Analyze Telemetry & Verify Harmonics button not found."
            run_btn.click().run()
            
        # Verify right panel has the detection report
        subheaders = [sh.value for sh in at.get("subheader")]
        assert "Detection Report" in subheaders, "Detection Report not found in right panel after running detection."
        
        # 4. Navigate to History tab
        history_btn = None
        for btn in at.sidebar.get("button"):
            if "History" in btn.label:
                history_btn = btn
                break
                
        assert history_btn is not None, "History navigation button not found."
        history_btn.click().run()
        
        assert at.session_state.current_route == "History", "Navigation to History failed."
        
        # Asset Check: The Right (Asset) Panel must retain the results even if user navigates to History tab.
        subheaders_history = [sh.value for sh in at.get("subheader")]
        # If the Right Panel clears or changes, it violates persistence.
        assert "Detection Report" in subheaders_history, (
            "Right Panel cleared/replaced its content. Routing logic violates the workbench's persistence requirement."
        )
        
        # 5. Navigate back to Simulator
        sim_btn = None
        for btn in at.sidebar.get("button"):
            if "Simulation" in btn.label:
                sim_btn = btn
                break
                
        assert sim_btn is not None, "Simulation navigation button not found."
        sim_btn.click().run()
        
        assert at.session_state.current_route == "Simulation", "Navigation to Simulation failed."
        
        # Assertion: Input Data / System Configuration must persist in st.session_state
        assert at.session_state.snr == 123, "System Configuration (SNR) did not persist after returning to Simulator."
        
    finally:
        if os.path.exists(test_csv):
            os.remove(test_csv)
