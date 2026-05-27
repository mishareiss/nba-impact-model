"""
Reusable Plotly chart builders for the NBA xShot + RAPM dashboard.

All functions:
  - Accept data in, return a go.Figure
  - Contain zero Streamlit calls (pure Plotly)
  - Are safe to call from any page
  - Use the shared theme constants from utils/theme.py

Chart builders
--------------
  percentile_bar_chart()     Baseball Savant-style horizontal percentile bars
  zone_efficiency_chart()    FG% by shot zone vs xShot baseline
  zone_frequency_chart()     Donut chart of shot distribution by zone
  impact_trend_chart()       RAPM/xRAPM season trend line
  shot_quality_trend()       FG% vs expected bars + shot difficulty line
  calibration_curve_fig()    Predicted vs actual make rate (model evaluation)
  feature_importance_fig()   XGBoost gain importance horizontal bars
  shot_difficulty_dist_fig() Distribution of xShot probabilities
  stability_scatter_fig()    Year-to-year RAPM/xRAPM scatter (with R²)
  process_vs_results_fig()   Shot difficulty vs FG% above expected scatter
  rapm_distribution_fig()    League RAPM/xRAPM KDE histogram with player markers
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy.stats import percentileofscore

from .court import ZONE_ORDER, ZONE_LABELS
from .theme import (
    ACCENT, ACCENT_BLUE, ACCENT_GREEN, ACCENT_RED, ACCENT_GOLD,
    MUTED, MUTED_LIGHT, GRID, ZERO_LINE, SURFACE,
    TIER_LEGEND, TIER_ELITE, TIER_GREAT, TIER_ABOVE, TIER_AVG, TIER_BELOW, TIER_POOR,
    tier_color, chart_layout, MODEBAR,
)

# ---------------------------------------------------------------------------
# Colour helpers (kept for backwards compatibility)
# ---------------------------------------------------------------------------

def pct_color(p: float) -> str:
    """Map a percentile (0–100) to a tier hex colour."""
    return tier_color(p)


def team_pct_color(p: float) -> str:
    return tier_color(p)

# ---------------------------------------------------------------------------
# Percentile bar chart  (Baseball Savant-style)
# ---------------------------------------------------------------------------

def percentile_bar_chart(
    player_row: pd.Series,
    dist_df: pd.DataFrame,
    sections: list[tuple[str, list[tuple[str, str, str, bool]]]],
    title: str = "",
) -> go.Figure | None:
    """
    Horizontal bar chart with section headers as visual dividers.

    Parameters
    ----------
    player_row : Series — the player's row from the deduped CTE
    dist_df    : DataFrame — all players in the same season for percentile ranking
    sections   : List of (section_name, [(col, display_label, fmt_spec, higher_is_better)])
    title      : Optional figure title (displayed at top)
    """
    labels, pcts, val_texts, colors, is_header = [], [], [], [], []

    for section_name, metrics in sections:
        section_rows: list[tuple] = []
        for col, label, fmt, higher_better in metrics:
            val = (
                player_row.get(col)
                if isinstance(player_row, dict)
                else (player_row[col] if col in player_row.index else None)
            )
            if val is None or pd.isna(val):
                continue
            val = float(val)
            p = 50.0
            if col in dist_df.columns:
                clean = dist_df[col].dropna()
                if len(clean) >= 5:
                    p = percentileofscore(clean, val, kind="rank")
                    if not higher_better:
                        p = 100.0 - p
            section_rows.append((label, p, f"{val:{fmt}}"))

        if not section_rows:
            continue

        # Section header row
        labels.append(f"  ─ {section_name}")
        pcts.append(0.0)
        val_texts.append("")
        colors.append("rgba(0,0,0,0)")
        is_header.append(True)

        for label, p, vtxt in section_rows:
            labels.append(label)
            pcts.append(p)
            val_texts.append(vtxt)
            colors.append(pct_color(p))
            is_header.append(False)

    if not any(not h for h in is_header):
        return None

    n = len(labels)
    fig = go.Figure()

    # Background bars
    bg_colors = ["rgba(0,0,0,0)" if h else "rgba(80,80,80,0.15)" for h in is_header]
    fig.add_trace(go.Bar(
        x=[100] * n, y=labels, orientation="h",
        marker_color=bg_colors, marker_line_width=0,
        showlegend=False, hoverinfo="skip",
    ))

    # Coloured foreground bars
    fig.add_trace(go.Bar(
        x=pcts, y=labels, orientation="h",
        marker_color=colors, marker_line_width=0,
        text=[
            "" if h else f"  {v}   <b>{p:.0f}<sup>th</sup></b>"
            for v, p, h in zip(val_texts, pcts, is_header)
        ],
        textposition="outside", cliponaxis=False,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Value: %{customdata}<br>"
            "Percentile: %{x:.0f}th<extra></extra>"
        ),
        customdata=val_texts,
        showlegend=False,
    ))

    # Reference lines
    for x_ref, lbl in [(25, "25th"), (50, "Avg"), (75, "75th")]:
        fig.add_vline(
            x=x_ref, line_dash="dot",
            line_color="rgba(200,200,200,0.35)",
            annotation_text=lbl,
            annotation_position="top",
            annotation_font_size=10,
            annotation_font_color="rgba(200,200,200,0.6)",
        )

    row_height = [30 if h else 50 for h in is_header]
    total_h = sum(row_height) + 80

    fig.update_layout(
        title=dict(text=title, font=dict(size=14), x=0.5, xanchor="center") if title else None,
        barmode="overlay",
        xaxis=dict(range=[0, 140], showticklabels=False, showgrid=False, zeroline=False),
        yaxis=dict(autorange="reversed", automargin=True, tickfont=dict(size=12)),
        height=total_h,
        margin=dict(l=20, r=130, t=30 if not title else 55, b=50),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        annotations=[dict(
            text=TIER_LEGEND, showarrow=False,
            xref="paper", yref="paper", x=0, y=-0.06,
            xanchor="left", font=dict(size=11),
        )],
    )
    return fig


# ---------------------------------------------------------------------------
# Zone efficiency chart
# ---------------------------------------------------------------------------

def zone_efficiency_chart(
    df_zones: pd.DataFrame,
    league_zones: pd.DataFrame | None = None,
    player_name: str = "",
    color: str = "#E8462A",
    title: str = "Shot Zone Breakdown",
) -> go.Figure:
    """
    Horizontal bar chart of FG% by shot zone with xShot baseline markers.

    If league_zones provided, adds a grey league-average reference dot per zone.
    """
    _labels = {
        "at_rim":    "At Rim",
        "short_mid": "Short Mid",
        "mid_range": "Mid-Range",
        "long_mid":  "Long Mid",
        "three":     "3-Point",
    }

    df = (
        df_zones[df_zones["shot_zone"].isin(ZONE_ORDER)]
        .copy()
        .assign(zone_label=lambda d: d["shot_zone"].map(_labels))
        .set_index("shot_zone").reindex(ZONE_ORDER)
        .reset_index()
        .dropna(subset=["fg_pct"])
    )

    if df.empty:
        fig = go.Figure()
        fig.update_layout(title=title, height=300,
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        return fig

    df["fg_vs_xshot"] = (df["fg_pct"].fillna(0) - df["mean_xshot"].fillna(0))
    bar_colors = [
        "#2ECC71" if v >= 0 else "#E74C3C" for v in df["fg_vs_xshot"]
    ]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=df["fg_pct"],
        y=df["zone_label"],
        orientation="h",
        name="Actual FG%",
        marker_color=bar_colors,
        marker_line_width=0,
        text=[f"{v:.3f}" for v in df["fg_pct"]],
        textposition="outside",
        cliponaxis=False,
        hovertemplate=(
            "Zone: %{y}<br>"
            "FG%: %{x:.3f}<br>"
            "vs Expected: %{customdata[0]:+.3f}<br>"
            "Attempts: %{customdata[1]}<extra></extra>"
        ),
        customdata=list(zip(df["fg_vs_xshot"], df.get("attempts", [0]*len(df)))),
    ))

    # xShot reference dots (player)
    fig.add_trace(go.Scatter(
        x=df["mean_xshot"],
        y=df["zone_label"],
        mode="markers",
        name="Expected FG% (xShot)",
        marker=dict(symbol="line-ns", size=16, color="rgba(248,196,30,0.9)",
                    line=dict(width=3, color="rgba(248,196,30,0.9)")),
        hovertemplate="Expected FG%: %{x:.3f}<extra></extra>",
    ))

    # League average reference dots (if provided)
    if league_zones is not None and not league_zones.empty:
        lg = (
            league_zones[league_zones["shot_zone"].isin(ZONE_ORDER)]
            .set_index("shot_zone").reindex(ZONE_ORDER).reset_index()
            .dropna(subset=["fg_pct"])
        )
        lg["zone_label"] = lg["shot_zone"].map(_labels)
        fig.add_trace(go.Scatter(
            x=lg["fg_pct"],
            y=lg["zone_label"],
            mode="markers",
            name="League Avg FG%",
            marker=dict(symbol="diamond", size=9, color="rgba(160,160,160,0.8)",
                        line=dict(width=1, color="rgba(220,220,220,0.6)")),
            hovertemplate="League avg FG%: %{x:.3f}<extra></extra>",
        ))

    max_x = max(df["fg_pct"].max(), 0.75)
    fig.update_layout(
        title=dict(text=f"{player_name} — {title}" if player_name else title,
                   font=dict(size=13), x=0, xanchor="left"),
        xaxis=dict(range=[0, max_x * 1.25], showgrid=True,
                   gridcolor="rgba(80,80,80,0.3)", tickformat=".0%",
                   title="FG%"),
        yaxis=dict(automargin=True, tickfont=dict(size=12), autorange="reversed"),
        height=280,
        margin=dict(l=10, r=80, t=40, b=30),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=-0.15, x=0),
        barmode="overlay",
    )
    return fig


def zone_frequency_chart(
    df_zones: pd.DataFrame,
    player_name: str = "",
    color: str = "#E8462A",
) -> go.Figure:
    """Pie-style donut chart showing shot frequency distribution by zone."""
    _labels = {
        "at_rim":    "At Rim",
        "short_mid": "Short Mid",
        "mid_range": "Mid-Range",
        "long_mid":  "Long Mid",
        "three":     "3-Point",
    }
    _colors = {
        "at_rim":    "#3498DB",
        "short_mid": "#2ECC71",
        "mid_range": "#F1C40F",
        "long_mid":  "#E67E22",
        "three":     "#E74C3C",
    }

    df = (
        df_zones[df_zones["shot_zone"].isin(ZONE_ORDER)]
        .copy()
        .set_index("shot_zone").reindex(ZONE_ORDER).reset_index()
        .dropna(subset=["attempts"])
    )
    if df.empty:
        return go.Figure()

    fig = go.Figure(go.Pie(
        labels=[_labels.get(z, z) for z in df["shot_zone"]],
        values=df["attempts"],
        marker_colors=[_colors.get(z, "#888") for z in df["shot_zone"]],
        hole=0.55,
        textinfo="percent+label",
        textfont_size=12,
        hovertemplate="%{label}<br>%{value:,} attempts (%{percent})<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text=f"{player_name} — Shot Distribution" if player_name else "Shot Distribution",
                   font=dict(size=13), x=0.5, xanchor="center"),
        height=280,
        margin=dict(l=10, r=10, t=40, b=10),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    return fig


# ---------------------------------------------------------------------------
# Impact trend chart
# ---------------------------------------------------------------------------

def impact_trend_chart(
    df: pd.DataFrame,
    player_name: str = "",
    show_od: bool = True,
) -> go.Figure | None:
    """
    Season-over-season RAPM/xRAPM/O-RAPM/D-RAPM trend line chart.

    Parameters
    ----------
    df         : career stats DataFrame with columns season, rapm, xrapm, o_rapm, d_rapm
    player_name: for annotation
    show_od    : whether to include O-RAPM / D-RAPM traces
    """
    df_r = df[df["rapm"].notna() | df["xrapm"].notna()]
    if df_r.empty:
        return None

    fig = go.Figure()

    if df_r["rapm"].notna().any():
        fig.add_trace(go.Scatter(
            x=df_r["season"], y=df_r["rapm"],
            mode="lines+markers", name="RAPM",
            line=dict(color="#E8462A", width=2.5), marker=dict(size=8),
            hovertemplate="%{x}: <b>%{y:+.2f}</b> RAPM<extra></extra>",
        ))

    if df_r["xrapm"].notna().any():
        fig.add_trace(go.Scatter(
            x=df_r["season"], y=df_r["xrapm"],
            mode="lines+markers", name="xRAPM",
            line=dict(color="#4C9BE8", width=2.5, dash="dash"), marker=dict(size=8),
            hovertemplate="%{x}: <b>%{y:+.2f}</b> xRAPM<extra></extra>",
        ))

    if show_od:
        if "o_rapm" in df_r.columns and df_r["o_rapm"].notna().any():
            fig.add_trace(go.Scatter(
                x=df_r["season"], y=df_r["o_rapm"],
                mode="lines+markers", name="O-RAPM",
                line=dict(color="#F4D03F", width=1.8, dash="dot"), marker=dict(size=6),
                hovertemplate="%{x}: <b>%{y:+.2f}</b> O-RAPM<extra></extra>",
            ))
        if "d_rapm" in df_r.columns and df_r["d_rapm"].notna().any():
            fig.add_trace(go.Scatter(
                x=df_r["season"], y=df_r["d_rapm"],
                mode="lines+markers", name="D-RAPM",
                line=dict(color="#2ECC71", width=1.8, dash="dot"), marker=dict(size=6),
                hovertemplate="%{x}: <b>%{y:+.2f}</b> D-RAPM<extra></extra>",
            ))

    # Career-best annotation
    if df_r["rapm"].notna().any():
        best_idx = df_r["rapm"].idxmax()
        best = df_r.loc[best_idx]
        fig.add_annotation(
            x=best["season"], y=float(best["rapm"]),
            text=f"Career best<br>{float(best['rapm']):+.2f}",
            showarrow=True, arrowhead=2, arrowcolor="#E8462A",
            font=dict(size=10, color="#E8462A"), ax=0, ay=-38,
        )

    fig.add_hline(y=0, line_dash="dot", line_color="rgba(200,200,200,0.4)",
                  annotation_text="League avg", annotation_position="right",
                  annotation_font_color="rgba(180,180,180,0.7)")

    fig.update_layout(
        title=dict(text=player_name if player_name else "", font=dict(size=13)),
        xaxis_title="Season",
        yaxis_title="Pts / 100 Poss (vs avg)",
        height=360,
        legend=dict(orientation="h", y=1.08),
        hovermode="x unified",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


# ---------------------------------------------------------------------------
# Dual-player comparison overlay
# ---------------------------------------------------------------------------

def dual_trend_chart(
    df_a: pd.DataFrame, name_a: str, color_a: str,
    df_b: pd.DataFrame, name_b: str, color_b: str,
    metric: str = "rapm",
    metric_label: str = "RAPM",
) -> go.Figure | None:
    """
    Single-metric trend for two players on the same chart — used on Compare page.
    """
    col_a = df_a[df_a[metric].notna()] if metric in df_a.columns else pd.DataFrame()
    col_b = df_b[df_b[metric].notna()] if metric in df_b.columns else pd.DataFrame()

    if col_a.empty and col_b.empty:
        return None

    fig = go.Figure()

    if not col_a.empty:
        fig.add_trace(go.Scatter(
            x=col_a["season"], y=col_a[metric],
            mode="lines+markers", name=name_a,
            line=dict(color=color_a, width=2.5), marker=dict(size=8),
            hovertemplate=f"%{{x}}: <b>%{{y:+.2f}}</b> {metric_label}<extra></extra>",
        ))

    if not col_b.empty:
        fig.add_trace(go.Scatter(
            x=col_b["season"], y=col_b[metric],
            mode="lines+markers", name=name_b,
            line=dict(color=color_b, width=2.5, dash="dash"), marker=dict(size=8),
            hovertemplate=f"%{{x}}: <b>%{{y:+.2f}}</b> {metric_label}<extra></extra>",
        ))

    fig.add_hline(y=0, line_dash="dot", line_color="rgba(200,200,200,0.35)")
    fig.update_layout(
        yaxis_title=f"{metric_label} (pts/100 poss vs avg)",
        xaxis_title="Season",
        height=340,
        legend=dict(orientation="h", y=1.08),
        hovermode="x unified",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


# ---------------------------------------------------------------------------
# Shot quality trend (FG% vs expected + difficulty)
# ---------------------------------------------------------------------------

def shot_quality_trend(df: pd.DataFrame) -> go.Figure | None:
    """Bar + dual-axis line chart: FG% vs expected per season + avg shot difficulty."""
    df_s = df[df["mean_xshot"].notna()]
    if df_s.empty:
        return None

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df_s["season"],
        y=df_s["fg_pct_above_expected"],
        name="FG% vs Expected",
        marker_color=[
            ACCENT_GREEN if v >= 0 else ACCENT_RED
            for v in df_s["fg_pct_above_expected"]
        ],
        hovertemplate="%{x}: <b>%{y:+.3f}</b> FG% vs expected<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=df_s["season"], y=df_s["mean_xshot"],
        name="Avg Shot Difficulty",
        mode="lines+markers",
        line=dict(color=ACCENT_GOLD, width=2),
        yaxis="y2",
        hovertemplate="%{x}: <b>%{y:.3f}</b> avg xShot<extra></extra>",
    ))
    fig.add_hline(y=0, line_dash="dot", line_color=ZERO_LINE)
    fig.update_layout(
        yaxis=dict(title="FG% vs Expected"),
        yaxis2=dict(title="Avg Shot Difficulty (xShot)",
                    overlaying="y", side="right", showgrid=False),
        height=350,
        legend=dict(orientation="h", y=1.08),
        hovermode="x unified",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


# ---------------------------------------------------------------------------
# Model evaluation charts
# ---------------------------------------------------------------------------

def calibration_curve_fig(data: dict) -> go.Figure:
    """
    Interactive calibration curve: predicted make probability vs actual make rate.

    A well-calibrated model's curve hugs the diagonal. Deviations reveal
    systematic over- or under-confidence in specific probability ranges.

    Parameters
    ----------
    data : dict from load_calibration_data() with keys mean_predicted,
           fraction_positive.
    """
    x = data["mean_predicted"]
    y = data["fraction_positive"]

    fig = go.Figure()

    # Perfect calibration reference line
    fig.add_trace(go.Scatter(
        x=[0, 1], y=[0, 1],
        mode="lines",
        name="Perfect calibration",
        line=dict(color="rgba(160,165,175,0.45)", width=1.5, dash="dash"),
        hoverinfo="skip",
    ))

    # Model calibration curve
    fig.add_trace(go.Scatter(
        x=x, y=y,
        mode="lines+markers",
        name="xShot model",
        line=dict(color=ACCENT, width=2.5),
        marker=dict(size=7, color=ACCENT,
                    line=dict(width=1.5, color="rgba(255,255,255,0.3)")),
        hovertemplate=(
            "Predicted: <b>%{x:.3f}</b><br>"
            "Actual make rate: <b>%{y:.3f}</b><extra></extra>"
        ),
    ))

    # Shade the calibration gap
    fig.add_trace(go.Scatter(
        x=x + x[::-1],
        y=y + list(x)[::-1],
        fill="toself",
        fillcolor="rgba(232,70,42,0.07)",
        line=dict(color="rgba(0,0,0,0)"),
        showlegend=False,
        hoverinfo="skip",
        name="gap",
    ))

    fig.update_layout(
        **chart_layout(height=380, hovermode="x unified"),
        xaxis=dict(title="Predicted probability (xShot)", range=[0, 1],
                   showgrid=True, gridcolor=GRID, zeroline=False,
                   tickformat=".0%"),
        yaxis=dict(title="Actual make rate", range=[0, 1],
                   showgrid=True, gridcolor=GRID, zeroline=False,
                   tickformat=".0%"),
    )
    return fig


def feature_importance_fig(data: dict, top_n: int = 15) -> go.Figure:
    """
    Horizontal bar chart of normalised XGBoost gain importance.

    Shows the top_n most influential features. Bars are coloured by
    category: spatial features use blue, shot-type flags use orange,
    context features use grey.

    Parameters
    ----------
    data   : dict from load_feature_importance() with keys features, importance.
    top_n  : number of features to display (sorted by importance descending).
    """
    features = data["features"]
    importance = data["importance"]

    pairs = sorted(zip(features, importance), key=lambda x: x[1])
    pairs = pairs[-top_n:]  # top N by importance (sorted ascending for h-bar)

    feats, imps = zip(*pairs)

    # Colour by feature category
    _SPATIAL = {"shot_distance", "shot_angle", "x_legacy", "y_legacy",
                "shot_zone", "is_corner_three", "is_paint"}
    _CONTEXT = {"period", "clock_seconds", "is_overtime", "is_playoffs",
                "shot_value", "is_three"}

    colors = []
    for f in feats:
        if f in _SPATIAL:
            colors.append(ACCENT_BLUE)
        elif f in _CONTEXT:
            colors.append(MUTED_LIGHT)
        else:
            colors.append(ACCENT_GOLD)   # shot-type flags

    # Clean up feature name display
    labels = [f.replace("is_", "").replace("_", " ").title() for f in feats]

    fig = go.Figure(go.Bar(
        x=list(imps),
        y=labels,
        orientation="h",
        marker_color=colors,
        marker_line_width=0,
        text=[f"{v:.1%}" for v in imps],
        textposition="outside",
        cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Importance: %{x:.2%}<extra></extra>",
    ))

    # Legend annotations for category colours
    fig.add_annotation(
        text=(
            f"<span style='color:{ACCENT_BLUE}'>■</span> Spatial  "
            f"<span style='color:{ACCENT_GOLD}'>■</span> Shot type  "
            f"<span style='color:{MUTED_LIGHT}'>■</span> Context"
        ),
        xref="paper", yref="paper", x=0, y=-0.06,
        showarrow=False, font=dict(size=11),
    )

    fig.update_layout(
        **chart_layout(height=max(300, top_n * 28 + 80)),
        xaxis=dict(title="Normalised gain importance", showgrid=True,
                   gridcolor=GRID, zeroline=False, tickformat=".0%",
                   range=[0, max(imps) * 1.3]),
        yaxis=dict(automargin=True, tickfont=dict(size=12)),
        margin=dict(l=20, r=100, t=40, b=60),
    )
    return fig


def shot_difficulty_dist_fig(df: pd.DataFrame) -> go.Figure:
    """
    Bar chart showing the distribution of xShot probabilities across all shots.

    Illustrates that the model captures the full range of shot difficulty —
    from near-certain dunks (~0.95) to highly contested long-twos (~0.25).

    Parameters
    ----------
    df : DataFrame from get_shot_difficulty_dist() with xshot_bin, n_shots columns.
    """
    if df.empty:
        return go.Figure()

    total = df["n_shots"].sum()
    df = df.copy()
    df["pct"] = df["n_shots"] / total

    # Colour bars by xShot range: low = harder (red), high = easier (green)
    colors = []
    for b in df["xshot_bin"]:
        b = float(b)
        if b >= 0.7:
            colors.append(ACCENT_GREEN)
        elif b >= 0.45:
            colors.append(ACCENT_GOLD)
        elif b >= 0.25:
            colors.append(ACCENT)
        else:
            colors.append(ACCENT_RED)

    fig = go.Figure(go.Bar(
        x=df["xshot_bin"],
        y=df["n_shots"],
        marker_color=colors,
        marker_line_width=0,
        hovertemplate=(
            "xShot bin: <b>%{x:.2f}</b><br>"
            "Shots: %{y:,}<br>"
            "Share: %{customdata:.1%}<extra></extra>"
        ),
        customdata=df["pct"],
        name="Shot count",
    ))

    fig.update_layout(
        **chart_layout(height=340),
        xaxis=dict(title="Predicted make probability (xShot)",
                   showgrid=True, gridcolor=GRID, zeroline=False,
                   tickformat=".2f"),
        yaxis=dict(title="Number of shots", showgrid=True, gridcolor=GRID,
                   zeroline=False),
        bargap=0.05,
    )
    return fig


# ---------------------------------------------------------------------------
# Stability analysis charts
# ---------------------------------------------------------------------------

def stability_scatter_fig(
    df_pairs: pd.DataFrame,
    metric: str = "rapm",
    label: str = "RAPM",
    color: str = ACCENT,
    highlight_names: list[str] | None = None,
) -> go.Figure | None:
    """
    Year-to-year scatter for a metric across consecutive seasons.

    Plots Year N vs Year N+1 for all player-season pairs.
    Adds an OLS regression line and displays R² in the title.

    Parameters
    ----------
    df_pairs        : DataFrame from get_stability_data() with {metric}_a / {metric}_b columns.
    metric          : "rapm" or "xrapm".
    highlight_names : Optional list of player names to highlight in a different colour.
    """
    col_a = f"{metric}_a"
    col_b = f"{metric}_b"

    if col_a not in df_pairs.columns or col_b not in df_pairs.columns:
        return None

    clean = df_pairs.dropna(subset=[col_a, col_b])
    if len(clean) < 10:
        return None

    x = clean[col_a].values.astype(float)
    y = clean[col_b].values.astype(float)

    # OLS for R²
    r = float(np.corrcoef(x, y)[0, 1])
    r2 = r ** 2

    # Regression line
    m, b_int = np.polyfit(x, y, 1)
    x_line = np.linspace(x.min() - 0.3, x.max() + 0.3, 80)
    y_line = m * x_line + b_int

    fig = go.Figure()

    # All players — background grey dots
    mask_hl = (
        clean["full_name"].isin(highlight_names) if highlight_names else pd.Series(False, index=clean.index)
    )
    bg = clean[~mask_hl]

    fig.add_trace(go.Scatter(
        x=bg[col_a], y=bg[col_b],
        mode="markers",
        marker=dict(size=6, color="rgba(160,165,175,0.35)",
                    line=dict(width=0.5, color="rgba(200,200,200,0.2)")),
        hovertemplate=(
            "<b>%{customdata}</b><br>"
            f"Year N {label}: %{{x:+.2f}}<br>"
            f"Year N+1 {label}: %{{y:+.2f}}<extra></extra>"
        ),
        customdata=bg["full_name"],
        name="All players",
        showlegend=False,
    ))

    # Highlighted players
    if highlight_names:
        hl = clean[mask_hl]
        if not hl.empty:
            fig.add_trace(go.Scatter(
                x=hl[col_a], y=hl[col_b],
                mode="markers+text",
                marker=dict(size=10, color=color,
                            line=dict(width=1.5, color="rgba(255,255,255,0.5)")),
                text=hl["full_name"].apply(lambda n: n.split()[-1]),
                textposition="top center",
                textfont=dict(size=10, color=color),
                hovertemplate=(
                    "<b>%{customdata}</b><br>"
                    f"Year N: %{{x:+.2f}}<br>"
                    f"Year N+1: %{{y:+.2f}}<extra></extra>"
                ),
                customdata=hl["full_name"],
                name="Selected",
            ))

    # Regression line
    fig.add_trace(go.Scatter(
        x=x_line, y=y_line,
        mode="lines",
        line=dict(color=color, width=2, dash="dash"),
        name=f"OLS fit  (R²={r2:.2f})",
        hoverinfo="skip",
    ))

    fig.add_hline(y=0, line_dash="dot", line_color=ZERO_LINE)
    fig.add_vline(x=0, line_dash="dot", line_color=ZERO_LINE)

    n_pairs = len(clean)
    fig.update_layout(
        **chart_layout(height=420, hovermode="closest"),
        xaxis=dict(title=f"Year N {label} (pts/100 poss)", showgrid=True,
                   gridcolor=GRID, zeroline=False),
        yaxis=dict(title=f"Year N+1 {label} (pts/100 poss)", showgrid=True,
                   gridcolor=GRID, zeroline=False),
        annotations=[dict(
            text=f"R² = {r2:.3f}  ·  n = {n_pairs:,} player-season pairs",
            xref="paper", yref="paper", x=0.01, y=0.98,
            showarrow=False,
            font=dict(size=12, color=MUTED_LIGHT),
            align="left",
        )],
    )
    return fig


# ---------------------------------------------------------------------------
# Process vs Results scatter
# ---------------------------------------------------------------------------

def process_vs_results_fig(
    df_all: pd.DataFrame,
    highlight_row: pd.Series | None = None,
    highlight_label: str = "",
    color: str = ACCENT,
) -> go.Figure:
    """
    Scatter plot: shot difficulty (mean xShot) vs shot-making (FG% above expected).

    Contextualises where a player sits in the shot-quality landscape:
      Top-right  → takes hard shots AND beats expectation (elite finisher)
      Top-left   → beats expectation on easier looks (selective efficiency)
      Bottom-right → takes hard shots but underperforms expectation
      Bottom-left  → easy shots + underperforms (weakest profile)

    Parameters
    ----------
    df_all        : league-wide DataFrame from get_process_vs_results().
    highlight_row : optional single-player row to label and colour distinctly.
    """
    if df_all.empty:
        return go.Figure()

    fig = go.Figure()

    # Background players
    mask_hl = (
        (df_all["full_name"] == highlight_label) if highlight_label else pd.Series(False, index=df_all.index)
    )
    bg = df_all[~mask_hl]

    fig.add_trace(go.Scatter(
        x=bg["mean_xshot"],
        y=bg["fg_pct_above_expected"],
        mode="markers",
        marker=dict(
            size=6,
            color="rgba(160,165,175,0.30)",
            line=dict(width=0.5, color="rgba(200,200,200,0.15)"),
        ),
        hovertemplate=(
            "<b>%{customdata[0]}</b>  (%{customdata[1]})<br>"
            "Avg xShot: %{x:.3f}<br>"
            "FG% vs Expected: %{y:+.3f}<extra></extra>"
        ),
        customdata=list(zip(bg["full_name"], bg["team"])),
        name="All players",
        showlegend=False,
    ))

    # Highlighted player
    if highlight_row is not None:
        hx = float(highlight_row.get("mean_xshot", np.nan))
        hy = float(highlight_row.get("fg_pct_above_expected", np.nan))
        if not (np.isnan(hx) or np.isnan(hy)):
            fig.add_trace(go.Scatter(
                x=[hx], y=[hy],
                mode="markers+text",
                marker=dict(size=14, color=color,
                            line=dict(width=2, color="rgba(255,255,255,0.6)")),
                text=[highlight_label.split()[-1] if highlight_label else ""],
                textposition="top center",
                textfont=dict(size=12, color=color),
                hovertemplate=(
                    f"<b>{highlight_label}</b><br>"
                    "Avg xShot: %{x:.3f}<br>"
                    "FG% vs Expected: %{y:+.3f}<extra></extra>"
                ),
                name=highlight_label or "Selected",
            ))

    # Quadrant reference lines
    x_med = float(df_all["mean_xshot"].median())
    fig.add_hline(y=0, line_dash="dot", line_color=ZERO_LINE,
                  annotation_text="League avg FG% vs expected",
                  annotation_font_color=MUTED, annotation_position="right")
    fig.add_vline(x=x_med, line_dash="dot", line_color=ZERO_LINE,
                  annotation_text=f"Median xShot ({x_med:.3f})",
                  annotation_font_color=MUTED, annotation_position="top")

    fig.update_layout(
        **chart_layout(height=420, hovermode="closest"),
        xaxis=dict(title="Avg Shot Difficulty (mean xShot)", showgrid=True,
                   gridcolor=GRID, zeroline=False),
        yaxis=dict(title="FG% Above Expected (Shot-Making)", showgrid=True,
                   gridcolor=GRID, zeroline=False, tickformat="+.3f"),
    )
    return fig


# ---------------------------------------------------------------------------
# RAPM/xRAPM distribution with player markers
# ---------------------------------------------------------------------------

def rapm_distribution_fig(
    df: pd.DataFrame,
    selected_names: list[str] | None = None,
) -> go.Figure:
    """
    Overlapping KDE histograms of RAPM and xRAPM with optional vertical
    player-marker lines.

    Demonstrates that the metric values form a bell curve centred near zero,
    and lets users see where highlighted players land in the distribution.

    Parameters
    ----------
    df             : DataFrame with columns full_name, rapm, xrapm.
    selected_names : Optional list of player names to mark with vertical lines.
    """
    from scipy.stats import gaussian_kde

    fig = go.Figure()

    for col, name, color in [
        ("rapm",  "RAPM",  ACCENT),
        ("xrapm", "xRAPM", ACCENT_BLUE),
    ]:
        vals = df[col].dropna().values
        if len(vals) < 5:
            continue

        fig.add_trace(go.Histogram(
            x=vals, name=name, nbinsx=30,
            marker_color=color.replace("#", "rgba(") + ",0.45)" if color.startswith("#")
                         else color,
            marker_line_width=0, opacity=0.6,
            hovertemplate=f"{name}: %{{x:.2f}}<br>Players: %{{y}}<extra></extra>",
        ))

        kde = gaussian_kde(vals, bw_method=0.4)
        x_range = np.linspace(vals.min() - 0.5, vals.max() + 0.5, 200)
        bin_w = (vals.max() - vals.min()) / 30
        y_kde = kde(x_range) * len(vals) * bin_w
        fig.add_trace(go.Scatter(
            x=x_range, y=y_kde, mode="lines",
            line=dict(color=color, width=2),
            showlegend=False, hoverinfo="skip",
        ))

    # Reference lines
    fig.add_vline(x=0, line_dash="dot", line_color=ZERO_LINE,
                  annotation_text="League avg",
                  annotation_font_color=MUTED, annotation_position="top right")

    # Player markers
    if selected_names:
        pal = [ACCENT_GOLD, ACCENT_GREEN, "rgba(220,220,255,0.9)"]
        for i, name in enumerate(selected_names[:3]):
            row = df[df["full_name"] == name]
            if row.empty:
                continue
            rapm_val = float(row.iloc[0]["rapm"])
            c = pal[i % len(pal)]
            fig.add_vline(
                x=rapm_val, line_dash="solid", line_color=c, line_width=2,
                annotation_text=name.split()[-1],
                annotation_font_color=c, annotation_position="top",
                annotation_font_size=10,
            )

    fig.update_layout(
        **chart_layout(height=360, hovermode="closest"),
        barmode="overlay",
        xaxis=dict(title="RAPM / xRAPM (pts/100 poss vs avg)",
                   showgrid=True, gridcolor=GRID, zeroline=False),
        yaxis=dict(title="Player count", showgrid=True, gridcolor=GRID, zeroline=False),
    )
    return fig
