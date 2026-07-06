import re

with open('f:/solo_leveling_assistant/project-astraeus/app.py', 'r', encoding='utf-8') as f:
    app_code = f.read()

# Add fragment import and orchestrator imports
import_str = """import logging

from astraeus.core.orchestrator import submit_multi_planet_search, get_job_status, cancel_job, JobState
from astraeus.simulation.synthetic import SyntheticTransitScenario, generate_synthetic_transit_series"""
app_code = app_code.replace("import logging", import_str)

# Define the polling fragment before main()
fragment_code = """
@st.fragment(run_every=2)
def render_job_status(job_id):
    status = get_job_status(job_id)
    if not status:
        st.error("Job not found")
        return
        
    state = status.get("status")
    candidates = status.get("candidates", [])
    iteration = status.get("iteration", 0)
    
    # Update payload in session state for rendering below
    payload = st.session_state["discovery_payload"]
    payload["total_iterations_executed"] = iteration
    payload["candidates"] = candidates
    st.session_state["discovery_payload"] = payload
    
    st.markdown("### Search Progress")
    if state in [JobState.PENDING, JobState.RUNNING]:
        st.info(f"Running iteration {iteration}...")
        if st.button("Cancel Analysis", key=f"cancel_{job_id}"):
            cancel_job(job_id)
            st.rerun()
    elif state == JobState.DONE:
        st.success(f"Analysis complete! Found {len(candidates)} candidates.")
        if st.button("Clear Job", key=f"clear_done_{job_id}"):
            st.session_state.pop("active_job_id", None)
            st.rerun()
    elif state == JobState.FAILED:
        st.error(f"Analysis failed: {status.get('error')}")
        if st.button("Clear Job", key=f"clear_fail_{job_id}"):
            st.session_state.pop("active_job_id", None)
            st.rerun()
    elif state == JobState.CANCELLED:
        st.warning("Analysis was cancelled.")
        if st.button("Clear Job", key=f"clear_cancel_{job_id}"):
            st.session_state.pop("active_job_id", None)
            st.rerun()
"""
app_code = app_code.replace("def main():", fragment_code + "\ndef main():")

# Replace "if st.button("Generate Research Manuscript"):" block 
# Actually, I'll put a "Run Analysis" button above "Manuscript Export"

run_analysis_block = """
                if "active_job_id" in st.session_state:
                    render_job_status(st.session_state["active_job_id"])
                else:
                    if st.button("Run Live Analysis"):
                        # Generate a synthetic multi-planet system for demo
                        scenario = SyntheticTransitScenario(duration=100.0)
                        series = generate_synthetic_transit_series(scenario)
                        raw_lc = {
                            "time": series.time_days,
                            "flux": series.observed_flux,
                            "target_name": target,
                            "metadata": {}
                        }
                        
                        # Reset payload candidates
                        st.session_state["discovery_payload"]["candidates"] = []
                        st.session_state["discovery_payload"]["total_iterations_executed"] = 0
                        
                        job_id = submit_multi_planet_search(raw_lc, max_signals=2, snr_floor=snr_threshold)
                        st.session_state["active_job_id"] = job_id
                        st.rerun()
                
                # 4. Two-Stage PDF Compiler Sidebar Handshake
"""
app_code = app_code.replace("# 4. Two-Stage PDF Compiler Sidebar Handshake", run_analysis_block)

with open('f:/solo_leveling_assistant/project-astraeus/app.py', 'w', encoding='utf-8') as f:
    f.write(app_code)

print("App patched successfully!")
