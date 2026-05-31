"""Sensitivity Lab module for interactive transit model fitting."""

import streamlit as st
import numpy as np
import plotly.graph_objects as go
from astraeus.core.sensitivity_engine import get_model_curve

def render(main_panel, right_panel) -> None:
    """Render the Sensitivity Lab module."""
    
    # 1. Generate or load a reference dataset (mock data for now)
    # Cache it so it doesn't regenerate on every slider move
    @st.cache_data
    def get_reference_data():
        np.random.seed(42)
        # Zoom in on the transit event (phase around 0)
        t = np.linspace(-0.15, 0.15, 600)
        # Mock transit true parameters
        true_params = {
            'period': 1.0,
            't0': 0.0,
            'rp_rs': 0.1,
            'a_rs': 15.0,
            'inc': 90.0
        }
        flux_true = get_model_curve(true_params, t)
        noise = np.random.normal(0, 0.0015, len(t))
        return t, flux_true + noise
        
    time_arr, ref_flux = get_reference_data()
    
    # 2. Control Group (Right Panel)
    if right_panel:
        with right_panel:
            st.subheader("Model Controls")
            
            # Sliders
            radius = st.slider("Planet Radius Ratio (Rp/Rs)", 
                               min_value=0.01, max_value=0.30, value=0.05, step=0.01)
            
            inclination = st.slider("Inclination (degrees)", 
                                    min_value=85.0, max_value=90.0, value=87.5, step=0.1)
            
            period = st.slider("Period (days)", 
                               min_value=0.5, max_value=5.0, value=1.0, step=0.1)
                               
            a_rs = st.slider("Semi-major Axis (a/Rs)",
                             min_value=5.0, max_value=30.0, value=10.0, step=1.0)
                             
            limb_darkening = st.slider("Limb Darkening (u1)",
                                       min_value=0.0, max_value=1.0, value=0.0, step=0.1)
                                       
            st.info("Adjust the sliders to fit the model to the reference data.")
    else:
        # Fallback if no right panel
        st.sidebar.subheader("Model Controls")
        radius = st.sidebar.slider("Planet Radius Ratio (Rp/Rs)", 0.01, 0.30, 0.05, 0.01)
        inclination = st.sidebar.slider("Inclination (degrees)", 85.0, 90.0, 87.5, 0.1)
        period = st.sidebar.slider("Period (days)", 0.5, 5.0, 1.0, 0.1)
        a_rs = st.sidebar.slider("Semi-major Axis (a/Rs)", 5.0, 30.0, 10.0, 1.0)
        limb_darkening = st.sidebar.slider("Limb Darkening (u1)", 0.0, 1.0, 0.0, 0.1)

    # 3. Compute Model Curve
    params = {
        'period': period,
        't0': 0.0,
        'rp_rs': radius,
        'a_rs': a_rs,
        'inc': inclination,
        # The sensitivity engine does not yet support limb darkening natively,
        # but we capture it here for future extensions.
        'u1': limb_darkening
    }
    
    model_flux = get_model_curve(params, time_arr)
    
    # 4. Main Panel - Plotting
    with main_panel:
        st.title("Sensitivity Lab")
        st.markdown("Fit a theoretical transit model to the reference dataset interactively.")
        
        fig = go.Figure()
        
        # Reference Data (Scatter)
        fig.add_trace(go.Scatter(
            x=time_arr, 
            y=ref_flux,
            mode='markers',
            marker=dict(size=5, color='rgba(200, 200, 255, 0.5)'),
            name='Reference Data'
        ))
        
        # Model Curve (Line)
        fig.add_trace(go.Scatter(
            x=time_arr, 
            y=model_flux,
            mode='lines',
            line=dict(color='#00ffcc', width=4),
            name='Model Fit'
        ))
        
        fig.update_layout(
            xaxis_title="Time from Mid-Transit (days)",
            yaxis_title="Relative Flux",
            template="plotly_dark",
            margin=dict(l=40, r=40, t=40, b=40),
            hovermode="x unified",
            legend=dict(yanchor="top", y=0.99, xanchor="right", x=0.99)
        )
        
        # Render plot instantly. Use key so Streamlit tracks it properly.
        st.plotly_chart(fig, use_container_width=True, key="sensitivity_plot")
