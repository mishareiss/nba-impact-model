"""
Player Profile page: season-over-season trends, percentile profile, and shot chart.
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
from dashboard.utils.viz import (
    percentile_bar_chart, zone_efficiency_chart, zone_frequency_chart,
    impact_trend_chart, shot_quality_trend, TIER_LEGEND
)
from dashboard.utils.shot_queries import get_player_shots, get_player_shot_zones, get_league_zone_averages
from dashboard.utils.archetypes import classify, stability_flags
from dashboard.utils.court import shot_scatter_fig

st.set_page_config(page_title="Player Profile · NBA Impact", page_icon="👤", layout="wide")
st.title("👤 Player Profile")


# ── Percentile chart config ────────────────────────────────────────────────────

METRIC_SECTIONS = [
    ("OVERALL IMPACT", [
        ("rapm",   "RAPM — Net Impact",             "+.2f", True),
        ("xrapm",  "xRAPM — Expected Shot Impact",  "+.2f", True),
        ("o_rapm", "O-RAPM — Offensive Impact",     "+.2f", True),
        ("d_rapm", "D-RAPM — Defensive Impact",     "+.2f", True),
    ]),
    ("SCORING", [
        ("ppg",                    "Points Per Game",              ".1f",  True),
        ("fg_pct_above_expected",  "FG% vs Expected (Shot-Making)", "+.3f", True),
        ("shot_pts_above_expected","Points Above Expected",         "+.0f", True),
        ("mean_xshot",             "Avg Shot Difficulty (xShot)",  ".3f",  True),
    ]),
    ("PLAYMAKING & REBOUNDING", [
        ("apg", "Assists Per Game",  ".1f", True),
        ("rpg", "Rebounds Per Game", ".1f", True),
        ("mpg", "Minutes Per Game",  ".1f", True),
    ]),
    ("DEFENSE (Traditional Proxies)", [
        ("spg", "Steals Per Game", ".1f", True),
        ("bpg", "Blocks Per Game", ".1f", True),
    ]),
]


def _html_metric_card(label: str, value: str, delta: str = "",
                       help_text: str = "") -> str:
    """Renders one metric card as HTML — never truncates regardless of label length."""
    delta_html = (
        f'<div style="color:#9FA8B3;font-size:0.68rem;margin-top:4px">{delta}</div>'
        if delta else ""
    )
    title_attr = f'title="{help_text}"' if help_text else ""
    return (
        f'<div {title_attr} style="background:rgba(255,255,255,0.05);border-radius:8px;'
        f'padding:10px 14px;flex:1;min-width:130px;text-align:center;cursor:default">'
        f'<div style="color:#9FA8B3;font-size:0.72rem;font-weight:600;'
        f'letter-spacing:0.03em;white-space:nowrap;overflow:visible">{label}</div>'
        f'<div style="font-size:1.4rem;font-weight:700;margin-top:5px">{value}</div>'
        f'{delta_html}</div>'
    )


def _render_metric_row(cards: list[tuple]) -> None:
    """Renders a flex row of metric cards with no truncation. cards = (label, value, delta, help)."""
    html = (
        '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">'
        + "".join(_html_metric_card(*c) for c in cards)
        + "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


# ── Selection ─────────────────────────────────────────────────────────────────
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

dist = get_league_distribution(latest_season, season_type, min_poss=500)


def _pct_label(col: str, val) -> str:
    """Returns '87th pct' or '' if data is unavailable."""
    if pd.isna(val) or dist.empty or col not in dist.columns:
        return ""
    clean = dist[col].dropna()
    if len(clean) < 5:
        return ""
    return f"{percentileofscore(clean, float(val), kind='rank'):.0f}th pct"


def _fmt(v, spec: str) -> str:
    return f"{float(v):{spec}}" if pd.notna(v) else "—"


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

    # Row 1: Impact ratings
    _render_metric_row([
        ("RAPM",
         _fmt(latest["rapm"],  "+.2f"),
         _pct_label("rapm", latest["rapm"]),
         "Net actual pts/100 poss vs league average"),
        ("xRAPM",
         _fmt(latest["xrapm"], "+.2f"),
         _pct_label("xrapm", latest["xrapm"]),
         "Net expected pts/100 poss based on shot quality"),
        ("O-RAPM",
         _fmt(latest.get("o_rapm"), "+.2f"),
         _pct_label("o_rapm", latest.get("o_rapm")),
         "Offensive pts/100 poss added above average (re-run model to populate)"),
        ("D-RAPM",
         _fmt(latest.get("d_rapm"), "+.2f"),
         _pct_label("d_rapm", latest.get("d_rapm")),
         "Defensive pts/100 poss saved above average (positive = better)"),
        ("FG% Above Expected",
         _fmt(latest["fg_pct_above_expected"], "+.3f"),
         _pct_label("fg_pct_above_expected", latest["fg_pct_above_expected"]),
         "Actual FG% minus model-predicted FG% — measures shot-making ability"),
        ("Pts Above Expected",
         _fmt(latest["shot_pts_above_expected"], "+.0f"),
         _pct_label("shot_pts_above_expected", latest["shot_pts_above_expected"]),
         "Total points scored above xShot expectation"),
    ])

    # Row 2: Traditional per-game stats
    _render_metric_row([
        ("PPG",  _fmt(latest["ppg"], ".1f"),  _pct_label("ppg",  latest["ppg"]),  "Points per game"),
        ("APG",  _fmt(latest["apg"], ".1f"),  _pct_label("apg",  latest["apg"]),  "Assists per game"),
        ("RPG",  _fmt(latest["rpg"], ".1f"),  _pct_label("rpg",  latest["rpg"]),  "Rebounds per game"),
        ("SPG",  _fmt(latest["spg"], ".1f"),  _pct_label("spg",  latest["spg"]),  "Steals per game"),
        ("BPG",  _fmt(latest["bpg"], ".1f"),  _pct_label("bpg",  latest["bpg"]),  "Blocks per game"),
        ("MPG",  _fmt(latest["mpg"], ".1f"),  "", "Minutes per game"),
        ("GP",   f"{int(latest['gp'])}" if pd.notna(latest["gp"]) else "—", "", "Games played"),
    ])

st.markdown("---")

# ── Page tabs ──────────────────────────────────────────────────────────────────
tab_profile, tab_trends, tab_shot = st.tabs(
    ["📊 Percentile Profile", "📈 Season Trends", "🏀 Shot Chart"]
)

# ── Tab 1: Percentile Profile ──────────────────────────────────────────────────
with tab_profile:
    # Archetype badge
    arch = classify(latest)
    flags = stability_flags(latest)
    badge_html = (
        f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">'
        f'<span style="background:{arch["color"]}22;border:1px solid {arch["color"]}55;'
        f'border-radius:6px;padding:4px 10px;font-size:0.9rem;font-weight:600;'
        f'color:{arch["color"]}">{arch["icon"]} {arch["label"]}</span>'
        f'<span style="color:#9FA8B3;font-size:0.8rem">{arch["description"]}</span>'
        + "".join(
            f'<span title="{f["help"]}" style="background:rgba(255,255,255,0.06);'
            f'border-radius:6px;padding:3px 8px;font-size:0.78rem;cursor:help">'
            f'{f["text"]}</span>'
            for f in flags
        )
        + "</div>"
    )
    st.markdown(badge_html, unsafe_allow_html=True)

    st.caption(
        f"Compared to all players with ≥500 stint possessions — {latest_season} {season_type}. "
        "Bar width = percentile rank."
    )
    if not dist.empty:
        fig_pct = percentile_bar_chart(latest, dist, METRIC_SECTIONS)
        if fig_pct is not None:
            st.plotly_chart(fig_pct, use_container_width=True)
        else:
            st.info("Insufficient data for percentile profile this season.")
    else:
        st.info("League distribution unavailable for this season.")


# ── Tab 2: Season Trends ───────────────────────────────────────────────────────
with tab_trends:
    st.subheader("Impact Rating — Season Trend")
    st.caption(
        "RAPM = actual outcomes. xRAPM = expected shot quality. "
        "Gap between them reflects shot-making variance — "
        "RAPM > xRAPM means outscoring process (elite finishing), "
        "xRAPM > RAPM = positive regression candidate."
    )

    fig_rapm = impact_trend_chart(df, player_name=player_name)
    if fig_rapm:
        st.plotly_chart(fig_rapm, use_container_width=True)
    else:
        st.info(
            f"**{player_name}** does not have ≥1,000 stint possessions in any "
            f"{season_type} season."
        )

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
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_pool, use_container_width=True)

    st.markdown("---")
    st.subheader("Shot Quality — Season Trend")
    st.caption(
        "**Bars:** FG% vs Expected (green = above, red = below). "
        "**Line:** average difficulty of shots attempted. "
    )
    fig_sqt = shot_quality_trend(df)
    if fig_sqt:
        st.plotly_chart(fig_sqt, use_container_width=True)


# ── Tab 3: Shot Chart ──────────────────────────────────────────────────────────
with tab_shot:
    st.caption(
        "Individual shot locations for the selected season. "
        "**Green circles** = makes (shade = how surprising). "
        "**Red × marks** = misses. "
        "Overlaid zones show FG% above/below expected."
    )

    sc_seasons = df["season"].sort_values(ascending=False).unique().tolist()
    sc_col1, sc_col2 = st.columns([2, 1])
    sc_season = sc_col1.selectbox(
        "Season", sc_seasons, key="sc_season",
        index=0,
    )
    sc_type = sc_col2.selectbox(
        "Season Type", get_season_types(), key="sc_type"
    )

    with st.spinner("Loading shots…"):
        df_shots_raw = get_player_shots(person_id, sc_season, sc_type)
        df_zones_sc = get_player_shot_zones(person_id, sc_season, sc_type)
        df_lg_zones = get_league_zone_averages(sc_season, sc_type)

    if df_shots_raw.empty:
        st.info(f"No shot data for {player_name} in {sc_season} {sc_type}.")
    else:
        ch1, ch2 = st.columns([3, 2])
        with ch1:
            fig_sc = shot_scatter_fig(
                df_shots_raw,
                player_name=player_name,
                season=sc_season,
                season_type=sc_type,
                team_color=team_color(team),
                show_zone_overlay=True,
                df_zones=df_zones_sc,
            )
            st.plotly_chart(fig_sc, use_container_width=True)

        with ch2:
            st.markdown("**Shot Zone Efficiency**")
            fig_zone_eff = zone_efficiency_chart(
                df_zones_sc,
                league_zones=df_lg_zones,
                player_name=player_name,
            )
            st.plotly_chart(fig_zone_eff, use_container_width=True)

            st.markdown("**Shot Distribution**")
            fig_zone_freq = zone_frequency_chart(df_zones_sc, player_name=player_name,
                                                 color=team_color(team))
            st.plotly_chart(fig_zone_freq, use_container_width=True)

# ── Career stats table ─────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Career Stats by Season")
st.caption(
    "Per-game counting stats. RAPM/xRAPM/O-RAPM/D-RAPM blank = below 1,000 possession threshold. "
    "Season +/- is the raw cumulative total (not per-game)."
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
        "o_rapm":                 st.column_config.NumberColumn(
                                      "O-RAPM", format="%.2f", width="small",
                                      help="Offensive pts/100 poss above average"),
        "d_rapm":                 st.column_config.NumberColumn(
                                      "D-RAPM", format="%.2f", width="small",
                                      help="Defensive pts/100 poss saved above average"),
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
        "season_plus_minus", "rapm", "xrapm", "o_rapm", "d_rapm",
        "rapm_vs_xrapm", "possessions",
        "shots_attempted", "actual_fg_pct", "mean_xshot",
        "fg_pct_above_expected", "shot_pts_above_expected",
    ],
)
