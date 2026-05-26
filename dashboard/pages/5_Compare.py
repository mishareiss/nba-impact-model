"""
Compare Players page.

Purpose: Support basketball decision-making by placing two players side by side
across all analytical dimensions — impact ratings, shot quality, shot charts,
and historical trends — in a unified view designed for roster evaluation,
lineup decisions, and scouting comparisons.

Design principles:
  - Every section answers a specific basketball question
  - Layout mirrors scouting reports: summary first, depth below
  - Archetype + stability flags surface the most actionable signals
  - Shot profile comparison is central, not an afterthought
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from dashboard.utils.db import get_season_types
from dashboard.utils.queries import (
    get_player_names, get_player_career, get_league_distribution
)
from dashboard.utils.nba_static import player_headshot_url, team_color
from dashboard.utils.viz import (
    percentile_bar_chart, zone_efficiency_chart, zone_frequency_chart,
    dual_trend_chart, TIER_LEGEND
)
from dashboard.utils.shot_queries import (
    get_player_shots, get_player_shot_zones, get_league_zone_averages, get_player_id
)
from dashboard.utils.archetypes import classify, stability_flags
from dashboard.utils.court import shot_scatter_fig

st.set_page_config(
    page_title="Compare Players · NBA Impact",
    page_icon="⚖️",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Shared style helpers
# ---------------------------------------------------------------------------

METRIC_SECTIONS = [
    ("OVERALL IMPACT", [
        ("rapm",   "RAPM",          "+.2f", True),
        ("xrapm",  "xRAPM",         "+.2f", True),
        ("o_rapm", "O-RAPM",        "+.2f", True),
        ("d_rapm", "D-RAPM",        "+.2f", True),
    ]),
    ("SCORING", [
        ("ppg",                    "PPG",              ".1f",  True),
        ("fg_pct_above_expected",  "FG% vs Expected",  "+.3f", True),
        ("shot_pts_above_expected","Pts Above Expected","+.0f", True),
        ("mean_xshot",             "Avg Shot Difficulty",".3f", True),
    ]),
    ("PLAYMAKING & REBOUNDING", [
        ("apg", "APG", ".1f", True),
        ("rpg", "RPG", ".1f", True),
        ("mpg", "MPG", ".1f", True),
    ]),
    ("DEFENSE", [
        ("spg", "SPG", ".1f", True),
        ("bpg", "BPG", ".1f", True),
    ]),
]

COMPARE_COLORS = ["#E8462A", "#4C9BE8"]  # Player A = red, B = blue


def _fmt(v, spec: str) -> str:
    return f"{float(v):{spec}}" if pd.notna(v) else "—"


def _card(label: str, val: str, delta: str = "", color: str = "#E8462A") -> str:
    delta_html = (
        f'<div style="color:#9FA8B3;font-size:0.65rem;margin-top:3px">{delta}</div>'
        if delta else ""
    )
    return (
        f'<div style="background:rgba(255,255,255,0.05);border-left:3px solid {color};'
        f'border-radius:6px;padding:8px 12px;flex:1;min-width:110px;text-align:center">'
        f'<div style="color:#9FA8B3;font-size:0.68rem;font-weight:600;'
        f'white-space:nowrap;overflow:visible">{label}</div>'
        f'<div style="font-size:1.35rem;font-weight:700;margin-top:4px">{val}</div>'
        f'{delta_html}</div>'
    )


def _metric_row(cards: list[tuple], color: str) -> None:
    html = (
        '<div style="display:flex;gap:6px;flex-wrap:wrap;margin:6px 0">'
        + "".join(_card(*c, color=color) for c in cards)
        + "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def _archetype_badge(arch: dict, flags: list[dict]) -> None:
    badge = (
        f'<div style="display:flex;align-items:center;gap:10px;margin:8px 0">'
        f'<span style="background:{arch["color"]}22;border:1px solid {arch["color"]}55;'
        f'border-radius:6px;padding:3px 9px;font-size:0.85rem;font-weight:700;'
        f'color:{arch["color"]}">{arch["icon"]} {arch["label"]}</span>'
        f'<span style="color:#9FA8B3;font-size:0.78rem">{arch["description"]}</span>'
        + "".join(
            f'<span title="{f["help"]}" style="cursor:help;background:rgba(255,255,255,0.06);'
            f'border-radius:5px;padding:2px 7px;font-size:0.72rem">{f["text"]}</span>'
            for f in flags
        )
        + "</div>"
    )
    st.markdown(badge, unsafe_allow_html=True)


def _player_header(row: pd.Series, pid: int, color: str) -> None:
    """Render player name, headshot, team, and key metric cards."""
    h_col, info_col = st.columns([1, 5])
    with h_col:
        try:
            st.image(player_headshot_url(pid), width=110)
        except Exception:
            st.markdown("👤")
    with info_col:
        name = row.get("full_name", "")
        team = str(row.get("team", ""))
        season = str(row.get("season", ""))
        tcolor = team_color(team)
        st.markdown(
            f"<h3 style='margin-bottom:2px;color:{color}'>{name}</h3>"
            f"<span style='color:{tcolor};font-weight:600'>{team}</span>"
            f"&nbsp;<span style='color:#888'>· {season}</span>",
            unsafe_allow_html=True,
        )
        _archetype_badge(classify(row), stability_flags(row))
        _metric_row([
            ("RAPM",   _fmt(row.get("rapm"),  "+.2f")),
            ("xRAPM",  _fmt(row.get("xrapm"), "+.2f")),
            ("O-RAPM", _fmt(row.get("o_rapm"), "+.2f")),
            ("D-RAPM", _fmt(row.get("d_rapm"), "+.2f")),
        ], color=color)
        _metric_row([
            ("PPG", _fmt(row.get("ppg"), ".1f")),
            ("APG", _fmt(row.get("apg"), ".1f")),
            ("RPG", _fmt(row.get("rpg"), ".1f")),
            ("SPG", _fmt(row.get("spg"), ".1f")),
            ("BPG", _fmt(row.get("bpg"), ".1f")),
            ("MPG", _fmt(row.get("mpg"), ".1f")),
        ], color=color)


# ---------------------------------------------------------------------------
# Page header + player selection
# ---------------------------------------------------------------------------

st.title("⚖️ Compare Players")
st.caption(
    "Side-by-side analytical comparison for roster evaluation, scouting, and lineup decisions. "
    "Select any two players across any season."
)

all_names = get_player_names()

defaults = ["Nikola Jokić", "LeBron James"]
def_a = defaults[0] if defaults[0] in all_names else all_names[0]
def_b = defaults[1] if defaults[1] in all_names else (all_names[1] if len(all_names) > 1 else all_names[0])

ctrl_c1, ctrl_c2, ctrl_c3, ctrl_c4 = st.columns([3, 3, 2, 2])
name_a = ctrl_c1.selectbox("Player A", all_names, index=all_names.index(def_a), key="cmp_a")
name_b = ctrl_c2.selectbox("Player B", all_names, index=all_names.index(def_b), key="cmp_b")
season_type = ctrl_c3.selectbox("Season Type", get_season_types(), key="cmp_stype")

# Determine available seasons from the intersection of both players
df_a_full = get_player_career(name_a, season_type)
df_b_full = get_player_career(name_b, season_type)

if df_a_full.empty or df_b_full.empty:
    st.warning("One or both players have no data for this season type. Try Regular Season.")
    st.stop()

seasons_a = set(df_a_full["season"].tolist())
seasons_b = set(df_b_full["season"].tolist())
shared_seasons = sorted(seasons_a & seasons_b, reverse=True)
all_seasons = sorted(seasons_a | seasons_b, reverse=True)

season_options = ["Latest (each player)"] + all_seasons
chosen_season = ctrl_c4.selectbox("Season", season_options, key="cmp_season")

# Resolve season for each player
if chosen_season == "Latest (each player)":
    row_a = df_a_full.iloc[-1]
    row_b = df_b_full.iloc[-1]
    sc_season_a = str(row_a["season"])
    sc_season_b = str(row_b["season"])
else:
    rows_a = df_a_full[df_a_full["season"] == chosen_season]
    rows_b = df_b_full[df_b_full["season"] == chosen_season]
    if rows_a.empty or rows_b.empty:
        missing = name_a if rows_a.empty else name_b
        st.warning(f"**{missing}** has no data in {chosen_season} {season_type}.")
        st.stop()
    row_a = rows_a.iloc[-1]
    row_b = rows_b.iloc[-1]
    sc_season_a = sc_season_b = chosen_season

pid_a = int(row_a["person_id"])
pid_b = int(row_b["person_id"])

dist = get_league_distribution(sc_season_a, season_type, min_poss=500)

st.markdown("---")

# ---------------------------------------------------------------------------
# Section 1: Player headers
# ---------------------------------------------------------------------------

col_a, col_sep, col_b = st.columns([5, 0.15, 5])
with col_a:
    _player_header(row_a, pid_a, COMPARE_COLORS[0])
with col_sep:
    st.markdown(
        "<div style='border-left:1px solid rgba(255,255,255,0.12);height:220px;margin:auto'></div>",
        unsafe_allow_html=True,
    )
with col_b:
    _player_header(row_b, pid_b, COMPARE_COLORS[1])

st.markdown("---")

# ---------------------------------------------------------------------------
# Section 2: Percentile comparison
# ---------------------------------------------------------------------------

st.subheader("📊 Percentile Comparison")
st.caption(
    f"Ranked against all players with ≥500 stint possessions — {sc_season_a} {season_type}. "
    "Bar width = percentile rank within the league."
)

pct_col_a, pct_col_b = st.columns(2)
with pct_col_a:
    st.markdown(
        f"<div style='color:{COMPARE_COLORS[0]};font-weight:700;font-size:1.05rem;'>"
        f"{name_a}</div>",
        unsafe_allow_html=True,
    )
    if not dist.empty:
        fig_pct_a = percentile_bar_chart(row_a, dist, METRIC_SECTIONS)
        if fig_pct_a:
            st.plotly_chart(fig_pct_a, use_container_width=True)
        else:
            st.info("Insufficient data for percentile profile.")

with pct_col_b:
    st.markdown(
        f"<div style='color:{COMPARE_COLORS[1]};font-weight:700;font-size:1.05rem;'>"
        f"{name_b}</div>",
        unsafe_allow_html=True,
    )
    if not dist.empty:
        fig_pct_b = percentile_bar_chart(row_b, dist, METRIC_SECTIONS)
        if fig_pct_b:
            st.plotly_chart(fig_pct_b, use_container_width=True)
        else:
            st.info("Insufficient data for percentile profile.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Section 3: Shot Profile Comparison
# ---------------------------------------------------------------------------

st.subheader("🎯 Shot Profile Comparison")
st.caption(
    "How each player generates their offense. "
    "**Bar** = actual FG%. **Gold tick** = xShot (expected FG%). **Diamond** = league average. "
    "Green bars = above expectation, red = below."
)

with st.spinner("Loading shot zone data…"):
    df_zones_a = get_player_shot_zones(pid_a, sc_season_a, season_type)
    df_zones_b = get_player_shot_zones(pid_b, sc_season_b, season_type)
    df_lg = get_league_zone_averages(sc_season_a, season_type)

zone_col_a, zone_col_b = st.columns(2)

with zone_col_a:
    st.markdown(
        f"<b style='color:{COMPARE_COLORS[0]}'>{name_a}</b> — {sc_season_a}",
        unsafe_allow_html=True,
    )
    if not df_zones_a.empty:
        fig_ze_a = zone_efficiency_chart(df_zones_a, league_zones=df_lg,
                                          player_name="", color=COMPARE_COLORS[0])
        st.plotly_chart(fig_ze_a, use_container_width=True)
        fig_zf_a = zone_frequency_chart(df_zones_a, color=COMPARE_COLORS[0])
        st.plotly_chart(fig_zf_a, use_container_width=True)
    else:
        st.info("No shot zone data available.")

with zone_col_b:
    st.markdown(
        f"<b style='color:{COMPARE_COLORS[1]}'>{name_b}</b> — {sc_season_b}",
        unsafe_allow_html=True,
    )
    if not df_zones_b.empty:
        fig_ze_b = zone_efficiency_chart(df_zones_b, league_zones=df_lg,
                                          player_name="", color=COMPARE_COLORS[1])
        st.plotly_chart(fig_ze_b, use_container_width=True)
        fig_zf_b = zone_frequency_chart(df_zones_b, color=COMPARE_COLORS[1])
        st.plotly_chart(fig_zf_b, use_container_width=True)
    else:
        st.info("No shot zone data available.")

# ── Zone stats delta table ─────────────────────────────────────────────────────
if not df_zones_a.empty and not df_zones_b.empty:
    with st.expander("📋 Zone-by-zone stats table (attempts, FG%, xShot, vs Expected)"):
        _lbl = {
            "at_rim": "At Rim", "short_mid": "Short Mid",
            "mid_range": "Mid-Range", "long_mid": "Long Mid", "three": "3-Point"
        }
        merged = pd.merge(
            df_zones_a[["shot_zone","attempts","fg_pct","mean_xshot","fg_pct_vs_expected"]],
            df_zones_b[["shot_zone","attempts","fg_pct","mean_xshot","fg_pct_vs_expected"]],
            on="shot_zone", how="outer", suffixes=("_a", "_b"),
        )
        merged["zone"] = merged["shot_zone"].map(_lbl).fillna(merged["shot_zone"])
        merged = merged.set_index("zone").drop(columns=["shot_zone"])

        # Friendly column names
        merged.columns = [
            f"FGA ({name_a})", f"FG% ({name_a})", f"xShot ({name_a})", f"vs Exp ({name_a})",
            f"FGA ({name_b})", f"FG% ({name_b})", f"xShot ({name_b})", f"vs Exp ({name_b})",
        ]
        st.dataframe(
            merged.style.format({
                c: "{:.3f}" for c in merged.columns if "FG%" in c or "xShot" in c or "vs Exp" in c
            }),
            use_container_width=True,
        )

st.markdown("---")

# ---------------------------------------------------------------------------
# Section 4: Shot Charts
# ---------------------------------------------------------------------------

st.subheader("🏀 Shot Charts")
st.caption(
    "Individual shot locations. Green circles = makes, red × = misses. "
    "Zone overlays show FG% above/below expected."
)

with st.spinner("Loading shot chart data…"):
    df_shots_a = get_player_shots(pid_a, sc_season_a, season_type)
    df_shots_b = get_player_shots(pid_b, sc_season_b, season_type)

sc_col_a, sc_col_b = st.columns(2)
with sc_col_a:
    if not df_shots_a.empty:
        fig_sc_a = shot_scatter_fig(
            df_shots_a,
            player_name=name_a, season=sc_season_a, season_type=season_type,
            team_color=team_color(str(row_a.get("team", ""))),
            show_zone_overlay=True, df_zones=df_zones_a,
        )
        st.plotly_chart(fig_sc_a, use_container_width=True)
    else:
        st.info(f"No shot chart data for {name_a}.")

with sc_col_b:
    if not df_shots_b.empty:
        fig_sc_b = shot_scatter_fig(
            df_shots_b,
            player_name=name_b, season=sc_season_b, season_type=season_type,
            team_color=team_color(str(row_b.get("team", ""))),
            show_zone_overlay=True, df_zones=df_zones_b,
        )
        st.plotly_chart(fig_sc_b, use_container_width=True)
    else:
        st.info(f"No shot chart data for {name_b}.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Section 5: Career Trend Comparison
# ---------------------------------------------------------------------------

st.subheader("📈 Historical Impact — Career Trend")
st.caption(
    "Both players on the same chart. Dashed = Player B. "
    "Switch between RAPM (actual), xRAPM (expected), O-RAPM, D-RAPM."
)

trend_metric = st.selectbox(
    "Metric",
    [("rapm", "RAPM"), ("xrapm", "xRAPM"), ("o_rapm", "O-RAPM"), ("d_rapm", "D-RAPM")],
    format_func=lambda x: x[1],
    key="cmp_trend_metric",
)

fig_trend = dual_trend_chart(
    df_a_full, name_a, COMPARE_COLORS[0],
    df_b_full, name_b, COMPARE_COLORS[1],
    metric=trend_metric[0],
    metric_label=trend_metric[1],
)
if fig_trend:
    st.plotly_chart(fig_trend, use_container_width=True)
else:
    st.info("No trend data for the selected metric.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Section 6: Process vs Results (Stability Analysis)
# ---------------------------------------------------------------------------

st.subheader("⚡ Process vs Results — Stability Analysis")
st.caption(
    "**RAPM − xRAPM gap**: large positive gap means outscoring shot quality "
    "(could regress). Large negative gap means underperforming process "
    "(positive regression candidate). "
    "Useful for contract evaluations, injury return projections, and trade targets."
)

def _gap_row(name: str, row: pd.Series, color: str) -> None:
    rapm  = row.get("rapm")
    xrapm = row.get("xrapm")
    fge   = row.get("fg_pct_above_expected")
    poss  = row.get("possessions", 0)

    gap = (float(rapm) - float(xrapm)) if pd.notna(rapm) and pd.notna(xrapm) else None

    cols = st.columns([2, 1, 1, 1, 3])
    cols[0].markdown(f"<b style='color:{color}'>{name}</b>", unsafe_allow_html=True)
    cols[1].metric("RAPM − xRAPM",
                   f"{gap:+.2f}" if gap is not None else "—",
                   delta=None)
    cols[2].metric("FG% vs Expected",
                   f"{float(fge):+.3f}" if pd.notna(fge) else "—",
                   delta=None)
    cols[3].metric("Stint Poss",
                   f"{int(poss):,}" if pd.notna(poss) else "—",
                   delta=None)

    flags = stability_flags(row)
    if flags:
        flag_html = " ".join(
            f'<span title="{f["help"]}" style="cursor:help;background:rgba(255,255,255,0.07);'
            f'border-radius:5px;padding:2px 8px;font-size:0.78rem">{f["text"]}</span>'
            for f in flags
        )
        cols[4].markdown(flag_html, unsafe_allow_html=True)

_gap_row(name_a, row_a, COMPARE_COLORS[0])
_gap_row(name_b, row_b, COMPARE_COLORS[1])

# ── Scatter: RAPM vs xRAPM with both players labelled ─────────────────────────
if not dist.empty and "rapm" in dist.columns and "xrapm" in dist.columns:
    with st.expander("📌 League context — RAPM vs xRAPM scatter"):
        st.caption(
            "Each dot = one player. Players above the diagonal are outperforming "
            "their shot quality (may regress). Below = underperforming process."
        )
        fig_scatter = go.Figure()

        # League background dots
        fig_scatter.add_trace(go.Scatter(
            x=dist["xrapm"], y=dist["rapm"],
            mode="markers",
            marker=dict(size=5, color="rgba(150,150,150,0.35)"),
            text=dist["full_name"],
            hovertemplate="%{text}<br>xRAPM: %{x:+.2f}<br>RAPM: %{y:+.2f}<extra></extra>",
            name="League",
            showlegend=True,
        ))

        # Player A dot
        if pd.notna(row_a.get("rapm")) and pd.notna(row_a.get("xrapm")):
            fig_scatter.add_trace(go.Scatter(
                x=[float(row_a["xrapm"])], y=[float(row_a["rapm"])],
                mode="markers+text",
                marker=dict(size=14, color=COMPARE_COLORS[0],
                            line=dict(width=2, color="white")),
                text=[name_a], textposition="top center",
                textfont=dict(color=COMPARE_COLORS[0], size=12),
                name=name_a,
                hovertemplate=f"{name_a}<br>xRAPM: %{{x:+.2f}}<br>RAPM: %{{y:+.2f}}<extra></extra>",
            ))

        # Player B dot
        if pd.notna(row_b.get("rapm")) and pd.notna(row_b.get("xrapm")):
            fig_scatter.add_trace(go.Scatter(
                x=[float(row_b["xrapm"])], y=[float(row_b["rapm"])],
                mode="markers+text",
                marker=dict(size=14, color=COMPARE_COLORS[1],
                            line=dict(width=2, color="white")),
                text=[name_b], textposition="top center",
                textfont=dict(color=COMPARE_COLORS[1], size=12),
                name=name_b,
                hovertemplate=f"{name_b}<br>xRAPM: %{{x:+.2f}}<br>RAPM: %{{y:+.2f}}<extra></extra>",
            ))

        # Diagonal reference
        axis_range = [
            min(dist["xrapm"].min(), dist["rapm"].min()) - 0.3,
            max(dist["xrapm"].max(), dist["rapm"].max()) + 0.3,
        ]
        fig_scatter.add_trace(go.Scatter(
            x=axis_range, y=axis_range,
            mode="lines",
            line=dict(color="rgba(200,200,200,0.25)", dash="dot", width=1.5),
            name="RAPM = xRAPM",
            showlegend=True,
        ))

        fig_scatter.add_annotation(
            x=axis_range[1] - 0.1, y=axis_range[1] + 0.1,
            text="Outperforming ↑", font=dict(size=10, color="rgba(200,200,200,0.5)"),
            showarrow=False,
        )
        fig_scatter.add_annotation(
            x=axis_range[1] - 0.1, y=axis_range[0] + 0.2,
            text="Underperforming ↓", font=dict(size=10, color="rgba(200,200,200,0.5)"),
            showarrow=False,
        )

        fig_scatter.update_layout(
            xaxis_title="xRAPM (Shot Quality)", yaxis_title="RAPM (Actual Outcomes)",
            height=400,
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", y=1.08),
        )
        fig_scatter.add_hline(y=0, line_dash="dot", line_color="rgba(200,200,200,0.25)")
        fig_scatter.add_vline(x=0, line_dash="dot", line_color="rgba(200,200,200,0.25)")
        st.plotly_chart(fig_scatter, use_container_width=True)
