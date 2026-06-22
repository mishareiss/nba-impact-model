"""
Player Profile — shot charts, percentile profile, season trends,
shot quality landscape, and synthesized analyst interpretation.
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
    inject_global_css, page_header, section_label, art_section,
    metric_card, metric_row, finding, chart_caption, interpretation_card,
    ACCENT, ACCENT_BLUE, ACCENT_GREEN, ACCENT_GOLD, ACCENT_PURPLE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    SURFACE, BORDER, GRID, ZERO_LINE, MODEBAR, TIER_LEGEND,
)

st.set_page_config(
    page_title="Player Profile · NBA Impact Dashboard",
    page_icon="",
    layout="wide",
)
inject_global_css()


def _pct(col: str, val, dist: pd.DataFrame) -> str:
    if pd.isna(val) or dist.empty or col not in dist.columns:
        return ""
    clean = dist[col].dropna()
    return (
        f"{percentileofscore(clean, float(val), kind='rank'):.0f}th"
        if len(clean) >= 5 else ""
    )


def _fmt(v, spec: str) -> str:
    return f"{float(v):{spec}}" if pd.notna(v) else "—"


def _generate_interpretation(latest: pd.Series, dist: pd.DataFrame) -> str:
    """Generate analyst interpretation text from player metrics."""
    name = latest.get("full_name", "This player")
    rapm  = latest.get("rapm")
    xrapm = latest.get("xrapm")
    o_rapm = latest.get("o_rapm")
    d_rapm = latest.get("d_rapm")
    gap   = latest.get("rapm_vs_xrapm")
    fga_v = latest.get("fg_pct_above_expected")
    mean_x = latest.get("mean_xshot")

    def pct_v(col, val):
        if pd.isna(val) or dist.empty or col not in dist.columns:
            return 50.0
        clean = dist[col].dropna()
        return percentileofscore(clean, float(val), kind="rank") if len(clean) >= 5 else 50.0

    lines = []

    # Overall impact
    if xrapm is not None and not pd.isna(xrapm):
        pct = pct_v("xrapm", xrapm)
        xv  = float(xrapm)
        if pct >= 85:
            lines.append(
                f"{name} ranks in the <strong>{pct:.0f}th percentile</strong> for xRAPM (+{xv:.2f}), "
                f"placing them among the elite impact players in the league this season."
            )
        elif pct >= 60:
            lines.append(
                f"{name} posts an above-average xRAPM of {xv:+.2f} ({pct:.0f}th percentile), "
                f"indicating solid positive impact on team process."
            )
        elif pct >= 40:
            lines.append(
                f"{name} registers a near-average xRAPM of {xv:+.2f} ({pct:.0f}th percentile)."
            )
        else:
            lines.append(
                f"{name} posts a below-average xRAPM of {xv:+.2f} ({pct:.0f}th percentile), "
                f"suggesting a negative impact on team process this season."
            )

    # Offensive vs defensive
    o_clause, d_clause = "", ""
    if o_rapm is not None and not pd.isna(o_rapm):
        ov = float(o_rapm)
        o_pct = pct_v("o_rapm", o_rapm)
        if o_pct >= 75:
            o_clause = f"an elite offensive presence (+{ov:.2f} O-RAPM, {o_pct:.0f}th percentile)"
        elif o_pct >= 50:
            o_clause = f"a positive offensive contributor (+{ov:.2f} O-RAPM)"
        else:
            o_clause = f"a below-average offensive impact ({ov:+.2f} O-RAPM)"
    if d_rapm is not None and not pd.isna(d_rapm):
        dv = float(d_rapm)
        d_pct = pct_v("d_rapm", d_rapm)
        if d_pct >= 75:
            d_clause = f"above-average defensive impact (+{dv:.2f} D-RAPM, {d_pct:.0f}th percentile)"
        elif d_pct >= 40:
            d_clause = f"neutral defensive presence ({dv:+.2f} D-RAPM)"
        else:
            d_clause = f"below-average defense ({dv:+.2f} D-RAPM)"
    if o_clause and d_clause:
        lines.append(f"The model attributes {o_clause} and {d_clause}.")
    elif o_clause:
        lines.append(f"Offensively: {o_clause}.")

    # RAPM vs xRAPM gap
    if gap is not None and not pd.isna(gap) and rapm is not None and not pd.isna(rapm):
        gv = float(gap)
        rv = float(rapm)
        if gv > 0.8:
            lines.append(
                f"RAPM ({rv:+.2f}) significantly exceeds xRAPM — a +{gv:.2f} process gap suggests "
                f"above-expectation shot conversion or positive variance. Some regression is possible."
            )
        elif gv < -0.8:
            lines.append(
                f"xRAPM exceeds RAPM by {abs(gv):.2f} — the process is better than outcomes suggest. "
                f"This player may be a positive regression candidate."
            )
        else:
            lines.append(
                f"RAPM and xRAPM are in close agreement (gap: {gv:+.2f}), indicating consistent outcomes."
            )

    # Shot quality
    if fga_v is not None and not pd.isna(fga_v) and mean_x is not None and not pd.isna(mean_x):
        fv = float(fga_v)
        mx = float(mean_x)
        x_med = 0.47  # rough league median xShot
        if fv > 0.02 and mx > x_med:
            lines.append(
                f"Shot quality profile: takes <strong>above-median difficulty shots</strong> (avg xShot {mx:.3f}) "
                f"and converts {abs(fv)*100:.1f}% above model expectation — an elite shooting profile."
            )
        elif fv > 0.02:
            lines.append(
                f"Shot quality: takes efficient looks (avg xShot {mx:.3f}) "
                f"and converts {abs(fv)*100:.1f}% above expectation — smart selection with strong finishing."
            )
        elif fv < -0.02:
            lines.append(
                f"Shot quality: converting {abs(fv)*100:.1f}% <em>below</em> model expectation "
                f"(avg xShot {mx:.3f}) — finishing or shot selection may be a concern."
            )
        else:
            lines.append(
                f"Shot quality: converting approximately at model expectation (avg xShot {mx:.3f})."
            )

    return " ".join(lines) if lines else "Insufficient data for full interpretation."


# ── Player / season selection ─────────────────────────────────────────────────
st.markdown(
    page_header("Player Profile", "Select a player to explore their shot quality, impact ratings, and trends."),
    unsafe_allow_html=True,
)
st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

all_names    = get_player_names()
default_name = "Nikola Jokić" if "Nikola Jokić" in all_names else (all_names[0] if all_names else "")

sel1, sel2 = st.columns([3, 1])
player_name = sel1.selectbox(
    "Search player", all_names,
    index=all_names.index(default_name) if default_name in all_names else 0,
)
season_type = sel2.selectbox("Season Type", get_season_types())

df        = get_player_career(player_name, season_type)
df_pooled = get_player_pooled(player_name)
if not df_pooled.empty:
    df_pooled = df_pooled[df_pooled["season_type"] == season_type]

if df.empty:
    st.markdown(
        f'<div style="text-align:center;padding:48px;color:{TEXT_MUTED}">'
        f'No data found for <strong>{player_name}</strong> ({season_type}).</div>',
        unsafe_allow_html=True,
    )
    st.stop()

latest        = df.iloc[-1]
latest_season = str(latest["season"])
person_id     = int(latest["person_id"])
team          = str(latest["team"])
tcolor        = team_color(team)
dist          = get_league_distribution(latest_season, season_type, min_poss=500)

# ── HEADER ────────────────────────────────────────────────────────────────────
hdr_img, hdr_info = st.columns([1, 8])
with hdr_img:
    try:
        st.image(player_headshot_url(person_id), width=120)
    except Exception:
        st.markdown(
            f'<div style="width:80px;height:80px;background:{SURFACE};'
            f'border:1px solid {BORDER};border-radius:50%;display:flex;'
            f'align-items:center;justify-content:center;font-size:2rem">👤</div>',
            unsafe_allow_html=True,
        )

with hdr_info:
    traded_label = "  (traded)" if "TM" in team else ""
    position_label = ""
    if "position" in latest and latest["position"] and str(latest["position"]) not in ("nan", "None", ""):
        position_label = f' · {latest["position"]}'

    st.markdown(
        f'<h2 style="margin-bottom:2px;margin-top:4px;font-size:1.7rem;color:{TEXT_PRIMARY}">'
        f'{player_name}</h2>'
        f'<div style="font-size:1.0rem;font-weight:700;color:{tcolor}">'
        f'{team}{traded_label}</div>'
        f'<div style="color:{TEXT_SECONDARY};font-size:0.82rem;margin-top:2px">'
        f'{latest_season} · {season_type}{position_label}</div>',
        unsafe_allow_html=True,
    )

    rapm_v  = _fmt(latest.get("rapm"),             "+.2f")
    xrapm_v = _fmt(latest.get("xrapm"),            "+.2f")
    gap_v   = _fmt(latest.get("rapm_vs_xrapm"),    "+.2f")
    orapm_v = _fmt(latest.get("o_rapm"),           "+.2f")
    drapm_v = _fmt(latest.get("d_rapm"),           "+.2f")
    fga_v   = _fmt(latest.get("fg_pct_above_expected"), "+.3f")
    pts_v   = _fmt(latest.get("shot_pts_above_expected"), "+.0f")

    pct_xrapm = _pct("xrapm", latest.get("xrapm"), dist)
    pct_rapm  = _pct("rapm",  latest.get("rapm"),  dist)
    pct_orapm = _pct("o_rapm", latest.get("o_rapm"), dist)
    pct_drapm = _pct("d_rapm", latest.get("d_rapm"), dist)
    pct_fga   = _pct("fg_pct_above_expected", latest.get("fg_pct_above_expected"), dist)

    st.markdown(
        metric_row(
            metric_card("xRAPM",            xrapm_v, pct_xrapm,  ACCENT),
            metric_card("O-RAPM",           orapm_v, pct_orapm,  ACCENT_BLUE),
            metric_card("D-RAPM",           drapm_v, pct_drapm,  ACCENT_PURPLE),
            metric_card("FG% vs Expected",  fga_v,   pct_fga,    ACCENT_GREEN),
            metric_card("RAPM − xRAPM",     gap_v,   "process gap", ACCENT_GOLD),
            metric_card("Pts Above Exp",    pts_v,   "season total", "#71717A"),
        ),
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    # Traditional stats row
    ppg_v = _fmt(latest.get("ppg"), ".1f")
    rpg_v = _fmt(latest.get("rpg"), ".1f")
    apg_v = _fmt(latest.get("apg"), ".1f")
    spg_v = _fmt(latest.get("spg"), ".1f")
    bpg_v = _fmt(latest.get("bpg"), ".1f")
    mpg_v = _fmt(latest.get("mpg"), ".1f")
    rapm_v2 = _fmt(latest.get("rapm"), "+.2f")

    st.markdown(
        metric_row(
            metric_card("PPG",  ppg_v,  _pct("ppg", latest.get("ppg"), dist),  "rgba(255,255,255,0.25)"),
            metric_card("RPG",  rpg_v,  _pct("rpg", latest.get("rpg"), dist),  "rgba(255,255,255,0.18)"),
            metric_card("APG",  apg_v,  _pct("apg", latest.get("apg"), dist),  "rgba(255,255,255,0.18)"),
            metric_card("SPG",  spg_v,  _pct("spg", latest.get("spg"), dist),  "rgba(255,255,255,0.14)"),
            metric_card("BPG",  bpg_v,  _pct("bpg", latest.get("bpg"), dist),  "rgba(255,255,255,0.14)"),
            metric_card("MPG",  mpg_v,  "",                                     "rgba(255,255,255,0.10)"),
            metric_card("RAPM", rapm_v2, pct_rapm,                              "rgba(255,255,255,0.10)"),
        ),
        unsafe_allow_html=True,
    )

st.markdown("<hr style='border-color:#27272A;margin:20px 0'>", unsafe_allow_html=True)

# ── PERCENTILE PROFILE ────────────────────────────────────────────────────────
st.markdown(art_section("", "Percentile Profile"), unsafe_allow_html=True)
st.caption(
    f"Where {player_name} ranks vs all players with ≥500 possessions — "
    f"{latest_season} {season_type}."
)
st.markdown(TIER_LEGEND, unsafe_allow_html=True)
st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

METRIC_SECTIONS = [
    ("OVERALL IMPACT", [
        ("xrapm",         "xRAPM — Process Impact",        "+.2f", True),
        ("rapm",          "RAPM — Net Actual Impact",       "+.2f", True),
        ("rapm_vs_xrapm", "RAPM − xRAPM  (Process Gap)",   "+.2f", True),
        ("o_rapm",        "O-RAPM — Offensive Impact",      "+.2f", True),
        ("d_rapm",        "D-RAPM — Defensive Impact",      "+.2f", True),
    ]),
    ("SHOT QUALITY", [
        ("ppg",                     "Points Per Game",             ".1f",  True),
        ("fg_pct_above_expected",   "FG% vs Expected (SMOE)",      "+.3f", True),
        ("shot_pts_above_expected", "Points Above Expected",        "+.0f", True),
        ("mean_xshot",              "Avg Shot Difficulty (xShot)",  ".3f",  True),
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

# ── ANALYST INTERPRETATION ────────────────────────────────────────────────────
st.markdown("<hr style='border-color:#27272A;margin:20px 0'>", unsafe_allow_html=True)
st.markdown(art_section("", "Analyst Interpretation"), unsafe_allow_html=True)

interp = _generate_interpretation(latest, dist)
st.markdown(interpretation_card(interp, ACCENT), unsafe_allow_html=True)

st.markdown(
    f'<p style="font-size:0.72rem;color:{TEXT_MUTED};margin-top:6px">'
    f'Interpretation generated from model outputs. Not a scouting report. '
    f'Do not act on this text without additional context.</p>',
    unsafe_allow_html=True,
)

# ── SHOT PROFILE ──────────────────────────────────────────────────────────────
st.markdown("<hr style='border-color:#27272A;margin:20px 0'>", unsafe_allow_html=True)
st.markdown(art_section("", "Shot Profile"), unsafe_allow_html=True)
st.caption(
    "Where and how does this player shoot? Switch to hexbin mode to see shot difficulty, "
    "FG%, or FG% vs model expectation by court zone."
)

sc_seasons = df["season"].sort_values(ascending=False).unique().tolist()
sc1, sc2, sc3, sc4 = st.columns([2, 2, 2, 2])
sc_season  = sc1.selectbox("Season", sc_seasons, key="sc_season")
sc_type    = sc2.selectbox("Season Type", get_season_types(), key="sc_stype")
chart_mode = sc3.radio("Style", ["Scatter", "Hexbin"], horizontal=True, key="sc_mode")

hex_mode = "volume"
if chart_mode == "Hexbin":
    mode_opts = {
        "Volume":          "volume",
        "Shot Difficulty": "xshot",
        "Actual FG%":      "fg_pct",
        "FG% vs Expected": "fg_vs_expected",
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
            fig_sc = shot_scatter_fig(
                df_shots, player_name=player_name, season=sc_season,
                season_type=sc_type, team_color=tcolor,
                show_zone_overlay=True, df_zones=df_zones,
            )
        else:
            fig_sc = shot_hexbin_fig(
                df_shots, mode=hex_mode, player_name=player_name,
                season=sc_season, season_type=sc_type, team_color=tcolor,
            )
        st.plotly_chart(fig_sc, use_container_width=True, config=MODEBAR, key="pp_court")
        if chart_mode == "Scatter":
            st.markdown(
                chart_caption("Green = made, red = missed. Circle size = model surprise (|made − xshot|)."),
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                chart_caption("Darker hexbin tiles = more extreme value for the selected metric."),
                unsafe_allow_html=True,
            )
    with ch2:
        st.markdown(f"**Zone Efficiency**")
        st.caption("Bar = actual FG%. Tick = xShot baseline. Green = above expected.")
        fig_ze = zone_efficiency_chart(df_zones, league_zones=df_lg, player_name=player_name)
        st.plotly_chart(fig_ze, use_container_width=True, config=MODEBAR, key="pp_ze")

        st.markdown("**Shot Distribution by Zone**")
        st.caption("Share of FGA from each zone — shot selection profile.")
        fig_zf = zone_frequency_chart(df_zones, player_name=player_name, color=tcolor)
        st.plotly_chart(fig_zf, use_container_width=True, config=MODEBAR, key="pp_zf")

# ── SEASON TRENDS ─────────────────────────────────────────────────────────────
st.markdown("<hr style='border-color:#27272A;margin:20px 0'>", unsafe_allow_html=True)
st.markdown(art_section("", "Season Trends"), unsafe_allow_html=True)

trend_c1, trend_c2 = st.columns(2)

with trend_c1:
    st.markdown("**RAPM vs xRAPM by Season**")
    st.caption(
        "Solid = RAPM (actual). Dashed = xRAPM (process). "
        "When RAPM > xRAPM, outcomes exceeded process — possible variance."
    )
    fig_rapm = impact_trend_chart(df, player_name=player_name, show_od=False)
    if fig_rapm:
        st.plotly_chart(fig_rapm, use_container_width=True, config=MODEBAR, key="pp_rapm")
    else:
        st.info("Fewer than 2 qualifying seasons for trend chart.")

with trend_c2:
    st.markdown("**Shot Quality Trend**")
    st.caption("Bars = FG% above/below expectation. Line = avg shot difficulty.")
    fig_sqt = shot_quality_trend(df)
    if fig_sqt:
        st.plotly_chart(fig_sqt, use_container_width=True, config=MODEBAR, key="pp_sqt")
    else:
        st.info("No shot quality data available.")

if not df_pooled.empty:
    with st.expander("Multi-year pooled RAPM+Prior (v2)", expanded=False):
        st.caption(
            "Each point = a 3-season rolling window. "
            "RAPM+Prior shrinks toward each player's historical per-minute baseline."
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
            line=dict(color="#6B7280", width=1.5, dash="dot"), marker=dict(size=6),
            hovertemplate="%{x}: <b>%{y:+.2f}</b> raw<extra></extra>",
        ))
        fig_pool.add_hline(y=0, line_dash="dot", line_color=ZERO_LINE)
        fig_pool.update_layout(
            height=260, xaxis_title="3-yr window (end season)", yaxis_title="pts / 100 poss",
            legend=dict(orientation="h", y=1.08, font=dict(size=11)),
            hovermode="x unified",
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=20, r=20, t=30, b=20),
            font=dict(color=TEXT_SECONDARY, size=11),
        )
        st.plotly_chart(fig_pool, use_container_width=True, config=MODEBAR, key="pp_pool")

# ── SHOT QUALITY LANDSCAPE ────────────────────────────────────────────────────
st.markdown("<hr style='border-color:#27272A;margin:20px 0'>", unsafe_allow_html=True)
st.markdown(art_section("", "Shot Quality Landscape"), unsafe_allow_html=True)

pvr_left, pvr_right = st.columns([3, 2])

with pvr_right:
    pv_x = float(latest.get("mean_xshot") or 0)
    pv_y = float(latest.get("fg_pct_above_expected") or 0)

    st.markdown("#### How to read this")
    st.markdown(
        "**X-axis — Shot Difficulty:** how hard are the shots this player takes? "
        "Higher = harder (driven by shot location and type).\n\n"
        "**Y-axis — FG% Above Expected:** how well does the player convert vs model prediction? "
        "Positive = better than expected.\n\n"
        "Grey dots = all qualifying players. Coloured dot = this player."
    )
    if pv_x and pv_y:
        pvr_df_pre = get_process_vs_results(latest_season, season_type, min_poss=200)
        if not pvr_df_pre.empty:
            x_med = float(pvr_df_pre["mean_xshot"].median())
            hard  = pv_x > x_med
            good  = pv_y > 0
            if hard and good:
                msg = "Takes <strong>difficult shots</strong> and converts <strong>above expectation</strong> — highest-value shooting profile."
                v = "green"
            elif not hard and good:
                msg = "Takes <strong>efficient looks</strong> and converts them well — smart selection, strong finishing."
                v = "green"
            elif hard and not good:
                msg = "Takes <strong>difficult shots</strong> but converts <strong>below expectation</strong> — shot selection may be costing the team."
                v = ""
            else:
                msg = "Takes <strong>easier looks</strong> but converts <strong>below expectation</strong> — finishing is a concern."
                v = ""
            st.markdown(finding(msg, variant=v), unsafe_allow_html=True)

with pvr_left:
    pvr_df = get_process_vs_results(latest_season, season_type, min_poss=200)
    fig_pvr = process_vs_results_fig(
        pvr_df, highlight_row=latest, highlight_label=player_name,
        color=tcolor if tcolor != "#607D8B" else ACCENT,
    )
    st.plotly_chart(fig_pvr, use_container_width=True, config=MODEBAR, key="pp_pvr")
    st.markdown(
        chart_caption(
            "Each dot = one qualifying player. "
            "Top-right = hardest shots + best conversion (elite). "
            "Reference lines = median shot difficulty and zero FG% vs expected."
        ),
        unsafe_allow_html=True,
    )

# ── CAREER TABLE ──────────────────────────────────────────────────────────────
st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
with st.expander("Career stats by season", expanded=False):
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
            "gp":                     st.column_config.NumberColumn("GP",   format="%d",   width="small"),
            "ppg":                    st.column_config.NumberColumn("PPG",  format="%.1f", width="small"),
            "rpg":                    st.column_config.NumberColumn("RPG",  format="%.1f", width="small"),
            "apg":                    st.column_config.NumberColumn("APG",  format="%.1f", width="small"),
            "spg":                    st.column_config.NumberColumn("SPG",  format="%.1f", width="small"),
            "bpg":                    st.column_config.NumberColumn("BPG",  format="%.1f", width="small"),
            "mpg":                    st.column_config.NumberColumn("MPG",  format="%.1f", width="small"),
            "season_plus_minus":      st.column_config.NumberColumn("+/-",  format="%.0f", width="small"),
            "xrapm":                  st.column_config.NumberColumn("xRAPM",      format="%+.2f", width="small"),
            "rapm":                   st.column_config.NumberColumn("RAPM",       format="%+.2f", width="small"),
            "rapm_vs_xrapm":          st.column_config.NumberColumn("RAPM−xRAPM", format="%+.2f", width="small"),
            "o_rapm":                 st.column_config.NumberColumn("O-RAPM",     format="%+.2f", width="small"),
            "d_rapm":                 st.column_config.NumberColumn("D-RAPM",     format="%+.2f", width="small"),
            "possessions":            st.column_config.NumberColumn("Poss",       format="%.0f",  width="small"),
            "shots_attempted":        st.column_config.NumberColumn("FGA",        format="%d",    width="small"),
            "actual_fg_pct":          st.column_config.NumberColumn("FG%",        format="%.3f",  width="small"),
            "mean_xshot":             st.column_config.NumberColumn("Avg xShot",  format="%.3f",  width="small"),
            "fg_pct_above_expected":  st.column_config.NumberColumn("FG% vs Exp", format="%+.3f", width="small"),
            "shot_pts_above_expected":st.column_config.NumberColumn("Pts vs Exp", format="%.0f",  width="small"),
        },
        column_order=[
            "season", "team", "gp", "ppg", "rpg", "apg", "spg", "bpg", "mpg",
            "season_plus_minus", "xrapm", "rapm", "rapm_vs_xrapm", "o_rapm", "d_rapm",
            "possessions", "shots_attempted", "actual_fg_pct",
            "mean_xshot", "fg_pct_above_expected", "shot_pts_above_expected",
        ],
    )
