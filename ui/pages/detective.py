"""Detective module for the dashboard."""

import streamlit as st
import pandas as pd
import json
import plotly.express as px
from astraeus.analysis.detection import detect_transit_candidate

def render(main_panel, right_panel) -> None:
    """Render the Detective module."""
    with main_panel:
        st.title("Exoplanet Detective")
        st.markdown("Upload your light curve data to detect transit candidates using the BLS method.")
        
        uploaded_file = st.file_uploader("Upload raw data (CSV with 'time' and 'flux' columns)", type=['csv'])
        
        if uploaded_file is not None:
            try:
                df = pd.read_csv(uploaded_file)
                if 'time' not in df.columns or 'flux' not in df.columns:
                    st.error("Uploaded CSV must contain 'time' and 'flux' columns.")
                else:
                    st.success(f"Data loaded successfully: {len(df)} points.")
                    
                    if st.button("Run Detection"):
                        with st.spinner("Running Box Least Squares analysis..."):
                            results = detect_transit_candidate(df['time'], df['flux'])
                            
                            # Separate the periodogram data from the stats
                            periodogram_data = results.pop('periodogram')
                            
                            # Store in session state so it persists across reruns
                            st.session_state['detective_results'] = results
                            st.session_state['detective_plot_data'] = periodogram_data
                            
            except Exception as e:
                st.error(f"Error reading file: {e}")
                
        # Display Plot if we have results in session state
        if 'detective_plot_data' in st.session_state:
            st.subheader("BLS Periodogram")
            plot_data = st.session_state['detective_plot_data']
            fig = px.line(
                x=plot_data['periods'], 
                y=plot_data['powers'], 
                labels={'x': 'Period (days)', 'y': 'Power'},
                title="BLS Power vs. Period"
            )
            st.plotly_chart(fig, use_container_width=True)
            
    if right_panel:
        with right_panel:
            st.subheader("Detection Report")
            if 'detective_results' in st.session_state:
                st.json(st.session_state['detective_results'])
            else:
                st.info("Awaiting detection run...")
