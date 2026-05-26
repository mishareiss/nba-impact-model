"""
NBA half-court plotting utilities for Plotly.

Coordinate system (play_by_play legacy coordinates):
  x_legacy: -252 → +252  (50 ft court width, origin = basket centre)
  y_legacy: -52.5 → +418 (baseline → half-court line)
  Basket centre ≈ (0, 0)

All court dimensions are in tenths-of-feet to match the data.

Public API
----------
court_traces()       — list of go.Scatter traces drawing the half-court lines
shot_scatter_fig()   — per-shot scatter coloured by make/miss and xShot surprise
shot_hexbin_fig()    — 2-D density / efficiency heatmap with four display modes
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd
import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# Court dimension constants (tenths of feet)
# ---------------------------------------------------------------------------
BASKET_Y = 0.0
BASELINE_Y = -52.5
HALFCOURT_Y = 418.0
COURT_HALF_W = 252.0

PAINT_HALF_W = 80.0          # key is 16 ft wide → 80 units each side
FT_LINE_Y = 137.5            # free-throw line
FT_CIRCLE_R = 60.0           # free-throw circle radius (6 ft)

BACKBOARD_Y = -7.5
BACKBOARD_HALF_W = 30.0

RESTRICTED_R = 40.0          # restricted area (4 ft)
BASKET_R = 7.5               # basket rim (0.75 ft)

THREE_CORNER_X = 220.0       # corner 3-point line x position (22 ft)
THREE_ARC_R = 237.5          # 3-point arc radius (23.75 ft)
THREE_ARC_START_Y = float(np.sqrt(THREE_ARC_R**2 - THREE_CORNER_X**2))  # ≈ 89.5

# Shooting chart view window
CHART_X_RANGE = (-255, 255)
CHART_Y_RANGE = (-65, 430)


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _arc(cx: float, cy: float, r: float,
         start_deg: float, end_deg: float,
         n: int = 60) -> tuple[list[float], list[float]]:
    """Return (x_list, y_list) of points along a circular arc."""
    angles = np.linspace(np.radians(start_deg), np.radians(end_deg), n)
    return (cx + r * np.cos(angles)).tolist(), (cy + r * np.sin(angles)).tolist()


def _line_trace(xs: list[float], ys: list[float],
                color: str, width: float = 1.5,
                dash: str = "solid") -> go.Scatter:
    return go.Scatter(
        x=xs, y=ys, mode="lines",
        line=dict(color=color, width=width, dash=dash),
        showlegend=False, hoverinfo="skip", name="court",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def court_traces(
    line_color: str = "rgba(160,160,160,0.60)",
    width: float = 1.5,
) -> list[go.Scatter]:
    """
    Return a list of go.Scatter traces that draw an NBA half-court.

    Usage:
        fig = go.Figure()
        for t in court_traces(): fig.add_trace(t)
    """
    lc = line_color
    lw = width
    traces: list[go.Scatter] = []

    def seg(x0, y0, x1, y1, dash="solid"):
        traces.append(_line_trace([x0, x1], [y0, y1], lc, lw, dash))

    def arc_trace(cx, cy, r, s, e, n=60, dash="solid"):
        xs, ys = _arc(cx, cy, r, s, e, n)
        traces.append(_line_trace(xs, ys, lc, lw, dash))

    # Outer boundary (baseline + two sidelines)
    seg(-COURT_HALF_W, BASELINE_Y, COURT_HALF_W, BASELINE_Y)
    seg(-COURT_HALF_W, BASELINE_Y, -COURT_HALF_W, HALFCOURT_Y)
    seg(COURT_HALF_W, BASELINE_Y, COURT_HALF_W, HALFCOURT_Y)

    # Paint rectangle
    seg(-PAINT_HALF_W, BASELINE_Y, -PAINT_HALF_W, FT_LINE_Y)
    seg(PAINT_HALF_W, BASELINE_Y, PAINT_HALF_W, FT_LINE_Y)
    seg(-PAINT_HALF_W, FT_LINE_Y, PAINT_HALF_W, FT_LINE_Y)   # FT line

    # Free throw circle — upper half solid, lower half dashed
    arc_trace(0, FT_LINE_Y, FT_CIRCLE_R, 0, 180, dash="solid")
    arc_trace(0, FT_LINE_Y, FT_CIRCLE_R, 180, 360, dash="dot")

    # Backboard
    seg(-BACKBOARD_HALF_W, BACKBOARD_Y, BACKBOARD_HALF_W, BACKBOARD_Y)

    # Basket rim
    arc_trace(0, BASKET_Y, BASKET_R, 0, 360, n=40)

    # Restricted area (front semicircle only)
    arc_trace(0, BASKET_Y, RESTRICTED_R, 0, 180)

    # 3-point corner lines
    seg(-THREE_CORNER_X, BASELINE_Y, -THREE_CORNER_X, THREE_ARC_START_Y)
    seg(THREE_CORNER_X, BASELINE_Y, THREE_CORNER_X, THREE_ARC_START_Y)

    # 3-point arc (right corner → left corner, sweeping above the basket)
    start_angle = float(np.degrees(np.arctan2(THREE_ARC_START_Y, THREE_CORNER_X)))
    end_angle = float(np.degrees(np.arctan2(THREE_ARC_START_Y, -THREE_CORNER_X)))
    arc_trace(0, BASKET_Y, THREE_ARC_R, start_angle, end_angle, n=120)

    return traces


ZONE_REGIONS: dict[str, dict] = {
    "at_rim": dict(
        label="At Rim",
        coords=[(0, 0)],               # rough display centre only
        description="Within the restricted area (≤ 4 ft from basket)",
        color_base="rgba(52, 152, 219",  # blue-ish
    ),
    "short_mid": dict(
        label="Short Mid",
        coords=[(0, 80)],
        description="Paint area outside restricted zone",
        color_base="rgba(46, 204, 113",
    ),
    "mid_range": dict(
        label="Mid-Range",
        coords=[(0, 175)],
        description="Mid-range jump shots",
        color_base="rgba(241, 196, 15",
    ),
    "long_mid": dict(
        label="Long Mid",
        coords=[(0, 215)],
        description="Long two-pointers near the 3-point line",
        color_base="rgba(230, 126, 34",
    ),
    "three": dict(
        label="3-Point",
        coords=[(0, 290), (-200, 10), (200, 10)],
        description="Beyond the 3-point arc and corner 3s",
        color_base="rgba(231, 76, 60",
    ),
}

ZONE_ORDER = ["at_rim", "short_mid", "mid_range", "long_mid", "three"]
ZONE_LABELS = {k: v["label"] for k, v in ZONE_REGIONS.items()}


def _zone_fill_color(fg_vs_expected: float, alpha: float = 0.25) -> str:
    """Map over/under-performance to a red/green rgba fill."""
    clamped = max(-0.15, min(0.15, fg_vs_expected))
    if clamped >= 0:
        g = int(180 + clamped / 0.15 * 75)
        return f"rgba(40,{g},80,{alpha})"
    else:
        r = int(180 + abs(clamped) / 0.15 * 75)
        return f"rgba({r},40,60,{alpha})"


def shot_scatter_fig(
    df_shots,
    player_name: str = "",
    season: str = "",
    season_type: str = "",
    team_color: str = "#E8462A",
    show_zone_overlay: bool = True,
    df_zones=None,
) -> go.Figure:
    """
    Build a half-court shot scatter figure.

    Parameters
    ----------
    df_shots : DataFrame with columns x_legacy, y_legacy, xshot, shot_made,
               shot_value, and optionally shot_zone, sub_type, shot_distance.
    df_zones : optional DataFrame with shot_zone, fg_pct_vs_expected for overlay tinting.
    """
    fig = go.Figure()

    # --- court ---
    for t in court_traces():
        fig.add_trace(t)

    # --- optional zone overlay ---
    if show_zone_overlay and df_zones is not None and len(df_zones) > 0:
        _add_zone_overlay(fig, df_zones)

    if len(df_shots) == 0:
        _apply_court_layout(fig, player_name, season, season_type, 0)
        return fig

    made = df_shots[df_shots["shot_made"] == 1]
    missed = df_shots[df_shots["shot_made"] == 0]

    # Hover text helpers
    def _hover(row):
        sub = row.get("sub_type", "")
        dist = row.get("shot_distance", None)
        dist_str = f"{dist / 10:.1f} ft" if dist is not None else ""
        xshot = row.get("xshot", None)
        xs_str = f"xShot: {xshot:.3f}" if xshot is not None else ""
        return f"{sub}<br>{dist_str}<br>{xs_str}"

    # Missed shots — small grey X
    if len(missed) > 0:
        fig.add_trace(go.Scatter(
            x=missed["x_legacy"],
            y=missed["y_legacy"],
            mode="markers",
            marker=dict(
                symbol="x-thin",
                size=6,
                color="rgba(180,60,60,0.55)",
                line=dict(width=1.2, color="rgba(200,80,80,0.7)"),
            ),
            name="Missed",
            hovertemplate=(
                "<b>Missed</b><br>"
                "%{customdata}<extra></extra>"
            ),
            customdata=[_hover(r) for _, r in missed.iterrows()],
        ))

    # Made shots — solid circle, colored by xShot performance
    if len(made) > 0:
        # Color each made shot by how surprising it was (made - xshot)
        xshot_vals = made["xshot"].fillna(0.4).values
        overperf = 1.0 - xshot_vals   # higher = more surprising make
        # Scale to a nice green range
        marker_colors = [
            f"rgba(40,{int(140 + v * 80)},80,0.75)" for v in overperf
        ]
        fig.add_trace(go.Scatter(
            x=made["x_legacy"],
            y=made["y_legacy"],
            mode="markers",
            marker=dict(
                symbol="circle",
                size=7,
                color=marker_colors,
                line=dict(width=0.5, color="rgba(255,255,255,0.25)"),
            ),
            name="Made",
            hovertemplate=(
                "<b>Made</b><br>"
                "%{customdata}<extra></extra>"
            ),
            customdata=[_hover(r) for _, r in made.iterrows()],
        ))

    total = len(df_shots)
    _apply_court_layout(fig, player_name, season, season_type, total)
    return fig


def _add_zone_overlay(fig: go.Figure, df_zones) -> None:
    """Tint approximate court zones by efficiency vs expected."""
    import math

    zone_centres = {
        "at_rim":     [(0, 25)],
        "short_mid":  [(-60, 80), (60, 80)],
        "mid_range":  [(-100, 160), (0, 150), (100, 160)],
        "long_mid":   [(-130, 205), (0, 205), (130, 205)],
        "three":      [(-210, 30), (-200, 180), (0, 270), (200, 180), (210, 30)],
    }
    zone_radii = {
        "at_rim": 38,
        "short_mid": 55,
        "mid_range": 62,
        "long_mid": 55,
        "three": 55,
    }

    zmap = {}
    for _, row in df_zones.iterrows():
        zmap[row["shot_zone"]] = float(row.get("fg_pct_vs_expected", 0) or 0)

    for zone, fgdiff in zmap.items():
        if zone not in zone_centres:
            continue
        r = zone_radii.get(zone, 50)
        fill = _zone_fill_color(fgdiff, alpha=0.18)
        line_c = _zone_fill_color(fgdiff, alpha=0.5)
        label = ZONE_LABELS.get(zone, zone)
        sign = "+" if fgdiff >= 0 else ""

        for cx, cy in zone_centres[zone]:
            # Draw a filled circle at this zone centre
            angles = np.linspace(0, 2 * math.pi, 50)
            xs = (cx + r * np.cos(angles)).tolist()
            ys = (cy + r * np.sin(angles)).tolist()
            fig.add_trace(go.Scatter(
                x=xs, y=ys, mode="lines", fill="toself",
                fillcolor=fill,
                line=dict(color=line_c, width=1),
                showlegend=False, hoverinfo="skip", name="zone",
            ))

        # Single annotation at primary centre
        pcx, pcy = zone_centres[zone][len(zone_centres[zone]) // 2]
        fig.add_annotation(
            x=pcx, y=pcy,
            text=f"<b>{label}</b><br>{sign}{fgdiff*100:.1f}%",
            font=dict(size=8, color="rgba(255,255,255,0.85)"),
            showarrow=False,
            bgcolor="rgba(0,0,0,0)",
        )


def _apply_court_layout(fig: go.Figure, player_name: str,
                        season: str, season_type: str, n_shots: int) -> None:
    title_parts = [p for p in [player_name, season, season_type] if p]
    title = " · ".join(title_parts)
    if n_shots:
        title += f"  ({n_shots:,} attempts)"

    fig.update_layout(
        title=dict(text=title, font=dict(size=15), x=0.5, xanchor="center"),
        xaxis=dict(
            range=list(CHART_X_RANGE),
            showgrid=False, zeroline=False,
            showticklabels=False, fixedrange=True,
        ),
        yaxis=dict(
            range=list(CHART_Y_RANGE),
            showgrid=False, zeroline=False,
            showticklabels=False, fixedrange=True,
            scaleanchor="x", scaleratio=1,
        ),
        plot_bgcolor="rgba(15,15,20,0.0)",
        paper_bgcolor="rgba(0,0,0,0)",
        height=460,
        margin=dict(l=5, r=5, t=50, b=10),
        legend=dict(
            orientation="h", y=1.02, x=0.5, xanchor="center",
            font=dict(size=11),
        ),
        hoverlabel=dict(bgcolor="rgba(30,30,40,0.9)", font_size=12),
    )


# ---------------------------------------------------------------------------
# Hexbin / density chart
# ---------------------------------------------------------------------------

HexbinMode = Literal["volume", "xshot", "fg_pct", "fg_vs_expected"]

_HEXBIN_CONFIG: dict[str, dict] = {
    "volume": dict(
        label="Shot Volume",
        colorscale="Blues",
        reversescale=False,
        colorbar_title="Attempts",
        zmid=None,
    ),
    "xshot": dict(
        label="Avg xShot (Shot Difficulty)",
        colorscale=[[0, "#2C3E50"], [0.5, "#F4D03F"], [1, "#E8462A"]],
        reversescale=False,
        colorbar_title="Avg xShot",
        zmid=None,
    ),
    "fg_pct": dict(
        label="Actual FG%",
        colorscale=[[0, "#922B21"], [0.5, "#F4D03F"], [1, "#1E8449"]],
        reversescale=False,
        colorbar_title="FG%",
        zmid=None,
    ),
    "fg_vs_expected": dict(
        label="FG% Above Expected",
        colorscale=[[0, "#922B21"], [0.5, "#2C3E50"], [1, "#1E8449"]],
        reversescale=False,
        colorbar_title="FG% vs Expected",
        zmid=0,
    ),
}

# Bin counts: fewer bins = more readable heat zones
_NBINS_X = 25
_NBINS_Y = 28


def shot_hexbin_fig(
    df_shots: pd.DataFrame,
    mode: HexbinMode = "volume",
    player_name: str = "",
    season: str = "",
    season_type: str = "",
    team_color: str = "#E8462A",
    min_attempts: int = 2,
) -> go.Figure:
    """
    Build a court heatmap from individual shot records.

    Parameters
    ----------
    df_shots     : DataFrame with x_legacy, y_legacy, xshot, shot_made columns.
    mode         : "volume"         → bin count (shot frequency)
                   "xshot"          → mean predicted make probability per bin
                   "fg_pct"         → actual make rate per bin
                   "fg_vs_expected" → (fg_pct − xshot) per bin (diverging scale)
    min_attempts : bins with fewer shots are masked to avoid small-sample noise.
    """
    fig = go.Figure()
    for t in court_traces():
        fig.add_trace(t)

    if df_shots.empty:
        _apply_court_layout(fig, player_name, season, season_type, 0)
        return fig

    cfg = _HEXBIN_CONFIG[mode]
    df = df_shots.copy()

    # --- bin the court into a grid ---
    x_edges = np.linspace(CHART_X_RANGE[0], CHART_X_RANGE[1], _NBINS_X + 1)
    y_edges = np.linspace(CHART_Y_RANGE[0], min(CHART_Y_RANGE[1], 380), _NBINS_Y + 1)

    df["x_bin"] = pd.cut(df["x_legacy"], bins=x_edges, labels=False)
    df["y_bin"] = pd.cut(df["y_legacy"], bins=y_edges, labels=False)
    df = df.dropna(subset=["x_bin", "y_bin"])
    df["x_bin"] = df["x_bin"].astype(int)
    df["y_bin"] = df["y_bin"].astype(int)

    # Aggregate per bin
    agg = df.groupby(["x_bin", "y_bin"]).agg(
        attempts  = ("shot_made", "count"),
        makes     = ("shot_made", "sum"),
        mean_xshot= ("xshot",     "mean"),
    ).reset_index()
    agg = agg[agg["attempts"] >= min_attempts].copy()
    agg["fg_pct"]         = agg["makes"] / agg["attempts"]
    agg["fg_vs_expected"] = agg["fg_pct"] - agg["mean_xshot"]

    # Map bin indices back to court coordinates (bin centres)
    x_centres = (x_edges[:-1] + x_edges[1:]) / 2
    y_centres = (y_edges[:-1] + y_edges[1:]) / 2
    agg["x"] = agg["x_bin"].map(lambda i: x_centres[i])
    agg["y"] = agg["y_bin"].map(lambda i: y_centres[i])

    # Select the z-value based on mode
    z_col = {
        "volume":         "attempts",
        "xshot":          "mean_xshot",
        "fg_pct":         "fg_pct",
        "fg_vs_expected": "fg_vs_expected",
    }[mode]

    z = agg[z_col].values
    zmid = cfg["zmid"]

    heatmap_kwargs: dict = dict(
        x=agg["x"],
        y=agg["y"],
        z=z,
        colorscale=cfg["colorscale"],
        reversescale=cfg["reversescale"],
        colorbar=dict(
            title=dict(text=cfg["colorbar_title"], side="right"),
            thickness=14, len=0.6, x=1.01,
            tickfont=dict(size=10),
        ),
        hovertemplate=(
            f"Attempts: %{{customdata[0]}}<br>"
            f"FG%: %{{customdata[1]:.1%}}<br>"
            f"Avg xShot: %{{customdata[2]:.3f}}<br>"
            f"FG% vs Expected: %{{customdata[3]:+.3f}}<extra></extra>"
        ),
        customdata=list(zip(
            agg["attempts"].round(0).astype(int),
            agg["fg_pct"].round(4),
            agg["mean_xshot"].round(4),
            agg["fg_vs_expected"].round(4),
        )),
        showscale=True,
        opacity=0.85,
    )
    if zmid is not None:
        heatmap_kwargs["zmid"] = zmid

    # Use a square marker approximation via go.Scatter with large square markers
    # (go.Heatmap requires a uniform grid; our bins are uniform so we can use it)
    bin_w = float(x_edges[1] - x_edges[0])
    bin_h = float(y_edges[1] - y_edges[0])
    fig.add_trace(go.Scatter(
        x=agg["x"], y=agg["y"],
        mode="markers",
        marker=dict(
            symbol="square",
            size=max(6, int(min(bin_w, bin_h) * 0.09)),
            color=z,
            colorscale=cfg["colorscale"],
            reversescale=cfg["reversescale"],
            colorbar=heatmap_kwargs["colorbar"],
            showscale=True,
            opacity=0.82,
            **({"cmid": zmid} if zmid is not None else {}),
        ),
        hovertemplate=heatmap_kwargs["hovertemplate"],
        customdata=heatmap_kwargs["customdata"],
        showlegend=False,
        name=cfg["label"],
    ))

    _apply_court_layout(fig, player_name, season, season_type, len(df_shots))

    # Override title to include mode label
    mode_label = cfg["label"]
    fig.update_layout(
        title=dict(
            text=fig.layout.title.text + f"  ·  {mode_label}",
            font=dict(size=14), x=0.5, xanchor="center",
        )
    )
    return fig
