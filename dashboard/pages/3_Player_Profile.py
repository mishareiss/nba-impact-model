"""
Player Profile — linear scroll through shot chart, zone efficiency,
RAPM/xRAPM career trend, percentile profile, and process vs results.
No inner tabs — sections flow naturally top-to-bottom.
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from scipy.stats import percentileofscore

from dashboard.utils.db import get_season_types
from dashboard.utils.queries import (
    get_player_names, get_player_career, get_player_pooled, get_league_distribution,
)
from dashboard.utils.nba_static import player_headshot_url, team_color
from dashboard.utils.shot_queries import (
    get_player_shots, get_player_shot_zones, get_league_zone_averages,
)
from dashboard.utils.model_queries import get_process_vs_results
from dashboard.utils.viz import (
    percentile_bar_chart, zone_efficiency_chart, zone_frequency_chart,
    impact_trend_chart, shot_quality_trend, process_vs_results_fig, TIER_LEGEND,
)
from dashboard.utils.court import shot_scatter_fig, shot_hexbin_fig
from dashboard.utils.theme import (
    ACCENT, ACCENT_BLUE, ACCENT_GREEN, ACCENT_GOLD, MUTED, MUTED_LIGHT,
    GRID, ZERO_LINE, MODEBAR, ARTICLE_CSS,
    art_section, finding, chart_caption, metric_card, metric_row,
    interactive_well_open, interactive_well_close,
)

st.set_page_config(
    page_title="Player Profile · NBA xShot + RAPM",
    page_icon="👤",
    layout="wide",
)
st.markdown(ARTICLE_CSS, unsafe_allow_html=True)

# ── Player / season selection ───────────────────────────────────────────────
all_names    = get_player_names()
default_name = "Nikola Jokić" if "Nikola Jokić" in all_names else (all_names[0] if all_names else "")

sel1, sel2 = st.columns([3, 1])
player_name = sel1.selectbox("Search player", all_names,
    index=all_names.index(default_name) if default_name in all_names else 0)
season_type = sel2.selectbox("Season Type", get_season_types())

df        = get_player_career(player_name, season_type)
df_pooled = get_player_pooled(player_name)
if not df_pooled.empty:
    df_pooled = df_pooled[df_pooled["season_type"] == season_type]

if df.empty:
    st.warning(f"No data found for **{player_name}** ({season_type}).")
    st.stop()

latest        = df.iloc[-1]
latest_season = str(latest["season"])
person_id     = int(latest["person_id"])
team          = str(latest["team"])
tcolor        = team_color(team)

dist = get_league_distribution(latest_season, season_type, min_poss=500)

def _pct(col: str, val) -> str:
    if pd.isna(val) or dist.empty or col not in dist.columns:
        return ""
    clean = dist[col].dropna()
    return f"{percentileofscore(clean, float(val), kind='rank'):.0f}th" if len(clean) >= 5 else ""

def _fmt(v, spec: str) -> str:
    return f"{float(v):{spec}}" if pd.notna(v) else "—"

# ── HEADER ─────────────────────────────────────────────────────────────────
hdr_img, hdr_info = st.columns([1, 7])
with hdr_img:
    try:
        st.image(player_headshot_url(person_id), width=130)
    except Exception:
        st.markdown("👤", unsafe_allow_html=True)

with hdr_info:
    traded_label = "  (traded)" if "TM" in team else ""
    st.markdown(
        f"<h2 style='margin-bottom:2px;margin-top:4px'>{player_name}</h2>"
        f"<div style='font-size:1.05rem;font-weight:600;color:{tcolor}'>"
        f"{team}{traded_label}"
        f"</div>"
        f"<div style='color:{MUTED};font-size:0.85rem;margin-top:2px'>"
        f"{latest_season} · {season_type}"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Impact metrics row
    rapm_v  = _fmt(latest["rapm"],          "+.2f")
    xrapm_v = _fmt(latest["xrapm"],         "+.2f")
    gap_v   = _fmt(latest.get("rapm_vs_xrapm"), "+.2f")
    fga_v   = _fmt(latest["fg_pct_above_expected"], "+.3f")
    pts_v   = _fmt(latest["shot_pts_above_expected"], "+.0f")

    st.markdown(
        metric_row(
            metric_card("RAPM",              rapm_v,  _pct("rapm",  latest["rapm"]),  ACCENT),
            metric_card("xRAPM",             xrapm_v, _pct("xrapm", latest["xrapm"]), ACCENT_BLUE),
            metric_card("RAPM − xRAPM",      gap_v,   "Process gap",                  ACCENT_GOLD),
            metric_card("FG% vs Expected",   fga_v,   _pct("fg_pct_above_expected", latest["fg_pct_above_expected"]), ACCENT_GREEN),
            metric_card("Pts Above Expected",pts_v,   "season total",                 MUTED_LIGHT),
        ),
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    # Traditional row
    st.markdown(
        metric_row(
            metric_card("PPG", _fmt(latest["ppg"],  ".1f"), _pct("ppg", latest["ppg"]),  "rgba(255,255,255,0.4)"),
            metric_card("RPG", _fmt(latest["rpg"],  ".1f"), _pct("rpg", latest["rpg"]),  "rgba(255,255,255,0.3)"),
            metric_card("APG", _fmt(latest["apg"],  ".1f"), _pct("apg", latest["apg"]),  "rgba(255,255,255,0.3)"),
            metric_card("SPG", _fmt(latest["spg"],  ".1f"), _pct("spg", latest["spg"]),  "rgba(255,255,255,0.25)"),
            metric_card("BPG", _fmt(latest["bpg"],  ".1f"), _pct("bpg", latest["bpg"]),  "rgba(255,255,255,0.25)"),
            metric_card("MPG", _fmt(latest["mpg"],  ".1f"), "",                           "rgba(255,255,255,0.2)"),
        ),
        unsafe_allow_html=True,
    )

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1 — PERCENTILE PROFILE
# ═══════════════════════════════════════════════════════════════════════════

st.markdown(art_section("", "Percentile Profile"), unsafe_allow_html=True)
st.caption(
    f"Where {player_name} ranks vs all players with ≥500 possessions — "
    f"{latest_season} {season_type}. Bar width = percentile (0th = leftmost, 100th = rightmost)."
)
st.markdown(TIER_LEGEND, unsafe_allow_html=True)
st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

METRIC_SECTIONS = [
    ("OVERALL IMPACT", [
        ("rapm",          "RAPM — Net Impact",            "+.2f", True),
        ("xrapm",         "xRAPM — Process Impact",       "+.2f", True),
        ("rapm_vs_xrapm", "RAPM − xRAPM  (Process Gap)",  "+.2f", True),
    ]),
    ("SCORING & SHOT QUALITY", [
        ("ppg",                     "Points Per Game",               ".1f",  True),
        ("fg_pct_above_expected",   "FG% vs Expected",               "+.3f", True),
        ("shot_pts_above_expected", "Points Above Expected",          "+.0f", True),
        ("mean_xshot",              "Avg Shot Difficulty (xShot)",    ".3f",  True),
    ]),
    ("TRADITIONAL", [
        ("apg", "Assists Per Game",  ".1f", True),
        ("rpg", "Rebounds Per Game", ".1f", True),
        ("spg", "Steals Per Game",   ".1f", True),
        ("bpg", "Blocks Per Game",   ".1f", True),
        ("mpg", "Minutes Per Game",  ".1f", True),
    ]),
]

if not dist.empty:
    fig_pct = percentile_bar_chart(latest, dist, METRIC_SECTIONS)
    if fig_pct:
        st.plotly_chart(fig_pct, use_container_width=True, config=MODEBAR, key="pp_pct")
    else:
        st.info("Insufficient data for percentile profile this season.")
else:
    st.info("League distribution unavailable for this season.")

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2 — SHOT PROFILE
# ═══════════════════════════════════════════════════════════════════════════

st.markdown("<hr class='art-divider'>", unsafe_allow_html=True)
st.markdown(art_section("", "Shot Profile"), unsafe_allow_html=True)
st.caption(
    "Where and how does this player shoot? Explore by season. "
    "Switch to hexbin mode to see shot difficulty, FG%, or FG% vs model expectation by court zone."
)

# Controls in a tidy strip
sc_seasons = df["season"].sort_values(ascending=False).unique().tolist()
sc1, sc2, sc3, sc4 = st.columns([2, 2, 2, 2])
sc_season  = sc1.selectbox("Season", sc_seasons, key="sc_season")
sc_type    = sc2.selectbox("Season Type", get_season_types(), key="sc_stype")
chart_mode = sc3.radio("Style", ["Scatter", "Hexbin"], horizontal=True, key="sc_mode")

hex_mode = "volume"
if chart_mode == "Hexbin":
    mode_opts = {
        "Volume":         "volume",
        "Shot Difficulty":"xshot",
        "Actual FG%":     "fg_pct",
        "FG% vs Expected":"fg_vs_expected",
    }
    hex_mode_label = sc4.selectbox("Hexbin metric", list(mode_opts.keys()), key="sc_hexmode")
    hex_mode = mode_opts[hex_mode_label]

with st.spinner("Loading shots…"):
    df_shots = get_player_shots(person_id, sc_season, sc_type)
    df_zones = get_player_shot_zones(person_id, sc_season, sc_type)
    df_lg    = get_league_zone_averages(sc_season, sc_type)

if df_shots.empty:
    st.info(f"No shot data for {player_name} in {sc_season} {sc_type}.")
else:
    ch1, ch2 = st.columns([5, 3])
    with ch1:
        if chart_mode == "Scatter":
            fig_sc = shot_scatter_fig(df_shots, player_name=player_name, season=sc_season,
                                      season_type=sc_type, team_color=tcolor,
                                      show_zone_overlay=True, df_zones=df_zones)
        else:
            fig_sc = shot_hexbin_fig(df_shots, mode=hex_mode, player_name=player_name,
                                     season=sc_season, season_type=sc_type, team_color=tcolor)
        st.plotly_chart(fig_sc, use_container_width=True, config=MODEBAR, key="pp_court")
        if chart_mode == "Scatter":
            st.markdown(
                chart_caption("Green = made, red = missed. Circle size indicates model's surprise (xShot surprise = |made − xshot|)."),
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                chart_caption("Darker hexbin tiles = more extreme value for the selected metric in that court zone."),
                unsafe_allow_html=True,
            )

    with ch2:
        st.markdown("**Zone Efficiency**")
        st.caption("Bar = actual FG%. Tick = xShot baseline. Green = above expected.")
        fig_ze = zone_efficiency_chart(df_zones, league_zones=df_lg, player_name=player_name)
        st.plotly_chart(fig_ze, use_container_width=True, config=MODEBAR, key="pp_ze")

        st.markdown("**Shot Distribution by Zone**")
        st.caption("Donut shows share of FGA from each zone — shot selection profile.")
        fig_zf = zone_frequency_chart(df_zones, player_name=player_name, color=tcolor)
        st.plotly_chart(fig_zf, use_container_width=True, config=MODEBAR, key="pp_zf")

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3 — SEASON TRENDS
# ═══════════════════════════════════════════════════════════════════════════

st.markdown("<hr class='art-divider'>", unsafe_allow_html=True)
st.markdown(art_section("", "Season Trends"), unsafe_allow_html=True)

trend_c1, trend_c2 = st.columns(2)

with trend_c1:
    st.markdown("**RAPM vs xRAPM by Season**")
    st.caption(
        "Solid line = actual outcomes (RAPM). Dashed line = process quality (xRAPM). "
        "When RAPM > xRAPM, the player outscored their process — either great finishing or positive variance."
    )
    fig_rapm = impact_trend_chart(df, player_name=player_name, show_od=False)
    if fig_rapm:
        st.plotly_chart(fig_rapm, use_container_width=True, config=MODEBAR, key="pp_rapm")
    else:
        st.info("Fewer than 2 qualifying seasons for trend chart.")

with trend_c2:
    st.markdown("**Shot Quality Trend**")
    st.caption(
        "Bars = FG% above/below model expectation. Line = avg shot difficulty. "
        "A player improving their shot selection should see the line rise."
    )
    fig_sqt = shot_quality_trend(df)
    if fig_sqt:
        st.plotly_chart(fig_sqt, use_container_width=True, config=MODEBAR, key="pp_sqt")
    else:
        st.info("No shot quality data available.")

# Pooled model view
if not df_pooled.empty:
    with st.expander("📊 Multi-year pooled RAPM+Prior (v2)", expanded=False):
        st.caption(
            "Each point = a 3-season rolling window ending at that season. "
            "RAPM+Prior shrinks toward each player's historical per-minute plus/minus baseline, "
            "producing more stable long-run estimates."
        )
        fig_pool = go.Figure()
        fig_pool.add_trace(go.Scatter(
            x=df_pooled["window_label"], y=df_pooled["rapm_prior"],
            mode="lines+markers", name="RAPM+Prior",
            line=dict(color=ACCENT_GOLD, width=2.5), marker=dict(size=9),
            hovertemplate="%{x}: <b>%{y:+.2f}</b><extra></extra>",
        ))
        fig_pool.add_trace(go.Scatter(
            x=df_pooled["window_label"], y=df_pooled["rapm"],
            mode="lines+markers", name="RAPM (raw pooled)",
            line=dict(color=MUTED_LIGHT, width=1.5, dash="dot"), marker=dict(size=6),
            hovertemplate="%{x}: <b>%{y:+.2f}</b> raw<extra></extra>",
        ))
        fig_pool.add_hline(y=0, line_dash="dot", line_color=ZERO_LINE)
        fig_pool.update_layout(
            height=280, xaxis_title="3-yr window (end season)", yaxis_title="pts / 100 poss",
            legend=dict(orientation="h", y=1.08), hovermode="x unified",
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=20, r=20, t=30, b=20),
        )
        st.plotly_chart(fig_pool, use_container_width=True, config=MODEBAR, key="pp_pool")

# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4 — PROCESS VS RESULTS
# ═══════════════════════════════════════════════════════════════════════════

st.markdown("<hr class='art-divider'>", unsafe_allow_html=True)
st.markdown(art_section("", "Shot Quality Landscape"), unsafe_allow_html=True)

pvr_left, pvr_right = st.columns([3, 2])

with pvr_right:
    pv_x = float(latest.get("mean_xshot") or 0)
    pv_y = float(latest.get("fg_pct_above_expected") or 0)

    st.markdown("#### How to read this chart")
    st.markdown(
        "**X-axis — Shot Difficulty (mean xShot):** how hard are the shots this player attempts? "
        "Higher = harder. Driven by location and shot type selection.\n\n"
        "**Y-axis — FG% Above Expected:** how well does the player convert relative to "
        "what the model predicts for their specific shots? Positive = better than expected.\n\n"
        "The grey dots are all qualifying players this season. "
        "The coloured dot is the selected player."
    )

    if pv_x and pv_y:
        # Interpret the quadrant
        pvr_df_pre = get_process_vs_results(latest_season, season_type, min_poss=200)
        if not pvr_df_pre.empty:
            x_med = float(pvr_df_pre["mean_xshot"].median())
            hard  = pv_x > x_med
            good  = pv_y > 0
            if hard and good:
                msg = "Takes <b>difficult shots</b> and converts them <b>above expectation</b> — the highest-value shooting profile."
                v = "green"
            elif not hard and good:
                msg = "Takes <b>efficient looks</b> and converts them well — smart selection, strong finishing."
                v = "green"
            elif hard and not good:
                msg = "Takes <b>difficult shots</b> but converts <b>below expectation</b> — shot selection may be costing the team."
                v = ""
            else:
                msg = "Takes <b>easier looks</b> but converts <b>below expectation</b> — finishing is a concern."
                v = ""
            st.markdown(finding(msg, variant=v), unsafe_allow_html=True)

with pvr_left:
    pvr_df = get_process_vs_results(latest_season, season_type, min_poss=200)
    fig_pvr = process_vs_results_fig(
        pvr_df, highlight_row=latest, highlight_label=player_name,
        color=tcolor if tcolor != "#888" else ACCENT,
    )
    st.plotly_chart(fig_pvr, use_container_width=True, config=MODEBAR, key="pp_pvr")
    st.markdown(
        chart_caption(
            "Each dot = one qualifying player this season. "
            "Top-right = hardest shots + best conversion (elite). "
            "Reference lines = median shot difficulty and league-average FG% vs expected."
        ),
        unsafe_allow_html=True,
    )

# ═══════════════════════════════════════════════════════════════════════════
# CAREER TABLE (collapsed)
# ═══════════════════════════════════════════════════════════════════════════

st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
with st.expander("📋  Career stats by season", expanded=False):
    table_df = df.sort_values("season", ascending=False).reset_index(drop=True)
    st.dataframe(
        table_df,
        use_container_width=True,
        hide_index=True,
        height=380,
        column_config={
            "person_id":              None,
            "season":                 st.column_config.TextColumn("Season", width="small"),
            "team":                   st.column_config.TextColumn("Team", width="small"),
            "gp":                     st.column_config.NumberColumn("GP",  format="%d", width="small"),
            "ppg":                    st.column_config.NumberColumn("PPG", format="%.1f", width="small"),
            "rpg":                    st.column_config.NumberColumn("RPG", format="%.1f", width="small"),
            "apg":                    st.column_config.NumberColumn("APG", format="%.1f", width="small"),
            "spg":                    st.column_config.NumberColumn("SPG", format="%.1f", width="small"),
            "bpg":                    st.column_config.NumberColumn("BPG", format="%.1f", width="small"),
            "mpg":                    st.column_config.NumberColumn("MPG", format="%.1f", width="small"),
            "season_plus_minus":      st.column_config.NumberColumn("+/- (Total)", format="%.0f", width="small"),
            "rapm":                   st.column_config.NumberColumn("RAPM",      format="%.2f", width="small"),
            "xrapm":                  st.column_config.NumberColumn("xRAPM",     format="%.2f", width="small"),
            "rapm_vs_xrapm":          st.column_config.NumberColumn("RAPM−xRAPM",format="%.2f", width="small"),
            "possessions":            st.column_config.NumberColumn("Poss",      format="%.0f", width="small"),
            "shots_attempted":        st.column_config.NumberColumn("FGA",       format="%d",   width="small"),
            "actual_fg_pct":          st.column_config.NumberColumn("FG%",       format="%.3f", width="small"),
            "mean_xshot":             st.column_config.NumberColumn("Avg xShot", format="%.3f", width="small"),
            "fg_pct_above_expected":  st.column_config.NumberColumn("FG% vs Exp",format="+.3f", width="small"),
            "shot_pts_above_expected":st.column_config.NumberColumn("Pts vs Exp",format="%.0f", width="small"),
        },
        column_order=[
            "season", "team", "gp", "ppg", "rpg", "apg", "spg", "bpg", "mpg",
            "season_plus_minus", "rapm", "xrapm", "rapm_vs_xrapm", "possessions",
            "shots_attempted", "actual_fg_pct", "mean_xshot",
            "fg_pct_above_expected", "shot_pts_above_expected",
        ],
    )
