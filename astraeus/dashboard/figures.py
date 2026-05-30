"""Plotly figure builders for dashboard simulations."""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

from astraeus.dashboard.simulation import DashboardSimulation


def make_orbit_figure(simulation: DashboardSimulation) -> go.Figure:
    """Build a 3D orbit view with the observer line of sight marked."""

    x = simulation.x_rsun
    y = simulation.y_rsun
    z = simulation.z_rsun
    axis_limit = 1.1 * max(
        float(np.max(np.abs(x))),
        float(np.max(np.abs(y))),
        float(np.max(np.abs(z))),
        1.0,
    )
    midpoint = len(x) // 4

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
                "width": 5,
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
            x=[x[midpoint]],
            y=[y[midpoint]],
            z=[z[midpoint]],
            mode="markers",
            marker={"size": 6, "color": "#38BDF8"},
            name="Quarter phase",
            hovertemplate=(
                "Quarter phase<br>"
                "x=%{x:.3f} R_sun<br>"
                "y=%{y:.3f} R_sun<br>"
                "z=%{z:.3f} R_sun<extra></extra>"
            ),
        )
    )
    fig.add_trace(
        go.Scatter3d(
            x=[0.0, 0.0],
            y=[0.0, 0.0],
            z=[-axis_limit, axis_limit],
            mode="lines",
            line={"color": "#EF4444", "dash": "dash", "width": 5},
            name="Line of sight",
            hoverinfo="skip",
        )
    )
    fig.update_layout(
        height=520,
        margin={"l": 0, "r": 0, "t": 16, "b": 0},
        legend={"orientation": "h", "y": 1.02, "x": 0.0},
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
