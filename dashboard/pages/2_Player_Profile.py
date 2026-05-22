"""
Player Profile page: season-over-season trends for any player.
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from scipy.stats import percentileofscore
from dashboard.utils.db import get_seasons, get_season_types
from dashboard.utils.queries import (
    get_player_names, get_player_career, get_player_pooled, get_league_distribution
)
from dashboard.utils.nba_static import player_headshot_url, team_color, team_logo_url

st.set_page_config(page_title="Player Profile · NBA Impact", page_icon="👤", layout="wide")
st.title("👤 Player Profile")


# ── Selection ────────────────────────────────────────────────────────────────
all_names = get_player_names()
default_name = "Nikola Joki\u0107" if "Nikola Joki\u0107" in all_names else all_names[0]

sel_col1, sel_col2 = st.columns([3, 1])
player_name = sel_col1.selectbox(
    "Search player", all_names,
    index=all_names.index(default_name) if default_name in all_names else 0,
)
season_type = sel_col2.selectbox("Season Type", get_season_types())

df = get_player_career(player_name, season_type)
df_pooled = get_player_pooled(player_name)
if not df_pooled.empty:
    df_pooled = df_pooled[df_pooled["season_type"] == season_type]

if df.empty:
    st.warning(f"No shot data found for **{player_name}** ({season_type}).")
    st.stop()

latest = df.iloc[-1]
latest_season = latest["season"]
person_id = int(latest["person_id"])
team = str(latest["team"])

# ── Header: headshot + key metrics ───────────────────────────────────────────
h_img, h_info = st.columns([1, 5])

with h_img:
    try:
        st.image(player_headshot_url(person_id), width=150)
    except Exception:
        st.markdown("👤")

with h_info:
    tcolor = team_color(team)
    st.markdown(
        f"<h2 style='margin-bottom:4px'>{player_name}</h2>"
        f"<span style='font-size:1.1rem; color:{tcolor}; font-weight:600'>{team}</span>"
        f"<span style='color:#888'> · {latest_season} ({season_type})</span>",
        unsafe_allow_html=True,
    )

    # Fetch league distribution for percentile context
    seasons = get_seasons()
    dist = get_league_distribution(latest_season, season_type, min_poss=500)

    def pct_rank(col: str, val) -> str:
        if pd.isna(val) or dist.empty or col not in dist.columns:
            return "—"
        clean = dist[col].dropna()
        if len(clean) < 5:
            return "—"
        p = percentileofscore(clean, float(val))
        return f"{p:.0f}th"

    rapm_val  = latest["rapm"]
    xrapm_val = latest["xrapm"]
    ppg_val   = latest["ppg"]
    mpg_val   = latest["mpg"]
    smoe_val  = latest["fg_pct_above_expected"]
    xshot_val = latest["mean_xshot"]

    m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
    m1.metric("RAPM",
              f"{float(rapm_val):.2f}" if pd.notna(rapm_val) else "—",
              delta=pct_rank("rapm", rapm_val),
              delta_color="off",
              help="Net pts/100 poss vs avg player — percentile shown")
    m2.metric("xRAPM",
              f"{float(xrapm_val):.2f}" if pd.notna(xrapm_val) else "—",
              delta=pct_rank("xrapm", xrapm_val),
              delta_color="off",
              help="Expected pts/100 poss vs avg player")
    m3.metric("FG% vs Expected",
              f"{float(smoe_val):.3f}" if pd.notna(smoe_val) else "—",
              delta=pct_rank("fg_pct_above_expected", smoe_val),
              delta_color="off",
              help="Actual FG% minus predicted FG% — shot-making above expectation")
    m4.metric("Avg Shot Quality",
              f"{float(xshot_val):.3f}" if pd.notna(xshot_val) else "—",
              help="Mean xShot of attempts taken — higher = harder shots attempted")
    m5.metric("PPG",
              f"{float(ppg_val):.1f}" if pd.notna(ppg_val) else "—",
              help="Points per game")
    m6.metric("MPG",
              f"{float(mpg_val):.1f}" if pd.notna(mpg_val) else "—",
              help="Minutes per game")
    m7.metric("GP",
              f"{int(latest['gp'])}" if pd.notna(latest['gp']) else "—",
              help="Games played")

st.markdown("---")

# ── Impact trend ─────────────────────────────────────────────────────────────
st.subheader("Impact Rating Trend")
st.caption(
    "RAPM reflects actual scoring margin per 100 possessions. "
    "xRAPM uses expected shot value — it is more stable across short samples "
    "and less affected by hot/cold shooting streaks. "
    "Values above 0 indicate above-average impact."
)

df_rapm = df[df["rapm"].notna() | df["xrapm"].notna()]

if not df_rapm.empty:
    # Identify career best seasons
    best_rapm_idx = df_rapm["rapm"].idxmax() if df_rapm["rapm"].notna().any() else None

    fig_rapm = go.Figure()
    if df_rapm["rapm"].notna().any():
        fig_rapm.add_trace(go.Scatter(
            x=df_rapm["season"], y=df_rapm["rapm"],
            mode="lines+markers", name="RAPM",
            line=dict(color="#E8462A", width=2.5),
            marker=dict(size=8),
            hovertemplate="%{x}: <b>%{y:.2f}</b> RAPM<extra></extra>",
        ))
    if df_rapm["xrapm"].notna().any():
        fig_rapm.add_trace(go.Scatter(
            x=df_rapm["season"], y=df_rapm["xrapm"],
            mode="lines+markers", name="xRAPM",
            line=dict(color="#4C9BE8", width=2.5, dash="dash"),
            marker=dict(size=8),
            hovertemplate="%{x}: <b>%{y:.2f}</b> xRAPM<extra></extra>",
        ))

    # Mark career-best RAPM season
    if best_rapm_idx is not None and best_rapm_idx in df_rapm.index:
        best_row = df_rapm.loc[best_rapm_idx]
        fig_rapm.add_annotation(
            x=best_row["season"], y=float(best_row["rapm"]),
            text=f"Career best<br>{float(best_row['rapm']):.2f}",
            showarrow=True, arrowhead=2, arrowcolor="#E8462A",
            font=dict(size=11, color="#E8462A"),
            ax=0, ay=-35,
        )

    fig_rapm.add_hline(y=0, line_dash="dot", line_color="gray", opacity=0.5,
                       annotation_text="League avg", annotation_position="right")
    fig_rapm.update_layout(
        xaxis_title="Season",
        yaxis_title="Points per 100 Possessions (vs league avg)",
        height=370,
        legend=dict(orientation="h", y=1.08),
        hovermode="x unified",
    )
    st.plotly_chart(fig_rapm, use_container_width=True)

    # Pooled v2
    if not df_pooled.empty:
        with st.expander("📊 Multi-year pooled RAPM+Prior (v2) — more stable long-run view"):
            st.caption(
                "Each point covers a 3-season rolling window ending at that season. "
                "RAPM+Prior is shrunk toward the player's historical plus/minus "
                "baseline — better for career comparisons."
            )
            fig_pool = go.Figure()
            fig_pool.add_trace(go.Scatter(
                x=df_pooled["window_label"], y=df_pooled["rapm_prior"],
                mode="lines+markers", name="RAPM+Prior",
                line=dict(color="#F4D03F", width=2.5),
                marker=dict(size=9),
                hovertemplate="%{x}: <b>%{y:.2f}</b><extra></extra>",
            ))
            fig_pool.add_trace(go.Scatter(
                x=df_pooled["window_label"], y=df_pooled["rapm"],
                mode="lines+markers", name="RAPM (raw pooled)",
                line=dict(color="#AAB7B8", width=1.5, dash="dot"),
                marker=dict(size=6),
                hovertemplate="%{x}: <b>%{y:.2f}</b> raw<extra></extra>",
            ))
            fig_pool.add_hline(y=0, line_dash="dot", line_color="gray", opacity=0.5)
            fig_pool.update_layout(
                xaxis_title="3-yr Window (end season)",
                yaxis_title="Pts / 100 Poss",
                height=300,
                legend=dict(orientation="h", y=1.08),
                hovermode="x unified",
            )
            st.plotly_chart(fig_pool, use_container_width=True)
else:
    st.info(
        f"**{player_name}** does not have enough possessions (≥1,000) to "
        "produce a stable RAPM estimate in any season."
    )

# ── Shot quality trend ────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Shot Quality Trend")
st.caption(
    "**FG% vs Expected** (bars): how much the player outperforms or underperforms the "
    "difficulty of their own shot attempts. Green = making harder shots than expected. "
    "Red = underperforming on their shot menu.\n\n"
    "**Mean xShot** (line, right axis): average difficulty of shots attempted. "
    "Higher = tougher shot menu."
)

df_shot = df[df["mean_xshot"].notna()]
if not df_shot.empty:
    fig_shot = go.Figure()
    fig_shot.add_trace(go.Bar(
        x=df_shot["season"],
        y=df_shot["fg_pct_above_expected"],
        name="FG% vs Expected",
        marker_color=["#2ECC71" if v >= 0 else "#E74C3C" for v in df_shot["fg_pct_above_expected"]],
        hovertemplate="%{x}: <b>%{y:+.3f}</b> FG% vs expected<extra></extra>",
    ))
    fig_shot.add_trace(go.Scatter(
        x=df_shot["season"],
        y=df_shot["mean_xshot"],
        name="Avg Shot Difficulty (xShot)",
        mode="lines+markers",
        line=dict(color="#F4D03F", width=2),
        yaxis="y2",
        hovertemplate="%{x}: <b>%{y:.3f}</b> avg xShot<extra></extra>",
    ))
    fig_shot.add_hline(y=0, line_dash="dot", line_color="gray", opacity=0.4)
    fig_shot.update_layout(
        yaxis=dict(title="FG% vs Expected  (Actual − Predicted)"),
        yaxis2=dict(title="Avg Shot Difficulty (xShot)", overlaying="y", side="right",
                    showgrid=False),
        height=370,
        legend=dict(orientation="h", y=1.08),
        hovermode="x unified",
    )
    st.plotly_chart(fig_shot, use_container_width=True)

# ── Career stats table ────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Career Stats by Season")
st.caption(
    "All counting stats are **per game**. "
    "RAPM and xRAPM require ≥1,000 possessions — blank = insufficient sample. "
    "Shot quality metrics (Avg xShot, FG% vs Exp) only require ≥1 field goal attempt."
)

table_df = df.sort_values("season", ascending=False).reset_index(drop=True)

st.dataframe(
    table_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "person_id":             None,  # hide
        "season":                st.column_config.TextColumn("Season"),
        "team":                  st.column_config.TextColumn("Team"),
        "gp":                    st.column_config.NumberColumn("GP", format="%d"),
        "ppg":                   st.column_config.NumberColumn("PPG", format="%.1f",
                                     help="Points per game"),
        "rpg":                   st.column_config.NumberColumn("RPG", format="%.1f"),
        "apg":                   st.column_config.NumberColumn("APG", format="%.1f"),
        "spg":                   st.column_config.NumberColumn("SPG", format="%.1f"),
        "bpg":                   st.column_config.NumberColumn("BPG", format="%.1f"),
        "mpg":                   st.column_config.NumberColumn("MPG", format="%.1f"),
        "season_plus_minus":     st.column_config.NumberColumn("+/-", format="%.0f",
                                     help="Raw season plus/minus (total, not per game)"),
        "rapm":                  st.column_config.NumberColumn("RAPM", format="%.2f",
                                     help="Net actual pts/100 poss vs avg"),
        "xrapm":                 st.column_config.NumberColumn("xRAPM", format="%.2f",
                                     help="Net expected pts/100 poss vs avg"),
        "rapm_vs_xrapm":         st.column_config.NumberColumn("RAPM−xRAPM", format="%.2f"),
        "possessions":           st.column_config.NumberColumn("Stint Poss", format="%.0f"),
        "shots_attempted":       st.column_config.NumberColumn("FGA", format="%d",
                                     help="Total field goal attempts in dataset"),
        "actual_fg_pct":         st.column_config.NumberColumn("FG%", format="%.3f"),
        "mean_xshot":            st.column_config.NumberColumn("Avg xShot", format="%.3f",
                                     help="Average shot difficulty"),
        "fg_pct_above_expected": st.column_config.NumberColumn("FG% vs Exp", format="+.3f",
                                     help="Shot-making above expectation"),
        "shot_pts_above_expected": st.column_config.NumberColumn("Pts Above Exp", format="%.0f"),
    },
    column_order=[
        "season", "team", "gp", "ppg", "rpg", "apg", "spg", "bpg", "mpg",
        "season_plus_minus", "rapm", "xrapm", "rapm_vs_xrapm", "possessions",
        "shots_attempted", "actual_fg_pct", "mean_xshot",
        "fg_pct_above_expected", "shot_pts_above_expected",
    ],
)
