"""Data ingestion tab rendering for the dashboard."""

from __future__ import annotations

import streamlit as st

from astraeus.dashboard.figures import make_raw_light_curve_figure
from astraeus.dashboard.services.data_ingestion import (
    LightCurveData,
    load_archive_light_curve,
    load_uploaded_light_curve,
)
from astraeus.dashboard.ui.mcmc_panel import render_mcmc_analysis_panel


ARCHIVE_SOURCE = "NASA Archive API"
CSV_UPLOAD_SOURCE = "Upload Raw CSV"
JSON_UPLOAD_SOURCE = "Upload Raw JSON"
LIGHT_CURVE_STATE_KEY = "dashboard_light_curve_data"


def render_data_ingestion_panel() -> None:
    """Render data ingestion controls and downstream analysis panels."""

    st.subheader("Data Input Configuration")

    source_type = st.radio(
        "Data Input Source",
        [ARCHIVE_SOURCE, CSV_UPLOAD_SOURCE, JSON_UPLOAD_SOURCE],
        horizontal=True,
    )

    loaded_light_curve = (
        _render_archive_loader()
        if source_type == ARCHIVE_SOURCE
        else _render_upload_loader(source_type)
    )
    if loaded_light_curve is not None:
        st.session_state[LIGHT_CURVE_STATE_KEY] = loaded_light_curve

    light_curve = st.session_state.get(LIGHT_CURVE_STATE_KEY)

    if light_curve is not None:
        _render_light_curve_preview(light_curve)
        render_mcmc_analysis_panel(light_curve)


def _render_archive_loader() -> LightCurveData | None:
    """Render archive controls and return loaded data when requested."""

    col1, col2 = st.columns(2)
    target_id = col1.text_input("Target ID (e.g., 'WASP-12b')", value="WASP-12b")
    mission = col2.selectbox("Telescope Mission", ["Kepler", "K2", "TESS"])

    if not st.button("Load from NASA Archive"):
        return None

    with st.spinner(f"Fetching {target_id} from {mission}..."):
        try:
            light_curve = load_archive_light_curve(target_id, mission)
        except Exception as exc:
            st.error(f"Error loading data: {exc}")
            return None

    st.success("Data loaded successfully.")
    return light_curve


def _render_upload_loader(source_type: str) -> LightCurveData | None:
    """Render file-upload controls and return loaded data when requested."""

    file_ext = "csv" if "CSV" in source_type else "json"
    uploaded_file = st.file_uploader(f"Upload .{file_ext} file", type=[file_ext])

    st.write("Column Name Overrides (Optional)")
    col1, col2, col3 = st.columns(3)
    time_col = col1.text_input("Time Column Override", help="Leave blank to auto-detect")
    flux_col = col2.text_input("Flux Column Override", help="Leave blank to auto-detect")
    err_col = col3.text_input("Flux Error Column Override", help="Leave blank to auto-detect")

    if uploaded_file is None or not st.button("Load Uploaded File"):
        return None

    column_map = _build_column_map(time_col, flux_col, err_col)
    with st.spinner("Processing file..."):
        try:
            light_curve = load_uploaded_light_curve(
                uploaded_file.getvalue(),
                file_ext,
                column_map=column_map,
            )
        except Exception as exc:
            st.error(f"Error parsing file: {exc}")
            return None

    st.success("Data loaded successfully.")
    return light_curve


def _build_column_map(time_col: str, flux_col: str, err_col: str) -> dict[str, str]:
    """Build loader column overrides from optional text inputs."""

    column_map: dict[str, str] = {}
    if time_col:
        column_map["time"] = time_col
    if flux_col:
        column_map["flux"] = flux_col
    if err_col:
        column_map["flux_err"] = err_col
    return column_map


def _render_light_curve_preview(light_curve: LightCurveData) -> None:
    """Render raw ingested light-curve data."""

    st.subheader("Raw Light Curve Preview")
    fig = make_raw_light_curve_figure(
        light_curve.time,
        light_curve.flux,
        light_curve.flux_err,
    )
    st.plotly_chart(fig, width="stretch")
