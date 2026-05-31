"""Simulation module for the dashboard."""

import streamlit as st
import streamlit.components.v1 as components
import numpy as np
from astropy import units as u
from types import SimpleNamespace

from astraeus.dashboard.figures import (
    make_light_curve_figure,
    make_residuals_figure,
    make_multi_orbit_animation_html,
)
from astraeus.core.transit_model import generate_multi_planet_transit
from astraeus.dashboard.simulation import semi_major_axis_for_solar_mass
from astraeus.data.preprocessing import inject_gaussian_noise
from astraeus.core.orbital_models import calculate_orbital_position


def render(main_panel, right_panel) -> None:
    """Render the Simulation module."""
    
    if "multi_planets" not in st.session_state:
        st.session_state.multi_planets = [
            {"name": "Planet 1", "radius_ratio": 0.10, "period_days": 3.0, "eccentricity": 0.0, "inclination_degrees": 88.5}
        ]
        
    if "snr" not in st.session_state:
        st.session_state.snr = 200

    with main_panel:
        st.title("ASTRAEUS Transit Dashboard - System Builder")
        
        col_charts, col_controls = st.columns([0.8, 0.2])
        
        with col_controls:
            # Inject professional SVG icon styling for control buttons
            st.markdown("""
<style>
/* ── base control button ── */
div[data-testid="stButton"] > button {
    font-size: 12px !important;
    font-weight: 500 !important;
    letter-spacing: 0.4px !important;
    display: flex !important;
    align-items: center !important;
    gap: 6px !important;
}
/* Add Planet */
div[data-testid="stButton"] > button[kind="secondary"]:has(p:-webkit-any(*, *))  { }
.sim-btn-add    button::before { content: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='13' height='13' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2.2' stroke-linecap='round'%3E%3Cline x1='12' y1='5' x2='12' y2='19'/%3E%3Cline x1='5' y1='12' x2='19' y2='12'/%3E%3C/svg%3E"); display:inline-block; vertical-align:middle; margin-right:5px; }
.sim-btn-reset  button::before { content: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='13' height='13' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8'/%3E%3Cpath d='M3 3v5h5'/%3E%3C/svg%3E"); display:inline-block; vertical-align:middle; margin-right:5px; }
.sim-btn-save   button::before { content: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='13' height='13' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z'/%3E%3Cpolyline points='17 21 17 13 7 13 7 21'/%3E%3Cpolyline points='7 3 7 8 15 8'/%3E%3C/svg%3E"); display:inline-block; vertical-align:middle; margin-right:5px; }
.sim-btn-edit   button::before { content: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='13' height='13' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7'/%3E%3Cpath d='M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z'/%3E%3C/svg%3E"); display:inline-block; vertical-align:middle; margin-right:5px; }
.sim-btn-remove button::before { content: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='13' height='13' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='3 6 5 6 21 6'/%3E%3Cpath d='M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6'/%3E%3Cpath d='M10 11v6'/%3E%3Cpath d='M14 11v6'/%3E%3Cpath d='M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2'/%3E%3C/svg%3E"); display:inline-block; vertical-align:middle; margin-right:5px; }
</style>
""", unsafe_allow_html=True)

            st.session_state.snr = st.slider("Target Signal-to-Noise Ratio (SNR)", 50, 500, st.session_state.snr, 10)

            st.markdown('<div class="sim-btn-add">', unsafe_allow_html=True)
            if st.button("Add Planet", use_container_width=True):
                new_period = 5.0 + 2.0 * len(st.session_state.multi_planets)
                new_name = f"Planet {len(st.session_state.multi_planets) + 1}"
                st.session_state.multi_planets.append(
                    {"name": new_name, "radius_ratio": 0.05, "period_days": new_period, "eccentricity": 0.0, "inclination_degrees": 90.0}
                )
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown('<div class="sim-btn-reset">', unsafe_allow_html=True)
            if st.button("Reset to Default", use_container_width=True):
                st.session_state.multi_planets = [
                    {"name": "Planet 1", "radius_ratio": 0.10, "period_days": 3.0, "eccentricity": 0.0, "inclination_degrees": 88.5}
                ]
                st.session_state.snr = 200
                st.session_state.pop("_orbit_html_key", None)
                st.session_state.pop("_orbit_html", None)
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

            for i, p in enumerate(list(st.session_state.multi_planets)):
                st.markdown("---")

                edit_key = f"edit_name_{i}"
                if edit_key not in st.session_state:
                    st.session_state[edit_key] = False

                if st.session_state[edit_key]:
                    p["name"] = st.text_input("Name", p.get("name", f"Planet {i+1}"), key=f"name_input_{i}", label_visibility="collapsed")
                    st.markdown('<div class="sim-btn-save">', unsafe_allow_html=True)
                    if st.button("Save", key=f"save_{i}", use_container_width=True):
                        st.session_state[edit_key] = False
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f"**{p.get('name', f'Planet {i+1}')}**")
                    st.markdown('<div class="sim-btn-edit">', unsafe_allow_html=True)
                    if st.button("Edit", key=f"edit_btn_{i}", use_container_width=True):
                        st.session_state[edit_key] = True
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)

                st.markdown('<div class="sim-btn-remove">', unsafe_allow_html=True)
                if st.button("Remove", key=f"remove_{i}", use_container_width=True):
                    st.session_state.multi_planets.pop(i)
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

                p["radius_ratio"] = st.slider("Radius Ratio", 0.01, 0.20, p["radius_ratio"], 0.005, key=f"rr_{i}")
                p["period_days"] = st.slider("Period (days)", 0.5, 20.0, float(p["period_days"]), 0.1, key=f"pd_{i}")
                p["eccentricity"] = st.slider("Eccentricity", 0.0, 0.9, p["eccentricity"], 0.01, key=f"ecc_{i}")
                p["inclination_degrees"] = st.slider("Inclination", 80.0, 90.0, p["inclination_degrees"], 0.1, key=f"inc_{i}")

        # Simulation
        samples = 900
        max_period = max([p["period_days"] for p in st.session_state.multi_planets]) if st.session_state.multi_planets else 1.0
        time_days = np.linspace(0.0, max_period, samples)
        time = time_days * u.day
        
        planet_list = []
        orbits = []
        for p in st.session_state.multi_planets:
            sma = semi_major_axis_for_solar_mass(p["period_days"]).to(u.R_sun)
            planet_list.append({
                "R_star": 1.0 * u.R_sun,
                "period": p["period_days"] * u.day,
                "semi_major_axis": sma,
                "eccentricity": p["eccentricity"] * u.dimensionless_unscaled,
                "inclination": p["inclination_degrees"] * u.deg,
                "R_planet": p["radius_ratio"] * 1.0 * u.R_sun,
                "u1": 0.0,
                "u2": 0.0,
            })
            
            x, y, z = calculate_orbital_position(
                time=time,
                period=p["period_days"] * u.day,
                semi_major_axis=sma,
                eccentricity=p["eccentricity"] * u.dimensionless_unscaled,
                inclination=p["inclination_degrees"] * u.deg,
            )
            orbits.append({
                "name": p.get("name", f"Planet {len(orbits)+1}"),
                "x": x.to_value(u.R_sun),
                "y": y.to_value(u.R_sun),
                "z": z.to_value(u.R_sun),
            })
            
        if planet_list:
            theoretical_flux = generate_multi_planet_transit(time, planet_list)
        else:
            theoretical_flux = np.ones_like(time_days)
            
        observed_flux = inject_gaussian_noise(
            theoretical_flux,
            snr=float(st.session_state.snr),
            seed=42,
        )
        
        noise_sigma = float(np.mean(np.abs(theoretical_flux)) / st.session_state.snr)
        
        # Mock simulation object for figures
        simulation = SimpleNamespace(
            time_days=time_days,
            theoretical_flux=theoretical_flux,
            observed_flux=observed_flux,
            residuals=observed_flux - theoretical_flux,
            noise_sigma=noise_sigma,
            orbits=orbits,
        )
        
        with col_charts:
            st.subheader("Orbit View")
            # Only regenerate animation HTML when orbital params change (not SNR).
            # This prevents the iframe from re-fetching Plotly CDN on every slider move.
            _orbit_key = str([
                (p.get("name"), round(p["period_days"], 2),
                 round(p["eccentricity"], 3), round(p["inclination_degrees"], 2),
                 round(p["radius_ratio"], 4))
                for p in st.session_state.multi_planets
            ])
            if st.session_state.get("_orbit_html_key") != _orbit_key:
                st.session_state._orbit_html_key = _orbit_key
                st.session_state._orbit_html = make_multi_orbit_animation_html(simulation)
            components.html(st.session_state._orbit_html, height=560, scrolling=False)

            
            st.subheader("Light Curve")
            st.plotly_chart(make_light_curve_figure(simulation), width="stretch")
            
            st.subheader("Residuals")
            st.plotly_chart(make_residuals_figure(simulation), width="stretch")
        
    if right_panel:
        with right_panel:
            st.subheader("Simulation Logs")
            st.write("Multi-planet simulation generated.")
            st.json({
                "snr": st.session_state.snr,
                "planets": st.session_state.multi_planets
            })
