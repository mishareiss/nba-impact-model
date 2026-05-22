"""
Player Profile page: season-over-season trend analysis for any player.
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
from dashboard.utils.db import get_season_types
from dashboard.utils.queries import get_player_names, get_player_career, get_player_pooled

st.set_page_config(page_title="Player Profile · NBA Impact", page_icon="👤", layout="wide")
st.title("👤 Player Profile")

# ── Selection ────────────────────────────────────────────────────────────────
all_names = get_player_names()
default_name = "Nikola Joki\u0107" if "Nikola Joki\u0107" in all_names else all_names[0]
col1, col2 = st.columns([3, 1])
player_name = col1.selectbox("Player", all_names,
                              index=all_names.index(default_name) if default_name in all_names else 0)
season_type = col2.selectbox("Season Type", get_season_types())

df = get_player_career(player_name, season_type)
df_pooled = get_player_pooled(player_name)

if df.empty:
    st.warning(f"No data found for {player_name} ({season_type}).")
    st.stop()

# ── Header metrics (most recent season) ─────────────────────────────────────
latest = df.iloc[-1]
st.subheader(f"{player_name}  ·  {latest['team']}  ·  {latest['season']}")

m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("RAPM", f"{float(latest['rapm']):.2f}" if pd.notna(latest['rapm']) else "—")
m2.metric("xRAPM", f"{float(latest['xrapm']):.2f}" if pd.notna(latest['xrapm']) else "—")
m3.metric("Mean xShot", f"{float(latest['mean_xshot']):.3f}" if pd.notna(latest['mean_xshot']) else "—")
m4.metric("FG% Above Exp", f"{float(latest['fg_pct_above_expected']):.3f}" if pd.notna(latest['fg_pct_above_expected']) else "—")
m5.metric("PPG", f"{float(latest['pts']):.1f}" if pd.notna(latest['pts']) else "—")
m6.metric("GP", f"{int(latest['gp'])}" if pd.notna(latest['gp']) else "—")

st.markdown("---")

# ── RAPM trend ───────────────────────────────────────────────────────────────
st.subheader("Impact Rating Trend")
df_rapm = df[df["rapm"].notna() | df["xrapm"].notna()]

if not df_rapm.empty:
    fig_rapm = go.Figure()
    if df_rapm["rapm"].notna().any():
        fig_rapm.add_trace(go.Scatter(
            x=df_rapm["season"], y=df_rapm["rapm"],
            mode="lines+markers", name="RAPM", line=dict(color="#E8462A", width=2.5),
            marker=dict(size=8),
        ))
    if df_rapm["xrapm"].notna().any():
        fig_rapm.add_trace(go.Scatter(
            x=df_rapm["season"], y=df_rapm["xrapm"],
            mode="lines+markers", name="xRAPM", line=dict(color="#4C9BE8", width=2.5, dash="dash"),
            marker=dict(size=8),
        ))
    fig_rapm.add_hline(y=0, line_dash="dot", line_color="gray", opacity=0.5)
    fig_rapm.update_layout(
        xaxis_title="Season", yaxis_title="Points per 100 Poss",
        height=360, legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(fig_rapm, use_container_width=True)

    if not df_pooled.empty:
        with st.expander("Multi-year pooled RAPM (v2)"):
            fig_pool = go.Figure()
            fig_pool.add_trace(go.Scatter(
                x=df_pooled["window_label"], y=df_pooled["rapm_prior"],
                mode="lines+markers", name="RAPM+Prior", line=dict(color="#F4D03F", width=2.5),
                marker=dict(size=8),
            ))
            fig_pool.add_hline(y=0, line_dash="dot", line_color="gray", opacity=0.5)
            fig_pool.update_layout(xaxis_title="3-yr Window", yaxis_title="Pts / 100 Poss", height=300)
            st.plotly_chart(fig_pool, use_container_width=True)
else:
    st.info("Not enough possessions for RAPM in any season.")

# ── Shot quality trend ───────────────────────────────────────────────────────
st.subheader("Shot Quality Trend")
df_shot = df[df["mean_xshot"].notna()]

if not df_shot.empty:
    fig_shot = go.Figure()
    fig_shot.add_trace(go.Bar(
        x=df_shot["season"], y=df_shot["fg_pct_above_expected"],
        name="FG% Above Expected",
        marker_color=["#2ECC71" if v >= 0 else "#E74C3C"
                      for v in df_shot["fg_pct_above_expected"]],
    ))
    fig_shot.add_trace(go.Scatter(
        x=df_shot["season"], y=df_shot["mean_xshot"],
        name="Mean xShot (shot quality)", mode="lines+markers",
        line=dict(color="#4C9BE8", width=2), yaxis="y2",
    ))
    fig_shot.update_layout(
        yaxis=dict(title="FG% Above Expected"),
        yaxis2=dict(title="Mean xShot", overlaying="y", side="right"),
        height=360, legend=dict(orientation="h", y=1.08),
    )
    st.plotly_chart(fig_shot, use_container_width=True)

# ── Box score table ──────────────────────────────────────────────────────────
st.subheader("Season Stats")
box_cols = {
    "season": "Season", "team": "Team", "gp": "GP", "min": "MIN",
    "pts": "PTS", "reb": "REB", "ast": "AST", "stl": "STL", "blk": "BLK",
    "season_plus_minus": "+/-", "xrapm": "xRAPM", "rapm": "RAPM",
    "shots_attempted": "FGA", "mean_xshot": "xShot",
    "fg_pct_above_expected": "FG% +/-",
}
available = [c for c in box_cols if c in df.columns]
st.dataframe(
    df[available].rename(columns={c: box_cols[c] for c in available})
      .sort_values("Season", ascending=False)
      .reset_index(drop=True),
    use_container_width=True,
    hide_index=True,
)
