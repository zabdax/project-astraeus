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

    frame_names = [f.name for f in frames]

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
                            frame_names,
                            {
                                "frame": {"duration": 40, "redraw": False},
                                "fromcurrent": False,
                                "transition": {"duration": 0},
                                "mode": "immediate",
                                "loop": True,
                            },
                        ],
                        "label": "Play",
                        "method": "animate",
                    },
                    {
                        "args": [
                            [None],
                            {
                                "frame": {"duration": 0, "redraw": False},
                                "mode": "immediate",
                                "transition": {"duration": 0},
                            },
                        ],
                        "label": "Stop",
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

def make_multi_orbit_animation_html(simulation) -> str:
    """Return a self-contained HTML string for the 3D orbit animation.

    Drives infinite looping via requestAnimationFrame + Plotly.restyle,
    bypassing Plotly.js's broken loop support for Scatter3d.
    Optimised: 200-point downsampled paths, pre-flattened Float32Arrays,
    compact float serialisation, native 60 fps rAF.
    """
    import json

    PLANET_COLORS = [
        {"main": "#10B981", "line": "#047857"},
        {"main": "#3B82F6", "line": "#1D4ED8"},
        {"main": "#8B5CF6", "line": "#5B21B6"},
        {"main": "#EC4899", "line": "#BE185D"},
        {"main": "#F97316", "line": "#C2410C"},
        {"main": "#06B6D4", "line": "#0E7490"},
    ]

    orbits_raw = simulation.orbits if hasattr(simulation, "orbits") and simulation.orbits else []

    # --- downsample to at most ANIM_PTS points for both path and animation ---
    ANIM_PTS = 200
    axis_limit = 1.0
    orbits_ds = []  # downsampled for animation driver
    orbits_path = []  # downsampled path lines (visual)
    for orb in orbits_raw:
        rx = np.asarray(orb["x"], dtype=np.float32)
        ry = np.asarray(orb["y"], dtype=np.float32)
        rz = np.asarray(orb["z"], dtype=np.float32)
        n = len(rx)
        idx = np.linspace(0, n - 1, min(ANIM_PTS, n), dtype=int)
        sx, sy, sz = rx[idx], ry[idx], rz[idx]
        orbits_ds.append((sx, sy, sz))
        # path lines can use same downsampled set – smooth enough
        orbits_path.append((sx, sy, sz))
        axis_limit = max(axis_limit,
                         float(np.max(np.abs(sx))),
                         float(np.max(np.abs(sy))),
                         float(np.max(np.abs(sz))))
    axis_limit = round(axis_limit * 1.1, 4)

    num_orbits = len(orbits_ds)
    anim_n = len(orbits_ds[0][0]) if orbits_ds else 0
    al = axis_limit

    # Pre-flatten each planet's XYZ into a single list [x0,y0,z0, x1,y1,z1, ...]
    # JS will read with Float32Array; stride = 3.
    flat_coords = []
    for sx, sy, sz in orbits_ds:
        flat = []
        for x, y, z in zip(sx.tolist(), sy.tolist(), sz.tolist()):
            flat.append(round(x, 4))
            flat.append(round(y, 4))
            flat.append(round(z, 4))
        flat_coords.append(flat)

    # planet marker trace indices: 0=star, 1=los, 2..N+1=paths, N+2..2N+1=markers
    planet_marker_start = 2 + num_orbits
    planet_indices = list(range(planet_marker_start, planet_marker_start + num_orbits))

    # Build initial traces
    traces = [
        {
            "type": "scatter3d",
            "x": [0.0], "y": [0.0], "z": [0.0],
            "mode": "markers",
            "marker": {"size": 11, "color": "#FBBF24", "line": {"color": "#92400E", "width": 2}},
            "name": "Star",
        },
        {
            "type": "scatter3d",
            "x": [0.0, 0.0], "y": [0.0, 0.0], "z": [-al, al],
            "mode": "lines",
            "line": {"color": "#EF4444", "dash": "dash", "width": 3},
            "name": "Line of sight",
            "hoverinfo": "skip",
        },
    ]
    for idx, (sx, sy, sz) in enumerate(orbits_path):
        color = PLANET_COLORS[idx % len(PLANET_COLORS)]
        traces.append({
            "type": "scatter3d",
            "x": [round(v, 4) for v in sx.tolist()],
            "y": [round(v, 4) for v in sy.tolist()],
            "z": [round(v, 4) for v in sz.tolist()],
            "mode": "lines",
            "line": {"color": color["main"], "width": 2},
            "name": f"{orbits_raw[idx].get('name', f'Planet {idx+1}')} path",
            "hoverinfo": "skip",
        })
    for idx, (sx, sy, sz) in enumerate(orbits_ds):
        color = PLANET_COLORS[idx % len(PLANET_COLORS)]
        name = orbits_raw[idx].get("name", f"Planet {idx+1}")
        traces.append({
            "type": "scatter3d",
            "x": [round(float(sx[0]), 4)], "y": [round(float(sy[0]), 4)], "z": [round(float(sz[0]), 4)],
            "mode": "markers",
            "marker": {"size": 8, "color": color["main"], "line": {"color": color["line"], "width": 2}},
            "name": name,
        })

    traces_json = json.dumps(traces, separators=(",", ":"))
    layout_json = json.dumps({
        "height": 500,
        "margin": {"l": 0, "r": 0, "t": 10, "b": 0},
        "legend": {"orientation": "h", "y": 1.02, "x": 0.0},
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "scene": {
            "xaxis": {"title": "x (R\u2609)", "range": [-al, al]},
            "yaxis": {"title": "y (R\u2609)", "range": [-al, al]},
            "zaxis": {"title": "z (R\u2609)", "range": [-al, al]},
            "aspectmode": "cube",
            "camera": {"eye": {"x": 1.4, "y": 1.45, "z": 0.95}},
        },
    }, separators=(",", ":"))

    flat_json = json.dumps(flat_coords, separators=(",", ":"))
    planet_indices_json = json.dumps(planet_indices)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
  body{{margin:0;background:transparent;font-family:sans-serif;}}
  #plot{{width:100%;height:500px;}}
  #controls{{display:flex;gap:10px;padding:8px 4px;align-items:center;}}
  button{{display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:6px 20px;border:none;border-radius:6px;font-size:14px;font-weight:600;cursor:pointer;transition:opacity .15s,transform .1s;}}
  button:active{{transform:scale(0.96);}}
  button svg{{flex-shrink:0;}}
  #btn-play{{background:#10B981;color:#fff;}}
  #btn-play:disabled{{background:#6B7280;cursor:not-allowed;opacity:.55;}}
  #btn-stop{{background:#EF4444;color:#fff;}}
  #btn-stop:disabled{{background:#6B7280;cursor:not-allowed;opacity:.55;}}
  #status{{font-size:12px;color:#9CA3AF;margin-left:4px;display:inline-flex;align-items:center;}}
</style>
</head>
<body>
<div id="controls">
  <button id="btn-play">
    <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><polygon points="6 4 20 12 6 20"></polygon></svg>
    Play
  </button>
  <button id="btn-stop" disabled>
    <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"></rect></svg>
    Stop
  </button>
  <span id="status">Paused</span>
</div>
<div id="plot"></div>
<script>
(function(){{
  var traces={traces_json};
  var layout={layout_json};
  var flatRaw={flat_json};
  var pidx={planet_indices_json};
  var N={num_orbits};
  var animN={anim_n};
  // Adaptive frame budget: ~60fps for 1 planet, ~30fps for 3, ~20fps for 5+
  var frameDur=Math.max(16,N*10);

  // Convert flat arrays to Float32Arrays for fast typed access
  var flat=[];
  for(var p=0;p<N;p++) flat.push(new Float32Array(flatRaw[p]));

  Plotly.newPlot('plot',traces,layout,{{responsive:true,displaylogo:false,staticPlot:false}});

  var fi=0, running=false, rafId=null, lastT=0;
  var btnPlay=document.getElementById('btn-play');
  var btnStop=document.getElementById('btn-stop');
  var status=document.getElementById('status');

  function tick(now){{
    if(!running)return;
    rafId=requestAnimationFrame(tick);
    if(now-lastT<frameDur)return;
    lastT=now;
    var xs=[],ys=[],zs=[];
    var base=fi*3;
    for(var p=0;p<N;p++){{
      xs.push([flat[p][base]]);
      ys.push([flat[p][base+1]]);
      zs.push([flat[p][base+2]]);
    }}
    Plotly.restyle('plot',{{x:xs,y:ys,z:zs}},pidx);
    fi=(fi+1)%animN;
  }}

  btnPlay.addEventListener('click',function(){{
    if(running)return;
    running=true;
    btnPlay.disabled=true;
    btnStop.disabled=false;
    status.textContent='Playing \u221e';
    rafId=requestAnimationFrame(tick);
  }});

  btnStop.addEventListener('click',function(){{
    running=false;
    if(rafId){{cancelAnimationFrame(rafId);rafId=null;}}
    btnPlay.disabled=false;
    btnStop.disabled=true;
    status.textContent='Paused';
  }});
}})();
</script>
</body>
</html>"""


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

    frame_names = [f.name for f in frames]

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
                            frame_names,
                            {
                                "frame": {"duration": 40, "redraw": False},
                                "fromcurrent": False,
                                "transition": {"duration": 0},
                                "mode": "immediate",
                                "loop": True,
                            },
                        ],
                        "label": "Play",
                        "method": "animate",
                    },
                    {
                        "args": [
                            [None],
                            {
                                "frame": {"duration": 0, "redraw": False},
                                "mode": "immediate",
                                "transition": {"duration": 0},
                            },
                        ],
                        "label": "Stop",
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
    # Downsample to 400 pts for fast rendering – no visual loss
    _n = len(simulation.time_days)
    _idx = np.linspace(0, _n - 1, min(400, _n), dtype=int)
    t  = simulation.time_days[_idx]
    of = simulation.observed_flux[_idx]
    tf = simulation.theoretical_flux[_idx]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=t,
            y=of,
            mode="markers",
            marker={"size": 5, "color": "rgba(14, 165, 233, 0.55)"},
            name="Observed",
            hovertemplate="t=%{x:.4f} d<br>flux=%{y:.6f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=t,
            y=tf,
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
    # Downsample to 400 pts for fast rendering
    _n = len(simulation.time_days)
    _idx = np.linspace(0, _n - 1, min(400, _n), dtype=int)
    t  = simulation.time_days[_idx]
    r  = simulation.residuals[_idx]

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
            x=t,
            y=r,
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
