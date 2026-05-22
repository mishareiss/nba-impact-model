"""
Player Profile page: season-over-season trends + Baseball Savant-style percentile chart.
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
from dashboard.utils.db import get_season_types
from dashboard.utils.queries import (
    get_player_names, get_player_career, get_player_pooled, get_league_distribution
)
from dashboard.utils.nba_static import player_headshot_url, team_color

st.set_page_config(page_title="Player Profile · NBA Impact", page_icon="👤", layout="wide")
st.title("👤 Player Profile")


# ── Percentile chart helper ───────────────────────────────────────────────────

METRIC_GROUPS = [
    # (col, display_label, fmt_spec, higher_is_better)
    ("rapm",                   "RAPM — Overall Impact",          "+.2f", True),
    ("xrapm",                  "xRAPM — Expected Impact",        "+.2f", True),
    ("ppg",                    "Points Per Game",                ".1f",  True),
    ("apg",                    "Assists Per Game",               ".1f",  True),
    ("rpg",                    "Rebounds Per Game",              ".1f",  True),
    ("fg_pct_above_expected",  "FG% vs Expected (Shot-Making)",  "+.3f", True),
    ("shot_pts_above_expected","Points Above Expected",          "+.0f", True),
    ("mean_xshot",             "Avg Shot Difficulty (xShot)",    ".3f",  True),
]

# Group separators for the y-axis (blank row between sections)
_SECTION_LABELS = {
    "rapm":                   "── IMPACT ───────────────",
    "ppg":                    "── TRADITIONAL ──────────",
    "fg_pct_above_expected":  "── SHOT QUALITY ─────────",
}

def _pct_color(p: float) -> str:
    if p >= 90: return "#1A9E4E"
    if p >= 75: return "#2ECC71"
    if p >= 60: return "#A4C429"
    if p >= 40: return "#C8A82A"
    if p >= 25: return "#E67E22"
    return "#E74C3C"


def percentile_chart(player_row: pd.Series, dist_df: pd.DataFrame) -> go.Figure | None:
    """
    Builds a Baseball Savant-style horizontal bar chart.
    Each row = one metric. Bar width = percentile (0-100). Color = percentile tier.
    """
    labels, pcts, val_texts, colors = [], [], [], []

    for col, label, fmt, higher_better in METRIC_GROUPS:
        if col not in player_row.index or pd.isna(player_row[col]):
            continue
        val = float(player_row[col])

        p = 50.0
        if col in dist_df.columns:
            clean = dist_df[col].dropna()
            if len(clean) >= 10:
                p = percentileofscore(clean, val, kind="rank")
                if not higher_better:
                    p = 100.0 - p

        labels.append(label)
        pcts.append(p)
        val_texts.append(f"{val:{fmt}}")
        colors.append(_pct_color(p))

    if not labels:
        return None

    n = len(labels)
    fig = go.Figure()

    # Light gray background bar (0→100)
    fig.add_trace(go.Bar(
        x=[100] * n, y=labels, orientation="h",
        marker_color="rgba(80,80,80,0.18)",
        marker_line_width=0,
        showlegend=False, hoverinfo="skip",
    ))

    # Colored foreground bar (0→percentile)
    fig.add_trace(go.Bar(
        x=pcts, y=labels, orientation="h",
        marker_color=colors,
        marker_line_width=0,
        text=[
            f"  {v}   <b>{p:.0f}<sup>th</sup></b>"
            for v, p in zip(val_texts, pcts)
        ],
        textposition="outside",
        cliponaxis=False,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Value: %{customdata}<br>"
            "Percentile: %{x:.0f}th<extra></extra>"
        ),
        customdata=val_texts,
        showlegend=False,
    ))

    # Reference lines at 25 / 50 / 75
    for x_ref, label_ref in [(25, "25th"), (50, "Avg"), (75, "75th")]:
        fig.add_vline(
            x=x_ref, line_dash="dot",
            line_color="rgba(200,200,200,0.35)",
            annotation_text=label_ref,
            annotation_position="top",
            annotation_font_size=10,
            annotation_font_color="rgba(200,200,200,0.6)",
        )

    # Color legend annotation
    tier_legend = (
        "<span style='color:#1A9E4E'>■</span> Elite (≥90th)  "
        "<span style='color:#2ECC71'>■</span> Great (75–90th)  "
        "<span style='color:#A4C429'>■</span> Above avg (60–75th)  "
        "<span style='color:#C8A82A'>■</span> Average (40–60th)  "
        "<span style='color:#E67E22'>■</span> Below avg (25–40th)  "
        "<span style='color:#E74C3C'>■</span> Poor (&lt;25th)"
    )

    fig.update_layout(
        barmode="overlay",
        xaxis=dict(range=[0, 130], showticklabels=False,
                   showgrid=False, zeroline=False),
        yaxis=dict(autorange="reversed", automargin=True,
                   tickfont=dict(size=13)),
        height=n * 52 + 70,
        margin=dict(l=20, r=120, t=30, b=10),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        annotations=[dict(
            text=tier_legend, showarrow=False,
            xref="paper", yref="paper", x=0, y=-0.04,
            xanchor="left", font=dict(size=11),
        )],
    )
    return fig


# ── Selection ────────────────────────────────────────────────────────────────
all_names = get_player_names()
default_name = "Nikola Joki\u0107" if "Nikola Joki\u0107" in all_names else all_names[0]

sel1, sel2 = st.columns([3, 1])
player_name = sel1.selectbox("Search player", all_names,
                              index=all_names.index(default_name) if default_name in all_names else 0)
season_type = sel2.selectbox("Season Type", get_season_types())

df = get_player_career(player_name, season_type)
df_pooled = get_player_pooled(player_name)
if not df_pooled.empty:
    df_pooled = df_pooled[df_pooled["season_type"] == season_type]

if df.empty:
    st.warning(f"No shot data found for **{player_name}** ({season_type}).")
    st.stop()

latest = df.iloc[-1]
latest_season = str(latest["season"])
person_id = int(latest["person_id"])
team = str(latest["team"])

# ── Header: headshot + quick metrics ─────────────────────────────────────────
img_col, info_col = st.columns([1, 6])

with img_col:
    try:
        st.image(player_headshot_url(person_id), width=155)
    except Exception:
        st.markdown("👤")

with info_col:
    tcolor = team_color(team)
    traded = "TM" in team
    team_display = f"{team} (traded)" if traded else team
    st.markdown(
        f"<h2 style='margin-bottom:2px'>{player_name}</h2>"
        f"<span style='font-size:1.05rem;color:{tcolor};font-weight:600'>{team_display}</span>"
        f"&nbsp;<span style='color:#888'>· {latest_season} · {season_type}</span>",
        unsafe_allow_html=True,
    )
    st.markdown("")

    dist = get_league_distribution(latest_season, season_type, min_poss=500)

    def pct(col: str, val) -> str:
        if pd.isna(val) or dist.empty or col not in dist.columns:
            return "—"
        clean = dist[col].dropna()
        return f"{percentileofscore(clean, float(val), kind='rank'):.0f}th" if len(clean) >= 5 else "—"

    m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
    def _fmt(v, spec): return f"{float(v):{spec}}" if pd.notna(v) else "—"

    m1.metric("RAPM",            _fmt(latest["rapm"],  "+.2f"),
              delta=pct("rapm",  latest["rapm"]),  delta_color="off",
              help="Net actual pts/100 poss vs avg — percentile vs ≥500-poss players shown")
    m2.metric("xRAPM",           _fmt(latest["xrapm"], "+.2f"),
              delta=pct("xrapm", latest["xrapm"]), delta_color="off",
              help="Net expected pts/100 poss vs avg")
    m3.metric("FG% vs Expected", _fmt(latest["fg_pct_above_expected"], "+.3f"),
              delta=pct("fg_pct_above_expected", latest["fg_pct_above_expected"]),
              delta_color="off", help="Shot-making above expectation")
    m4.metric("Avg Shot Quality", _fmt(latest["mean_xshot"], ".3f"),
              help="Mean xShot of all attempts — higher = harder shots taken")
    m5.metric("PPG",  _fmt(latest["ppg"], ".1f"), help="Points per game")
    m6.metric("MPG",  _fmt(latest["mpg"], ".1f"), help="Minutes per game")
    m7.metric("GP",   f"{int(latest['gp'])}" if pd.notna(latest["gp"]) else "—")

st.markdown("---")

# ── Percentile Profile (Baseball Savant-style) ────────────────────────────────
st.subheader("Percentile Profile")
st.caption(
    f"Compared to all players with ≥500 stint possessions — {latest_season} {season_type}. "
    "Bar width = percentile rank. Colored by tier."
)

if not dist.empty:
    fig_pct = percentile_chart(latest, dist)
    if fig_pct is not None:
        st.plotly_chart(fig_pct, use_container_width=True)
    else:
        st.info("Insufficient data for percentile profile this season.")
else:
    st.info("League distribution unavailable for this season.")

st.markdown("---")

# ── Impact trend ──────────────────────────────────────────────────────────────
st.subheader("Impact Rating — Season Trend")
st.caption(
    "RAPM = actual outcomes. xRAPM = expected shot quality. "
    "Gap between them reflects shot-making variance — a player whose RAPM > xRAPM "
    "is outscoring their process (elite finishing or clutch play)."
)

df_rapm = df[df["rapm"].notna() | df["xrapm"].notna()]
if not df_rapm.empty:
    best_rapm_idx = df_rapm["rapm"].idxmax() if df_rapm["rapm"].notna().any() else None

    fig_rapm = go.Figure()
    if df_rapm["rapm"].notna().any():
        fig_rapm.add_trace(go.Scatter(
            x=df_rapm["season"], y=df_rapm["rapm"],
            mode="lines+markers", name="RAPM (Actual)",
            line=dict(color="#E8462A", width=2.5), marker=dict(size=8),
            hovertemplate="%{x}: <b>%{y:+.2f}</b> RAPM<extra></extra>",
        ))
    if df_rapm["xrapm"].notna().any():
        fig_rapm.add_trace(go.Scatter(
            x=df_rapm["season"], y=df_rapm["xrapm"],
            mode="lines+markers", name="xRAPM (Expected)",
            line=dict(color="#4C9BE8", width=2.5, dash="dash"), marker=dict(size=8),
            hovertemplate="%{x}: <b>%{y:+.2f}</b> xRAPM<extra></extra>",
        ))

    if best_rapm_idx is not None and best_rapm_idx in df_rapm.index:
        best = df_rapm.loc[best_rapm_idx]
        fig_rapm.add_annotation(
            x=best["season"], y=float(best["rapm"]),
            text=f"Career best<br>{float(best['rapm']):+.2f}",
            showarrow=True, arrowhead=2, arrowcolor="#E8462A",
            font=dict(size=10, color="#E8462A"), ax=0, ay=-38,
        )

    fig_rapm.add_hline(y=0, line_dash="dot", line_color="rgba(200,200,200,0.4)",
                       annotation_text="League avg", annotation_position="right",
                       annotation_font_color="rgba(180,180,180,0.7)")
    fig_rapm.update_layout(
        xaxis_title="Season",
        yaxis_title="Points per 100 Possessions (vs avg)",
        height=370, legend=dict(orientation="h", y=1.08), hovermode="x unified",
    )
    st.plotly_chart(fig_rapm, use_container_width=True)

    if not df_pooled.empty:
        with st.expander("📊 Multi-year pooled RAPM+Prior (v2) — more stable long-run view"):
            st.caption(
                "Each point = a 3-season rolling window ending at that season. "
                "RAPM+Prior shrinks toward each player's historical plus/minus baseline."
            )
            fig_pool = go.Figure()
            fig_pool.add_trace(go.Scatter(
                x=df_pooled["window_label"], y=df_pooled["rapm_prior"],
                mode="lines+markers", name="RAPM+Prior",
                line=dict(color="#F4D03F", width=2.5), marker=dict(size=9),
                hovertemplate="%{x}: <b>%{y:+.2f}</b><extra></extra>",
            ))
            fig_pool.add_trace(go.Scatter(
                x=df_pooled["window_label"], y=df_pooled["rapm"],
                mode="lines+markers", name="RAPM (raw pooled)",
                line=dict(color="#AAB7B8", width=1.5, dash="dot"), marker=dict(size=6),
                hovertemplate="%{x}: <b>%{y:+.2f}</b> raw<extra></extra>",
            ))
            fig_pool.add_hline(y=0, line_dash="dot", line_color="rgba(200,200,200,0.4)")
            fig_pool.update_layout(
                xaxis_title="3-yr Window (end season)",
                yaxis_title="Pts / 100 Poss",
                height=310, legend=dict(orientation="h", y=1.08), hovermode="x unified",
            )
            st.plotly_chart(fig_pool, use_container_width=True)
else:
    st.info(
        f"**{player_name}** does not have ≥1,000 stint possessions in any season "
        f"of {season_type} data."
    )

# ── Shot quality trend ────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Shot Quality — Season Trend")
st.caption(
    "**Bars:** FG% vs Expected (green = above expectation, red = below). "
    "**Line (right axis):** average difficulty of shots attempted. "
    "A player can be below avg difficulty but still be a great shot-maker "
    "(smart shot selection), or above avg difficulty and underperform (poor efficiency)."
)

df_shot = df[df["mean_xshot"].notna()]
if not df_shot.empty:
    fig_shot = go.Figure()
    fig_shot.add_trace(go.Bar(
        x=df_shot["season"],
        y=df_shot["fg_pct_above_expected"],
        name="FG% vs Expected",
        marker_color=["#2ECC71" if v >= 0 else "#E74C3C"
                      for v in df_shot["fg_pct_above_expected"]],
        hovertemplate="%{x}: <b>%{y:+.3f}</b> FG% vs expected<extra></extra>",
    ))
    fig_shot.add_trace(go.Scatter(
        x=df_shot["season"], y=df_shot["mean_xshot"],
        name="Avg Shot Difficulty",
        mode="lines+markers",
        line=dict(color="#F4D03F", width=2),
        yaxis="y2",
        hovertemplate="%{x}: <b>%{y:.3f}</b> avg xShot<extra></extra>",
    ))
    fig_shot.add_hline(y=0, line_dash="dot", line_color="rgba(200,200,200,0.4)")
    fig_shot.update_layout(
        yaxis=dict(title="FG% vs Expected  (Actual − Predicted)"),
        yaxis2=dict(title="Avg Shot Difficulty (xShot)",
                    overlaying="y", side="right", showgrid=False),
        height=370,
        legend=dict(orientation="h", y=1.08),
        hovermode="x unified",
    )
    st.plotly_chart(fig_shot, use_container_width=True)

# ── Career stats table ─────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Career Stats by Season")
st.caption(
    "Per-game counting stats. RAPM/xRAPM blank = below 1,000 possession threshold. "
    "Season +/- is the raw cumulative total for the season (not per-game)."
)

table_df = df.sort_values("season", ascending=False).reset_index(drop=True)
st.dataframe(
    table_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "person_id":              None,
        "season":                 st.column_config.TextColumn("Season", width="small"),
        "team":                   st.column_config.TextColumn("Team", width="small"),
        "gp":                     st.column_config.NumberColumn("GP", format="%d", width="small"),
        "ppg":                    st.column_config.NumberColumn("PPG", format="%.1f", width="small"),
        "rpg":                    st.column_config.NumberColumn("RPG", format="%.1f", width="small"),
        "apg":                    st.column_config.NumberColumn("APG", format="%.1f", width="small"),
        "spg":                    st.column_config.NumberColumn("SPG", format="%.1f", width="small"),
        "bpg":                    st.column_config.NumberColumn("BPG", format="%.1f", width="small"),
        "mpg":                    st.column_config.NumberColumn("MPG", format="%.1f", width="small"),
        "season_plus_minus":      st.column_config.NumberColumn(
                                      "+/- (Season Total)", format="%.0f", width="small",
                                      help="Raw season plus-minus total (not per game)"),
        "rapm":                   st.column_config.NumberColumn(
                                      "RAPM", format="%.2f", width="small",
                                      help="Net actual pts/100 poss vs avg"),
        "xrapm":                  st.column_config.NumberColumn(
                                      "xRAPM", format="%.2f", width="small",
                                      help="Net expected pts/100 poss vs avg"),
        "rapm_vs_xrapm":          st.column_config.NumberColumn(
                                      "RAPM−xRAPM", format="%.2f", width="small"),
        "possessions":            st.column_config.NumberColumn(
                                      "Stint Poss", format="%.0f", width="small",
                                      help="Total lineup stint possessions"),
        "shots_attempted":        st.column_config.NumberColumn(
                                      "FGA", format="%d", width="small"),
        "actual_fg_pct":          st.column_config.NumberColumn(
                                      "FG%", format="%.3f", width="small"),
        "mean_xshot":             st.column_config.NumberColumn(
                                      "Avg xShot", format="%.3f", width="small"),
        "fg_pct_above_expected":  st.column_config.NumberColumn(
                                      "FG% vs Exp", format="+.3f", width="small",
                                      help="Shot-making above expectation"),
        "shot_pts_above_expected": st.column_config.NumberColumn(
                                      "Pts Above Exp", format="%.0f", width="small"),
    },
    column_order=[
        "season", "team", "gp", "ppg", "rpg", "apg", "spg", "bpg", "mpg",
        "season_plus_minus", "rapm", "xrapm", "rapm_vs_xrapm", "possessions",
        "shots_attempted", "actual_fg_pct", "mean_xshot",
        "fg_pct_above_expected", "shot_pts_above_expected",
    ],
)
