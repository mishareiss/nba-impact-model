"""
Reusable Plotly chart builders for the NBA analytics dashboard.

All functions:
  - Accept data in, return a go.Figure
  - Contain zero Streamlit calls (pure Plotly)
  - Are safe to call from any page
  - Use consistent styling with the dark Streamlit theme

Extracted and generalized from 2_Player_Profile.py and 3_Team_Analytics.py so
both pages (and the new Compare page) share identical rendering logic.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from scipy.stats import percentileofscore

from .court import ZONE_ORDER, ZONE_LABELS

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def pct_color(p: float) -> str:
    """Map a percentile (0-100) to a tier colour."""
    if p >= 90: return "#1A9E4E"
    if p >= 75: return "#2ECC71"
    if p >= 60: return "#A4C429"
    if p >= 40: return "#C8A82A"
    if p >= 25: return "#E67E22"
    return "#E74C3C"


def team_pct_color(p: float) -> str:
    """Same tier scale, slightly different palette for team charts."""
    return pct_color(p)


TIER_LEGEND = (
    "<span style='color:#1A9E4E'>■</span> Elite (≥90th)  "
    "<span style='color:#2ECC71'>■</span> Great (75–89th)  "
    "<span style='color:#A4C429'>■</span> Above avg (60–74th)  "
    "<span style='color:#C8A82A'>■</span> Average (40–59th)  "
    "<span style='color:#E67E22'>■</span> Below avg (25–39th)  "
    "<span style='color:#E74C3C'>■</span> Poor (&lt;25th)"
)

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
            "#2ECC71" if v >= 0 else "#E74C3C"
            for v in df_s["fg_pct_above_expected"]
        ],
        hovertemplate="%{x}: <b>%{y:+.3f}</b> FG% vs expected<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=df_s["season"], y=df_s["mean_xshot"],
        name="Avg Shot Difficulty",
        mode="lines+markers",
        line=dict(color="#F4D03F", width=2),
        yaxis="y2",
        hovertemplate="%{x}: <b>%{y:.3f}</b> avg xShot<extra></extra>",
    ))
    fig.add_hline(y=0, line_dash="dot", line_color="rgba(200,200,200,0.4)")
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
