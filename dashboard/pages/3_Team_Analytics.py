"""
Team Analytics page: offensive/defensive shot quality and season-over-season trends.
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from scipy.stats import percentileofscore
from dashboard.utils.db import get_seasons, get_season_types
from dashboard.utils.queries import (
    get_team_shot_quality, get_team_trend, get_all_teams, get_team_league_distribution,
)
from dashboard.utils.nba_static import TEAM_COLORS, team_color

st.set_page_config(page_title="Team Analytics · NBA Impact", page_icon="🏟", layout="wide")
st.title("🏟 Team Shot Quality Analytics")


# ── Team percentile chart helpers ─────────────────────────────────────────────

# (col_in_dist_df, display_label, higher_is_better)
TEAM_METRIC_SECTIONS = [
    ("OFFENSE", [
        ("pts_above_expected_off", "Points Above Expected (Offense)",  True),
        ("mean_xshot_off",         "Avg Shot Quality Generated",        True),
        ("fg_pct",                 "Offensive FG%",                     True),
        ("net_pts_above_expected", "Net Points Above Expected",          True),
    ]),
    ("DEFENSE", [
        ("pts_saved_on_defense",  "Points Saved on Defense",      True),
        ("xshot_suppression",     "Shot Quality Suppression",      True),
        ("fg_pct_def_inverted",   "Defensive FG% Allowed (lower = better)", True),
    ]),
]


def _team_pct_color(p: float) -> str:
    if p >= 90: return "#1A9E4E"
    if p >= 75: return "#2ECC71"
    if p >= 60: return "#A4C429"
    if p >= 40: return "#C8A82A"
    if p >= 25: return "#E67E22"
    return "#E74C3C"


def team_percentile_chart(
    team_row: pd.Series,
    dist_df: pd.DataFrame,
    highlight_color: str = "#4C9BE8",
) -> go.Figure | None:
    """
    Baseball Savant-style horizontal bar chart for a single team vs all 30 teams.
    Sections: Offense / Defense.
    """
    labels, pcts, val_texts, colors, is_header = [], [], [], [], []

    for section_name, metrics in TEAM_METRIC_SECTIONS:
        labels.append(f"  ─ {section_name}")
        pcts.append(0.0)
        val_texts.append("")
        colors.append("rgba(0,0,0,0)")
        is_header.append(True)

        has_any = False
        for col, label, higher_better in metrics:
            if col not in team_row.index or col not in dist_df.columns:
                continue
            val = team_row[col]
            if pd.isna(val):
                continue
            val = float(val)
            clean = dist_df[col].dropna()
            if len(clean) < 2:
                continue
            p = percentileofscore(clean, val, kind="rank")
            if not higher_better:
                p = 100.0 - p

            # Format value depending on scale
            if "pct" in col or "fg_pct" in col:
                v_str = f"{val:.3f}"
            elif abs(val) >= 10:
                v_str = f"{val:+.0f}"
            else:
                v_str = f"{val:+.3f}"

            labels.append(label)
            pcts.append(p)
            val_texts.append(v_str)
            colors.append(_team_pct_color(p))
            is_header.append(False)
            has_any = True

        if not has_any:
            labels.pop(); pcts.pop(); val_texts.pop()
            colors.pop(); is_header.pop()

    if not any(not h for h in is_header):
        return None

    n = len(labels)
    bg_colors = ["rgba(0,0,0,0)" if h else "rgba(80,80,80,0.15)" for h in is_header]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[100] * n, y=labels, orientation="h",
        marker_color=bg_colors, marker_line_width=0,
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_trace(go.Bar(
        x=pcts, y=labels, orientation="h",
        marker_color=colors, marker_line_width=0,
        text=[
            "" if h else f"  {v}   <b>{p:.0f}<sup>th</sup></b>"
            for v, p, h in zip(val_texts, pcts, is_header)
        ],
        textposition="outside",
        cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Value: %{customdata}<br>Percentile: %{x:.0f}th<extra></extra>",
        customdata=val_texts,
        showlegend=False,
    ))

    for x_ref, lbl in [(25, "25th"), (50, "Avg"), (75, "75th")]:
        fig.add_vline(
            x=x_ref, line_dash="dot",
            line_color="rgba(200,200,200,0.35)",
            annotation_text=lbl, annotation_position="top",
            annotation_font_size=10,
            annotation_font_color="rgba(200,200,200,0.6)",
        )

    tier_legend = (
        "<span style='color:#1A9E4E'>■</span> Elite (≥90th)  "
        "<span style='color:#2ECC71'>■</span> Great (75–90th)  "
        "<span style='color:#A4C429'>■</span> Above avg (60–75th)  "
        "<span style='color:#C8A82A'>■</span> Average (40–60th)  "
        "<span style='color:#E67E22'>■</span> Below avg (25–40th)  "
        "<span style='color:#E74C3C'>■</span> Poor (&lt;25th)"
    )

    row_heights = [28 if h else 48 for h in is_header]
    fig.update_layout(
        barmode="overlay",
        xaxis=dict(range=[0, 145], showticklabels=False, showgrid=False, zeroline=False),
        yaxis=dict(autorange="reversed", automargin=True, tickfont=dict(size=12)),
        height=sum(row_heights) + 80,
        margin=dict(l=20, r=130, t=20, b=50),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        annotations=[dict(
            text=tier_legend, showarrow=False,
            xref="paper", yref="paper", x=0, y=-0.08,
            xanchor="left", font=dict(size=11),
        )],
    )
    return fig
st.caption(
    "Shot quality is measured by **xShot** — the model-predicted probability any given "
    "field goal attempt is made. Teams that generate high-quality shots offensively "
    "and allow low-quality shots defensively tend to sustain winning over time."
)

# ── Filters ──────────────────────────────────────────────────────────────────
seasons = get_seasons()
default_season = "2024-25" if "2024-25" in seasons else seasons[0]
col1, col2 = st.columns(2)
season      = col1.selectbox("Season", seasons, index=seasons.index(default_season), key="ta_season")
season_type = col2.selectbox("Season Type", get_season_types(), key="ta_stype")

df = get_team_shot_quality(season, season_type)

if df.empty:
    st.warning("No team data for this selection.")
    st.stop()

# ── Summary metrics ───────────────────────────────────────────────────────────
top_net   = df.iloc[0]
worst_net = df.iloc[-1]
top_off   = df.sort_values("pts_above_expected_off", ascending=False).iloc[0]
top_def   = df.sort_values("pts_above_expected_def").iloc[0]

m1, m2, m3, m4 = st.columns(4)
tcolor = lambda t: team_color(t)
m1.metric(
    "Best Net Shot Quality",
    f"{top_net['team']}  {float(top_net['net_pts_above_expected']):+.0f} pts",
    help="Net = Offensive Pts Above Expected minus Defensive Pts Conceded Above Expected",
)
m2.metric(
    "Best Offense",
    f"{top_off['team']}  {float(top_off['pts_above_expected_off']):+.0f} pts",
    help="Total points scored above xShot expectation for the season",
)
m3.metric(
    "Best Defense",
    f"{top_def['team']}  {float(top_def['pts_above_expected_def']):+.0f} pts",
    help="Total points conceded vs xShot expectation — negative = better defense",
)
m4.metric(
    "League Avg xShot Generated",
    f"{float(df['mean_xshot_off'].mean()):.3f}",
    help="Average xShot probability of all shots taken (league-wide)",
)

st.markdown("---")

# ── Scatter: xShot off vs xShot def ──────────────────────────────────────────
st.subheader("Shot Quality Map — Offense vs Defense")
st.caption(
    "**Best teams: top-left** — generating high-difficulty shots offensively "
    "while allowing low-difficulty shots defensively. "
    "Dashed lines = league average. Dot size ∝ total field goal attempts."
)

avg_off = float(df["mean_xshot_off"].mean())
avg_def = float(df["mean_xshot_def"].mean())

# Build per-team color list using team primary colors
df["_color"] = df["team"].apply(lambda t: team_color(str(t)))
color_map = {str(t): team_color(str(t)) for t in df["team"]}

hover_scatter = [
    f"<b>{row['team']}</b>  ({row['team_name']})<br>"
    f"xShot Generated: {float(row['mean_xshot_off']):.3f}<br>"
    f"xShot Allowed: {float(row['mean_xshot_def']):.3f}<br>"
    f"Off Pts Above Exp: {float(row['pts_above_expected_off']):+.0f}<br>"
    f"Def Pts Above Exp: {float(row['pts_above_expected_def']):+.0f}<br>"
    f"Net: {float(row['net_pts_above_expected']):+.0f}"
    for _, row in df.iterrows()
]

fig_scatter = px.scatter(
    df,
    x="mean_xshot_def",
    y="mean_xshot_off",
    text="team",
    color="team",
    color_discrete_map=color_map,
    size="fga",
    size_max=22,
    labels={
        "mean_xshot_def": "Avg xShot Allowed  (↓ better defense)",
        "mean_xshot_off": "Avg xShot Generated  (↑ better offense)",
    },
    title=f"Shot Quality Map  —  {season} {season_type}",
    height=560,
    custom_data=["team_name", "pts_above_expected_off", "pts_above_expected_def", "net_pts_above_expected"],
)
fig_scatter.update_traces(
    textposition="top center",
    marker=dict(line=dict(width=0.8, color="white")),
    hovertext=hover_scatter,
    hoverinfo="text",
)

# League average quadrant lines
fig_scatter.add_hline(y=avg_off, line_dash="dash", line_color="rgba(200,200,200,0.4)")
fig_scatter.add_vline(x=avg_def, line_dash="dash", line_color="rgba(200,200,200,0.4)")

# Quadrant labels
fig_scatter.add_annotation(
    x=df["mean_xshot_def"].min(), y=df["mean_xshot_off"].max(),
    text="Elite Offense\nElite Defense", showarrow=False,
    font=dict(color="#2ECC71", size=11), xanchor="left",
)
fig_scatter.add_annotation(
    x=df["mean_xshot_def"].max(), y=df["mean_xshot_off"].min(),
    text="Poor Offense\nPoor Defense", showarrow=False,
    font=dict(color="#E74C3C", size=11), xanchor="right",
)
fig_scatter.update_layout(
    showlegend=False,
    margin=dict(l=20, r=20, t=60, b=20),
)
st.plotly_chart(fig_scatter, use_container_width=True)

# ── Points Above Expected bar chart ──────────────────────────────────────────
st.markdown("---")
st.subheader("Points Above Expected — Offense & Defense")
st.caption(
    "**Offense (left bars)**: points scored above xShot expectation — measures shot-making. "
    "**Defense (right bars, inverted)**: negative = held opponents below expectation (good defense). "
    "Teams are sorted by net offensive+defensive advantage."
)

fig_bar = go.Figure()
# Offense bars
fig_bar.add_trace(go.Bar(
    name="Offense: Pts Above Exp",
    x=df["team"],
    y=df["pts_above_expected_off"],
    marker_color=[team_color(str(t)) for t in df["team"]],
    marker_opacity=0.9,
    hovertemplate="<b>%{x}</b>  Offense: %{y:+.0f} pts<extra></extra>",
))
# Defense bars (flip sign: negative original = good defense → show as positive green)
fig_bar.add_trace(go.Bar(
    name="Defense: Pts Conceded vs Exp (inverted)",
    x=df["team"],
    y=[-float(v) for v in df["pts_above_expected_def"]],
    marker_color=["#2ECC71" if float(v) <= 0 else "#E74C3C"
                  for v in df["pts_above_expected_def"]],
    marker_opacity=0.6,
    hovertemplate="<b>%{x}</b>  Def conceded vs exp: %{customdata:+.0f}<extra></extra>",
    customdata=df["pts_above_expected_def"],
))
fig_bar.add_hline(y=0, line_color="gray", opacity=0.4)
fig_bar.update_layout(
    barmode="group",
    xaxis_title="Team",
    yaxis_title="Points Above Expected",
    height=430,
    legend=dict(orientation="h", y=1.06),
    xaxis=dict(tickangle=-45),
)
st.plotly_chart(fig_bar, use_container_width=True)

# ── Full data table ───────────────────────────────────────────────────────────
with st.expander("📋 Full data table"):
    display_df = df.drop(columns=["_color", "season", "season_type"], errors="ignore")
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "team":                     st.column_config.TextColumn("Team"),
            "team_name":                st.column_config.TextColumn("Full Name"),
            "fga":                      st.column_config.NumberColumn("FGA (Off)", format="%d"),
            "fg_pct":                   st.column_config.NumberColumn("FG% (Off)", format="%.3f"),
            "mean_xshot_off":           st.column_config.NumberColumn("Avg xShot Off", format="%.3f"),
            "pts_above_expected_off":   st.column_config.NumberColumn("Pts Above Exp (Off)", format="+.0f"),
            "fga_allowed":              st.column_config.NumberColumn("FGA (Def)", format="%d"),
            "fg_pct_allowed":           st.column_config.NumberColumn("FG% Allowed", format="%.3f"),
            "mean_xshot_def":           st.column_config.NumberColumn("Avg xShot Allowed", format="%.3f"),
            "pts_above_expected_def":   st.column_config.NumberColumn("Pts Conceded vs Exp", format="+.0f"),
            "net_pts_above_expected":   st.column_config.NumberColumn("Net Pts Above Exp", format="+.0f"),
        },
        column_order=[
            "team", "team_name", "fga", "fg_pct", "mean_xshot_off",
            "pts_above_expected_off", "fga_allowed", "fg_pct_allowed",
            "mean_xshot_def", "pts_above_expected_def", "net_pts_above_expected",
        ],
    )

# ── Team Profile: percentile chart + season trend ────────────────────────────
st.markdown("---")
st.subheader("Team Profile")
st.caption(
    "Select a franchise to see its shot quality profile relative to all 30 teams "
    "for the current season, then track how it has evolved over time."
)

all_teams = get_all_teams()
default_team = "DEN" if "DEN" in all_teams else all_teams[0]
t1, t2, t3 = st.columns([2, 2, 2])
selected_team = t1.selectbox(
    "Franchise", all_teams,
    index=all_teams.index(default_team) if default_team in all_teams else 0,
    key="trend_team",
)
trend_stype = t2.selectbox("Season Type", get_season_types(), key="trend_stype")

# Percentile chart for selected team in the currently selected season
dist_teams = get_team_league_distribution(season, trend_stype)
if not dist_teams.empty and selected_team in dist_teams["team"].values:
    team_row = dist_teams[dist_teams["team"] == selected_team].iloc[0]
    fig_tpct = team_percentile_chart(team_row, dist_teams, highlight_color=team_color(selected_team))
    if fig_tpct is not None:
        st.markdown(
            f"**{selected_team}** percentile profile — {season} {trend_stype} "
            f"(vs all 30 teams)"
        )
        st.plotly_chart(fig_tpct, use_container_width=True)
elif not dist_teams.empty:
    st.info(f"No shot data for **{selected_team}** in {season} {trend_stype}.")

st.markdown("#### Season-over-Season Trend")
st.caption("Track how a franchise's shot quality profile has evolved since 2014-15.")

metric_label = t3.selectbox(
    "Metric",
    [
        "Shot Quality Generated vs Allowed",
        "Points Above Expected (Off + Def)",
        "FG% Offense vs Defense",
        "Net Points Above Expected",
    ],
    key="trend_metric",
)

df_trend = get_team_trend(selected_team, trend_stype)
tcolor_sel = team_color(selected_team)

if df_trend.empty:
    st.info(f"No trend data for {selected_team}.")
else:
    fig_trend = go.Figure()

    if metric_label == "Shot Quality Generated vs Allowed":
        fig_trend.add_trace(go.Scatter(
            x=df_trend["season"], y=df_trend["mean_xshot_off"],
            mode="lines+markers", name="xShot Generated",
            line=dict(color=tcolor_sel, width=2.5),
            hovertemplate="%{x}: <b>%{y:.3f}</b> xShot generated<extra></extra>",
        ))
        fig_trend.add_trace(go.Scatter(
            x=df_trend["season"], y=df_trend["mean_xshot_def"],
            mode="lines+markers", name="xShot Allowed",
            line=dict(color="#AAB7B8", width=2.5, dash="dash"),
            hovertemplate="%{x}: <b>%{y:.3f}</b> xShot allowed<extra></extra>",
        ))
        fig_trend.update_layout(yaxis_title="Mean xShot (0 = impossible, 1 = certain make)")

    elif metric_label == "Points Above Expected (Off + Def)":
        fig_trend.add_trace(go.Bar(
            x=df_trend["season"], y=df_trend["pts_above_expected_off"],
            name="Offense: Pts Above Exp",
            marker_color=[tcolor_sel] * len(df_trend),
            hovertemplate="%{x}: <b>%{y:+.0f}</b> off pts above exp<extra></extra>",
        ))
        fig_trend.add_trace(go.Bar(
            x=df_trend["season"], y=df_trend["pts_above_expected_def"],
            name="Defense: Pts Conceded vs Exp",
            marker_color=["#E74C3C" if float(v) > 0 else "#2ECC71"
                          for v in df_trend["pts_above_expected_def"]],
            hovertemplate="%{x}: <b>%{y:+.0f}</b> def pts vs exp<extra></extra>",
        ))
        fig_trend.update_layout(barmode="group", yaxis_title="Points vs Expected")

    elif metric_label == "FG% Offense vs Defense":
        fig_trend.add_trace(go.Scatter(
            x=df_trend["season"], y=df_trend["fg_pct"],
            mode="lines+markers", name="Offensive FG%",
            line=dict(color=tcolor_sel, width=2.5),
        ))
        fig_trend.add_trace(go.Scatter(
            x=df_trend["season"], y=df_trend["fg_pct_allowed"],
            mode="lines+markers", name="Defensive FG% Allowed",
            line=dict(color="#AAB7B8", width=2.5, dash="dash"),
        ))
        fig_trend.update_layout(yaxis_title="FG%")

    else:  # Net
        fig_trend.add_trace(go.Bar(
            x=df_trend["season"],
            y=df_trend["net_pts_above_expected"],
            marker_color=["#2ECC71" if float(v) >= 0 else "#E74C3C"
                          for v in df_trend["net_pts_above_expected"]],
            name="Net Pts Above Expected",
            hovertemplate="%{x}: <b>%{y:+.0f}</b> net pts above exp<extra></extra>",
        ))
        fig_trend.update_layout(yaxis_title="Net Points Above Expected")

    fig_trend.add_hline(y=0, line_dash="dot", line_color="gray", opacity=0.4)
    fig_trend.update_layout(
        title=f"{selected_team} — {metric_label}  ({trend_stype})",
        xaxis_title="Season",
        height=400,
        legend=dict(orientation="h", y=1.08),
        hovermode="x unified",
    )
    st.plotly_chart(fig_trend, use_container_width=True)
