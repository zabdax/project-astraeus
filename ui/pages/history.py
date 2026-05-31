"""History module for the dashboard."""

import streamlit as st
import pandas as pd
from astraeus.analysis.logging import load_experiment_history

def render(main_panel, right_panel) -> None:
    """Render the History module."""
    with main_panel:
        st.title("Experiment History")
        
        history = load_experiment_history()
        
        if not history:
            st.info("No past experiments found.")
        else:
            # Prepare dataframe data
            df_data = []
            for exp in history:
                row = {
                    "ID": exp.get("id", ""),
                    "Timestamp": exp.get("timestamp", ""),
                    "Dataset Hash": exp.get("dataset_hash", ""),
                }
                # Flatten params into the dataframe for easy viewing
                params = exp.get("params", {})
                for k, v in params.items():
                    row[f"param_{k}"] = v
                df_data.append(row)
                
            df = pd.DataFrame(df_data)
            
            st.subheader("Log Overview")
            st.dataframe(df, use_container_width=True)
            
            st.subheader("Restore Past Experiments")
            st.write("Click 'Restore' to load an experiment's parameters back into the session.")
            
            # Create a row for each experiment with a Restore button
            for exp in history:
                col_time, col_id, col_params, col_action = st.columns([2, 2, 4, 2])
                with col_time:
                    # Show time portion clearly
                    st.text(exp.get("timestamp", "")[:19]) 
                with col_id:
                    # Show shortened UUID
                    st.text(exp.get("id", "")[:8])
                with col_params:
                    # Show preview of params
                    st.caption(str(exp.get("params", {})))
                with col_action:
                    if st.button("Restore", key=f"restore_{exp.get('id')}"):
                        params = exp.get("params", {})
                        for k, v in params.items():
                            st.session_state[k] = v
                        st.success(f"Restored state from experiment {exp.get('id')[:8]}")

    if right_panel:
        with right_panel:
            st.subheader("History Details")
            st.write("View past experiments, compare dataset hashes, and restore parameters for reproducible research.")
