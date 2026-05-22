"""
Team Analytics page: offensive/defensive shot quality and season-over-season trends.
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from dashboard.utils.db import get_seasons, get_season_types
from dashboard.utils.queries import get_team_shot_quality, get_team_trend, get_all_teams

st.set_page_config(page_title="Team Analytics · NBA Impact", page_icon="🏟", layout="wide")
st.title("🏟 Team Shot Quality Analytics")

# ── Season snapshot ──────────────────────────────────────────────────────────
st.subheader("Season Snapshot")
seasons = get_seasons()
default_season = "2024-25" if "2024-25" in seasons else seasons[0]
col1, col2 = st.columns(2)
season = col1.selectbox("Season", seasons, index=seasons.index(default_season), key="ta_season")
season_type = col2.selectbox("Season Type", get_season_types(), key="ta_stype")

df = get_team_shot_quality(season, season_type)

if df.empty:
    st.warning("No team data for this selection.")
    st.stop()

# ── Key metrics ──────────────────────────────────────────────────────────────
top_off = df.iloc[0]
top_def = df.sort_values("pts_above_expected_def").iloc[0]

m1, m2, m3, m4 = st.columns(4)
m1.metric("Best Offense (Pts+Exp)", f"{top_off['team']}  +{top_off['pts_above_expected_off']:.0f}")
m2.metric("Avg xShot Generated", f"{float(df['mean_xshot_off'].mean()):.3f}")
m3.metric("Best Defense (Pts+Exp)", f"{top_def['team']}  {top_def['pts_above_expected_def']:.0f}")
m4.metric("Avg xShot Allowed", f"{float(df['mean_xshot_def'].mean()):.3f}")

st.markdown("---")

# ── Scatter: xShot off vs xShot def ─────────────────────────────────────────
st.subheader("Offensive vs Defensive Shot Quality")
st.caption("Best teams: top-left (generate high-quality shots, allow low-quality shots)")

fig_scatter = px.scatter(
    df,
    x="mean_xshot_def",
    y="mean_xshot_off",
    text="team",
    color="net_pts_above_expected",
    color_continuous_scale="RdYlGn",
    size="fga",
    labels={
        "mean_xshot_def": "Mean xShot Allowed (↓ better)",
        "mean_xshot_off": "Mean xShot Generated (↑ better)",
        "net_pts_above_expected": "Net Pts Above Exp",
    },
    title=f"Shot Quality: Offense vs Defense — {season} {season_type}",
    height=520,
)
fig_scatter.update_traces(textposition="top center", marker=dict(line=dict(width=0.5, color="white")))
# Add quadrant lines at league average
avg_off = float(df["mean_xshot_off"].mean())
avg_def = float(df["mean_xshot_def"].mean())
fig_scatter.add_hline(y=avg_off, line_dash="dash", line_color="gray", opacity=0.4)
fig_scatter.add_vline(x=avg_def, line_dash="dash", line_color="gray", opacity=0.4)
st.plotly_chart(fig_scatter, use_container_width=True)

# ── Pts above expected bar chart ─────────────────────────────────────────────
st.subheader("Points Above Expected — Offense & Defense")

fig_bar = go.Figure()
fig_bar.add_trace(go.Bar(
    x=df["team"],
    y=df["pts_above_expected_off"],
    name="Offense",
    marker_color=["#2ECC71" if v >= 0 else "#E74C3C" for v in df["pts_above_expected_off"]],
))
fig_bar.add_trace(go.Bar(
    x=df["team"],
    y=[-v for v in df["pts_above_expected_def"]],  # flip sign: negative = good defense
    name="Defense (inverted)",
    marker_color=["#2ECC71" if v <= 0 else "#E74C3C" for v in df["pts_above_expected_def"]],
))
fig_bar.update_layout(
    barmode="group",
    xaxis_title="Team",
    yaxis_title="Points Above Expected",
    height=420,
    legend=dict(orientation="h", y=1.06),
)
st.plotly_chart(fig_bar, use_container_width=True)

# ── Full table ────────────────────────────────────────────────────────────────
with st.expander("Full data table"):
    display_cols = {
        "team": "Team", "fga": "FGA", "fg_pct": "FG%",
        "mean_xshot_off": "xShot Off", "pts_above_expected_off": "Pts+Exp Off",
        "fga_allowed": "FGA Allowed", "fg_pct_allowed": "FG% Allowed",
        "mean_xshot_def": "xShot Def", "pts_above_expected_def": "Pts+Exp Def",
        "net_pts_above_expected": "Net Pts+Exp",
    }
    available = [c for c in display_cols if c in df.columns]
    st.dataframe(
        df[available].rename(columns={c: display_cols[c] for c in available}),
        use_container_width=True,
        hide_index=True,
    )

# ── Season trend for one team ────────────────────────────────────────────────
st.markdown("---")
st.subheader("Season-over-Season Trend")

all_teams = get_all_teams()
default_team = "DEN" if "DEN" in all_teams else all_teams[0]
col_t1, col_t2 = st.columns([2, 2])
selected_team = col_t1.selectbox("Team", all_teams,
                                  index=all_teams.index(default_team) if default_team in all_teams else 0,
                                  key="trend_team")
trend_stype = col_t2.selectbox("Season Type", get_season_types(), key="trend_stype")

df_trend = get_team_trend(selected_team, trend_stype)

if df_trend.empty:
    st.info(f"No trend data for {selected_team}.")
else:
    metric = st.radio(
        "Metric",
        ["mean_xshot_off / mean_xshot_def", "pts_above_expected_off / pts_above_expected_def",
         "fg_pct / fg_pct_allowed", "net_pts_above_expected"],
        horizontal=True,
        key="trend_metric",
    )

    fig_trend = go.Figure()

    if metric == "mean_xshot_off / mean_xshot_def":
        fig_trend.add_trace(go.Scatter(x=df_trend["season"], y=df_trend["mean_xshot_off"],
                                       mode="lines+markers", name="xShot Generated",
                                       line=dict(color="#E8462A", width=2.5)))
        fig_trend.add_trace(go.Scatter(x=df_trend["season"], y=df_trend["mean_xshot_def"],
                                       mode="lines+markers", name="xShot Allowed",
                                       line=dict(color="#4C9BE8", width=2.5)))
        fig_trend.update_layout(yaxis_title="Mean xShot")

    elif metric == "pts_above_expected_off / pts_above_expected_def":
        fig_trend.add_trace(go.Bar(x=df_trend["season"], y=df_trend["pts_above_expected_off"],
                                   name="Off Pts Above Exp",
                                   marker_color=["#2ECC71" if v >= 0 else "#E74C3C"
                                                 for v in df_trend["pts_above_expected_off"]]))
        fig_trend.add_trace(go.Bar(x=df_trend["season"], y=df_trend["pts_above_expected_def"],
                                   name="Def Pts Above Exp",
                                   marker_color=["#E74C3C" if v >= 0 else "#2ECC71"
                                                 for v in df_trend["pts_above_expected_def"]]))
        fig_trend.update_layout(barmode="group", yaxis_title="Pts Above Expected")

    elif metric == "fg_pct / fg_pct_allowed":
        fig_trend.add_trace(go.Scatter(x=df_trend["season"], y=df_trend["fg_pct"],
                                       mode="lines+markers", name="FG%",
                                       line=dict(color="#E8462A", width=2.5)))
        fig_trend.add_trace(go.Scatter(x=df_trend["season"], y=df_trend["fg_pct_allowed"],
                                       mode="lines+markers", name="FG% Allowed",
                                       line=dict(color="#4C9BE8", width=2.5)))
        fig_trend.update_layout(yaxis_title="FG%")

    else:  # net
        fig_trend.add_trace(go.Bar(
            x=df_trend["season"], y=df_trend["net_pts_above_expected"],
            marker_color=["#2ECC71" if v >= 0 else "#E74C3C"
                          for v in df_trend["net_pts_above_expected"]],
            name="Net Pts Above Exp",
        ))
        fig_trend.update_layout(yaxis_title="Net Pts Above Expected")

    fig_trend.add_hline(y=0, line_dash="dot", line_color="gray", opacity=0.4)
    fig_trend.update_layout(
        title=f"{selected_team} — {metric} ({trend_stype})",
        xaxis_title="Season",
        height=380,
        legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(fig_trend, use_container_width=True)
