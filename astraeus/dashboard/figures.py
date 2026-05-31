"""Plotly figure builders for dashboard simulations."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import plotly.graph_objects as go

from astraeus.dashboard.simulation import DashboardSimulation

if TYPE_CHECKING:
    from astraeus.dashboard.services.mcmc_retrieval import MCMCRetrievalResult


def make_multi_orbit_figure(simulation) -> go.Figure:
    """Build a 3D orbit view with the observer line of sight marked and animated planets."""
    fig = go.Figure()
    
    PLANET_COLORS = [
        {"main": "#10B981", "line": "#047857"}, # Green
        {"main": "#3B82F6", "line": "#1D4ED8"}, # Blue
        {"main": "#8B5CF6", "line": "#5B21B6"}, # Purple
        {"main": "#EC4899", "line": "#BE185D"}, # Pink
        {"main": "#F97316", "line": "#C2410C"}, # Orange
        {"main": "#06B6D4", "line": "#0E7490"}, # Cyan
    ]
    
    # Calculate axis limit across all orbits
    axis_limit = 1.0
    if hasattr(simulation, "orbits") and simulation.orbits:
        max_x = max(float(np.max(np.abs(orb["x"]))) for orb in simulation.orbits)
        max_y = max(float(np.max(np.abs(orb["y"]))) for orb in simulation.orbits)
        max_z = max(float(np.max(np.abs(orb["z"]))) for orb in simulation.orbits)
        axis_limit = 1.1 * max(max_x, max_y, max_z, 1.0)
    
    fig.add_trace(
        go.Scatter3d(
            x=[0.0],
            y=[0.0],
            z=[0.0],
            mode="markers",
            marker={
                "size": 11,
                "color": "#FBBF24",
                "line": {"color": "#92400E", "width": 2},
            },
            name="Star",
            hovertemplate="Star center<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter3d(
            x=[0.0, 0.0],
            y=[0.0, 0.0],
            z=[-axis_limit, axis_limit],
            mode="lines",
            line={"color": "#EF4444", "dash": "dash", "width": 3},
            name="Line of sight",
            hoverinfo="skip",
        )
    )
    
    if not hasattr(simulation, "orbits") or not simulation.orbits:
        fig.update_layout(
            height=520, margin={"l": 0, "r": 0, "t": 32, "b": 0},
            scene={
                "xaxis": {"title": "x (R_sun)", "range": [-axis_limit, axis_limit]},
                "yaxis": {"title": "y (R_sun)", "range": [-axis_limit, axis_limit]},
                "zaxis": {"title": "z (R_sun)", "range": [-axis_limit, axis_limit]},
                "aspectmode": "cube",
            }
        )
        return fig

    # Plot orbit paths
    for idx, orb in enumerate(simulation.orbits):
        x, y, z = orb["x"], orb["y"], orb["z"]
        name = orb.get("name", f"Planet {idx+1}")
        color = PLANET_COLORS[idx % len(PLANET_COLORS)]
        
        # Create a faded color sequence for the path so it still shows progression
        # We can just use the planet's main color for simplicity, or vary opacity.
        fig.add_trace(
            go.Scatter3d(
                x=x, y=y, z=z,
                mode="lines",
                line={
                    "color": color["main"],
                    "width": 2,
                },
                name=f"{name} path",
                hoverinfo="skip",
            )
        )
        
    # Plot initial planet positions
    planet_traces_start = len(fig.data)
    for idx, orb in enumerate(simulation.orbits):
        x, y, z = orb["x"], orb["y"], orb["z"]
        name = orb.get("name", f"Planet {idx+1}")
        color = PLANET_COLORS[idx % len(PLANET_COLORS)]
        fig.add_trace(
            go.Scatter3d(
                x=[x[0]], y=[y[0]], z=[z[0]],
                mode="markers",
                marker={
                    "size": 8,
                    "color": color["main"],
                    "line": {"color": color["line"], "width": 2},
                },
                name=name,
                hovertemplate=(
                    f"{name}<br>"
                    f"x=%{{x:.3f}} R_sun<br>"
                    f"y=%{{y:.3f}} R_sun<br>"
                    f"z=%{{z:.3f}} R_sun<extra></extra>"
                ),
            )
        )
        
    # Add animation frames
    samples = len(simulation.orbits[0]["x"])
    step_size = max(1, samples // 100)
    frames = []
    
    for i in range(0, samples, step_size):
        frame_data = []
        for orb in simulation.orbits:
            frame_data.append(go.Scatter3d(x=[orb["x"][i]], y=[orb["y"][i]], z=[orb["z"][i]]))
        frames.append(
            go.Frame(
                data=frame_data,
                traces=list(range(planet_traces_start, planet_traces_start + len(simulation.orbits))),
                name=f"frame{i}"
            )
        )
        
    if (samples - 1) % step_size != 0:
        i = samples - 1
        frame_data = []
        for orb in simulation.orbits:
            frame_data.append(go.Scatter3d(x=[orb["x"][i]], y=[orb["y"][i]], z=[orb["z"][i]]))
        frames.append(
            go.Frame(
                data=frame_data,
                traces=list(range(planet_traces_start, planet_traces_start + len(simulation.orbits))),
                name=f"frame{i}"
            )
        )
        
    fig.frames = frames

    fig.update_layout(
        height=520,
        margin={"l": 0, "r": 0, "t": 32, "b": 0},
        legend={"orientation": "h", "y": 1.02, "x": 0.0},
        uirevision="constant",
        updatemenus=[
            {
                "buttons": [
                    {
                        "args": [
                            None,
                            {
                                "frame": {"duration": 40, "redraw": True},
                                "fromcurrent": True,
                                "transition": {"duration": 0},
                                "mode": "immediate",
                                "loop": True,
                            },
                        ],
                        "label": "Play",
                        "method": "animate",
                    },
                ],
                "direction": "left",
                "pad": {"r": 10, "t": 10},
                "showactive": False,
                "type": "buttons",
                "x": 0.0,
                "xanchor": "left",
                "y": 1.15,
                "yanchor": "top",
            }
        ],
        scene={
            "xaxis": {"title": "x (R_sun)", "range": [-axis_limit, axis_limit]},
            "yaxis": {"title": "y (R_sun)", "range": [-axis_limit, axis_limit]},
            "zaxis": {"title": "z (R_sun)", "range": [-axis_limit, axis_limit]},
            "aspectmode": "cube",
            "camera": {"eye": {"x": 1.4, "y": 1.45, "z": 0.95}},
        },
    )
    return fig


def make_orbit_figure(simulation: DashboardSimulation) -> go.Figure:
    """Build a 3D orbit view with the observer line of sight marked and an animated planet."""

    x = simulation.x_rsun
    y = simulation.y_rsun
    z = simulation.z_rsun
    axis_limit = 1.1 * max(
        float(np.max(np.abs(x))),
        float(np.max(np.abs(y))),
        float(np.max(np.abs(z))),
        1.0,
    )

    fig = go.Figure()
    fig.add_trace(
        go.Scatter3d(
            x=x,
            y=y,
            z=z,
            mode="lines",
            line={
                "color": np.linspace(0.0, 1.0, len(x)),
                "colorscale": "Viridis",
                "width": 3,
            },
            name="Planet path",
            hovertemplate=(
                "x=%{x:.3f} R_sun<br>"
                "y=%{y:.3f} R_sun<br>"
                "z=%{z:.3f} R_sun<extra></extra>"
            ),
        )
    )
    fig.add_trace(
        go.Scatter3d(
            x=[0.0],
            y=[0.0],
            z=[0.0],
            mode="markers",
            marker={
                "size": 11,
                "color": "#FBBF24",
                "line": {"color": "#92400E", "width": 2},
            },
            name="Star",
            hovertemplate="Star center<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter3d(
            x=[0.0, 0.0],
            y=[0.0, 0.0],
            z=[-axis_limit, axis_limit],
            mode="lines",
            line={"color": "#EF4444", "dash": "dash", "width": 3},
            name="Line of sight",
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter3d(
            x=[x[0]],
            y=[y[0]],
            z=[z[0]],
            mode="markers",
            marker={
                "size": 8,
                "color": "#10B981",
                "line": {"color": "#047857", "width": 2},
            },
            name="Planet",
            hovertemplate=(
                "Planet<br>"
                "x=%{x:.3f} R_sun<br>"
                "y=%{y:.3f} R_sun<br>"
                "z=%{z:.3f} R_sun<extra></extra>"
            ),
        )
    )

    step_size = max(1, len(x) // 100)
    frames = []
    for i in range(0, len(x), step_size):
        frames.append(
            go.Frame(
                data=[go.Scatter3d(x=[x[i]], y=[y[i]], z=[z[i]])],
                traces=[3],
                name=f"frame{i}"
            )
        )
        
    if (len(x) - 1) % step_size != 0:
        i = len(x) - 1
        frames.append(
            go.Frame(
                data=[go.Scatter3d(x=[x[i]], y=[y[i]], z=[z[i]])],
                traces=[3],
                name=f"frame{i}"
            )
        )
        
    fig.frames = frames

    fig.update_layout(
        height=520,
        margin={"l": 0, "r": 0, "t": 32, "b": 0},
        legend={"orientation": "h", "y": 1.02, "x": 0.0},
        uirevision="constant",
        updatemenus=[
            {
                "buttons": [
                    {
                        "args": [
                            None,
                            {
                                "frame": {"duration": 40, "redraw": True},
                                "fromcurrent": True,
                                "transition": {"duration": 0},
                                "mode": "immediate",
                                "loop": True,
                            },
                        ],
                        "label": "Play",
                        "method": "animate",
                    },
                ],
                "direction": "left",
                "pad": {"r": 10, "t": 10},
                "showactive": False,
                "type": "buttons",
                "x": 0.0,
                "xanchor": "left",
                "y": 1.15,
                "yanchor": "top",
            }
        ],
        scene={
            "xaxis": {"title": "x (R_sun)", "range": [-axis_limit, axis_limit]},
            "yaxis": {"title": "y (R_sun)", "range": [-axis_limit, axis_limit]},
            "zaxis": {"title": "z (R_sun)", "range": [-axis_limit, axis_limit]},
            "aspectmode": "cube",
            "camera": {"eye": {"x": 1.4, "y": 1.45, "z": 0.95}},
        },
    )
    return fig


def make_light_curve_figure(simulation: DashboardSimulation) -> go.Figure:
    """Build the theoretical and observed light-curve plot."""

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=simulation.time_days,
            y=simulation.observed_flux,
            mode="markers",
            marker={"size": 5, "color": "rgba(14, 165, 233, 0.55)"},
            name="Observed",
            hovertemplate="t=%{x:.4f} d<br>flux=%{y:.6f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=simulation.time_days,
            y=simulation.theoretical_flux,
            mode="lines",
            line={"width": 3, "color": "#111827"},
            name="Pure geometric",
            hovertemplate="t=%{x:.4f} d<br>flux=%{y:.6f}<extra></extra>",
        )
    )
    fig.update_layout(
        height=430,
        margin={"l": 12, "r": 12, "t": 12, "b": 8},
        legend={"orientation": "h", "y": 1.08, "x": 0.0},
        xaxis_title="Time (days)",
        yaxis_title="Relative flux",
        hovermode="x unified",
    )
    return fig


def make_residuals_figure(simulation: DashboardSimulation) -> go.Figure:
    """Build the observed-minus-theoretical residual plot."""

    fig = go.Figure()
    fig.add_hline(y=0.0, line_dash="dash", line_color="#64748B")
    fig.add_hrect(
        y0=-simulation.noise_sigma,
        y1=simulation.noise_sigma,
        line_width=0,
        fillcolor="rgba(20, 184, 166, 0.10)",
    )
    fig.add_trace(
        go.Scatter(
            x=simulation.time_days,
            y=simulation.residuals,
            mode="markers",
            marker={"size": 5, "color": "rgba(244, 63, 94, 0.62)"},
            name="Residual",
            hovertemplate="t=%{x:.4f} d<br>residual=%{y:.6f}<extra></extra>",
        )
    )
    fig.update_layout(
        height=300,
        margin={"l": 12, "r": 12, "t": 12, "b": 8},
        showlegend=False,
        xaxis_title="Time (days)",
        yaxis_title="Observed - pure",
        hovermode="x unified",
    )
    return fig


def make_raw_light_curve_figure(time: np.ndarray, flux: np.ndarray, flux_err: np.ndarray) -> go.Figure:
    """Build a scatter plot of raw ingested light curve data."""

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=time,
            y=flux,
            error_y={
                "type": "data",
                "array": flux_err,
                "visible": True,
                "color": "rgba(14, 165, 233, 0.3)",
            },
            mode="markers",
            marker={"size": 4, "color": "rgba(14, 165, 233, 0.8)"},
            name="Raw Data",
            hovertemplate="t=%{x:.4f}<br>flux=%{y:.6f} +/- %{error_y.array:.6f}<extra></extra>",
        )
    )
    fig.update_layout(
        height=430,
        margin={"l": 12, "r": 12, "t": 12, "b": 8},
        xaxis_title="Time",
        yaxis_title="Flux",
        hovermode="x unified",
    )
    return fig


def make_retrieval_validation_figure(result: MCMCRetrievalResult) -> go.Figure:
    """Build a phase-folded validation plot for MCMC retrieval results."""

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=result.folded_time,
            y=result.folded_flux,
            mode="markers",
            marker={"size": 3, "color": "rgba(148, 163, 184, 0.4)"},
            name="Phase-folded Data",
        )
    )

    sort_idx = np.argsort(result.folded_time)
    fig.add_trace(
        go.Scatter(
            x=result.folded_time[sort_idx],
            y=result.theoretical_flux[sort_idx],
            mode="lines",
            line={"color": "#ff2a6d", "width": 3},
            name="MCMC Best Fit Model",
        )
    )

    fig.update_layout(
        xaxis_title="Phase (days from mid-transit)",
        yaxis_title="Relative Flux",
        template="plotly_dark",
        margin={"l": 40, "r": 40, "t": 40, "b": 40},
        hovermode="x unified",
    )
    return fig
