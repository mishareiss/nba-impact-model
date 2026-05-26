"""
NBA Basketball Intelligence Platform — Home
Executive overview, league trends, and navigation hub.
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import numpy as np
import streamlit as st
import plotly.graph_objects as go
from scipy.stats import gaussian_kde

from dashboard.utils.db import query
from dashboard.utils.nba_static import team_logo_url, player_headshot_url, team_color as _team_color

st.set_page_config(
    page_title="NBA Intelligence Platform",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Page-level CSS: tighter spacing, card styling, nav tiles
# ---------------------------------------------------------------------------
st.markdown("""
<style>
/* section divider */
.section-label {
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    color: rgba(180,180,180,0.55);
    text-transform: uppercase;
    margin: 28px 0 10px 0;
}
/* nav tiles */
.nav-grid { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 10px; }
.nav-tile {
    flex: 1; min-width: 160px;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.09);
    border-radius: 10px;
    padding: 18px 16px;
    text-decoration: none;
    transition: background 0.18s, border-color 0.18s;
    cursor: pointer;
}
.nav-tile:hover {
    background: rgba(232,70,42,0.10);
    border-color: rgba(232,70,42,0.45);
}
.nav-tile .nt-icon { font-size: 1.9rem; margin-bottom: 8px; }
.nav-tile .nt-title {
    font-size: 0.95rem; font-weight: 700; color: #F0F2F5;
    margin-bottom: 4px;
}
.nav-tile .nt-desc { font-size: 0.74rem; color: rgba(160,165,175,0.85); line-height: 1.4; }
/* exec metric cards */
.exec-cards { display: flex; gap: 10px; flex-wrap: wrap; }
.exec-card {
    flex: 1; min-width: 140px;
    background: rgba(255,255,255,0.042);
    border-left: 3px solid rgba(232,70,42,0.6);
    border-radius: 8px;
    padding: 12px 14px;
}
.ec-label { font-size: 0.68rem; font-weight: 600; color: rgba(160,165,175,0.85);
            text-transform: uppercase; letter-spacing: 0.05em; white-space: nowrap; }
.ec-value { font-size: 1.45rem; font-weight: 700; margin-top: 4px; }
.ec-sub   { font-size: 0.72rem; color: rgba(160,165,175,0.70); margin-top: 3px; }
/* intel feed placeholder */
.intel-placeholder {
    border: 1.5px dashed rgba(255,255,255,0.15);
    border-radius: 10px;
    padding: 28px 24px;
    text-align: center;
    color: rgba(160,165,175,0.60);
    font-size: 0.85rem;
}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Cached queries
# ---------------------------------------------------------------------------

@st.cache_data(ttl=1800, show_spinner=False)
def load_league_trends(season_type: str):
    """Shot profile + efficiency trends across all seasons from player_shot_zones."""
    return query(
        """
        SELECT season, season_type,
               ROUND((SUM(makes)::float
                      / NULLIF(SUM(attempts),0))::numeric, 4)                AS fg_pct,
               ROUND((SUM(attempts * mean_xshot)
                      / NULLIF(SUM(attempts),0))::numeric, 4)                AS avg_xshot,
               ROUND(((SUM(makes)
                       + 0.5 * SUM(CASE WHEN shot_value=3 THEN makes ELSE 0 END))::float
                      / NULLIF(SUM(attempts),0))::numeric, 4)                AS efg_pct,
               ROUND((SUM(CASE WHEN shot_zone='three'    THEN attempts END)::float
                      / NULLIF(SUM(attempts),0))::numeric, 4)                AS three_rate,
               ROUND((SUM(CASE WHEN shot_zone='at_rim'   THEN attempts END)::float
                      / NULLIF(SUM(attempts),0))::numeric, 4)                AS rim_rate,
               ROUND((SUM(CASE WHEN shot_zone IN ('short_mid','mid_range','long_mid')
                                    THEN attempts END)::float
                      / NULLIF(SUM(attempts),0))::numeric, 4)                AS midrange_rate,
               SUM(attempts)                                                  AS total_attempts
        FROM player_shot_zones
        WHERE season_type = :season_type
        GROUP BY season, season_type
        ORDER BY season
        """,
        {"season_type": season_type},
    )


@st.cache_data(ttl=1800, show_spinner=False)
def load_team_records(season: str, season_type: str) -> dict:
    """
    Derive win/loss records from lineup_stints by summing points per game.
    Returns dict keyed by team tricode: {'w': int, 'l': int}.
    """
    df = query(
        """
        WITH game_scores AS (
            SELECT ls.game_id, ls.home_team_id, ls.away_team_id,
                   SUM(ls.home_points) AS home_pts,
                   SUM(ls.away_points) AS away_pts
            FROM lineup_stints ls
            WHERE ls.season = :season AND ls.season_type = :season_type
            GROUP BY ls.game_id, ls.home_team_id, ls.away_team_id
        ),
        team_records AS (
            SELECT home_team_id AS team_id,
                   SUM(CASE WHEN home_pts > away_pts THEN 1 ELSE 0 END) AS wins,
                   SUM(CASE WHEN home_pts < away_pts THEN 1 ELSE 0 END) AS losses
            FROM game_scores GROUP BY home_team_id
            UNION ALL
            SELECT away_team_id AS team_id,
                   SUM(CASE WHEN away_pts > home_pts THEN 1 ELSE 0 END) AS wins,
                   SUM(CASE WHEN away_pts < home_pts THEN 1 ELSE 0 END) AS losses
            FROM game_scores GROUP BY away_team_id
        )
        SELECT t.tricode, SUM(wins) AS w, SUM(losses) AS l
        FROM team_records tr
        JOIN teams t ON t.team_id = tr.team_id
        GROUP BY t.tricode
        ORDER BY t.tricode
        """,
        {"season": season, "season_type": season_type},
    )
    if df.empty:
        return {}
    return {
        row["tricode"]: {"w": int(row["w"]), "l": int(row["l"])}
        for _, row in df.iterrows()
    }


@st.cache_data(ttl=600, show_spinner=False)
def load_snapshot(season: str, season_type: str):
    """Single-season exec snapshot metrics."""
    snap = query(
        """
        SELECT
            ROUND((SUM(makes)::float / NULLIF(SUM(attempts),0))::numeric, 3)    AS fg_pct,
            ROUND((SUM(attempts * mean_xshot) / NULLIF(SUM(attempts),0))::numeric, 3)
                                                                                 AS avg_xshot,
            ROUND(((SUM(makes) + 0.5*SUM(CASE WHEN shot_value=3 THEN makes ELSE 0 END))::float
                   / NULLIF(SUM(attempts),0))::numeric, 3)                       AS efg_pct,
            ROUND((SUM(CASE WHEN shot_zone='three' THEN attempts END)::float
                   / NULLIF(SUM(attempts),0))::numeric, 3)                       AS three_rate,
            ROUND((SUM(CASE WHEN shot_zone='at_rim' THEN attempts END)::float
                   / NULLIF(SUM(attempts),0))::numeric, 3)                       AS rim_rate,
            SUM(attempts)                                                         AS total_fga
        FROM player_shot_zones
        WHERE season = :season AND season_type = :season_type
        """,
        {"season": season, "season_type": season_type},
    )
    best_team = query(
        """
        SELECT team, team_name,
               ROUND((pts_above_expected_off - pts_above_expected_def)::numeric, 0)
                   AS net_pts_above_expected
        FROM team_shot_quality
        WHERE season = :season AND season_type = :season_type
        ORDER BY (pts_above_expected_off - pts_above_expected_def) DESC NULLS LAST
        LIMIT 1
        """,
        {"season": season, "season_type": season_type},
    )
    worst_team = query(
        """
        SELECT team, team_name,
               ROUND((pts_above_expected_off - pts_above_expected_def)::numeric, 0)
                   AS net_pts_above_expected
        FROM team_shot_quality
        WHERE season = :season AND season_type = :season_type
        ORDER BY (pts_above_expected_off - pts_above_expected_def) ASC NULLS LAST
        LIMIT 1
        """,
        {"season": season, "season_type": season_type},
    )
    top_player = query(
        """
        SELECT MAX(person_id) AS person_id, full_name, team,
               ROUND(MAX(xrapm)::numeric, 2) AS xrapm
        FROM player_career_stats
        WHERE season = :season AND season_type = :season_type
          AND possessions >= 500
        GROUP BY full_name, team
        ORDER BY ROUND(MAX(xrapm)::numeric, 2) DESC NULLS LAST
        LIMIT 1
        """,
        {"season": season, "season_type": season_type},
    )
    return snap, best_team, worst_team, top_player


@st.cache_data(ttl=1800, show_spinner=False)
def load_rapm_dist(season: str, season_type: str, min_poss: int = 300):
    """Per-player RAPM and xRAPM values for distribution chart."""
    return query(
        """
        SELECT full_name, team,
               MAX(rapm)   AS rapm,
               MAX(xrapm)  AS xrapm,
               MAX(o_rapm) AS o_rapm,
               MAX(d_rapm) AS d_rapm,
               MAX(possessions) AS possessions
        FROM player_career_stats
        WHERE season = :season AND season_type = :season_type
          AND possessions >= :min_poss
        GROUP BY full_name, team
        ORDER BY rapm DESC NULLS LAST
        """,
        {"season": season, "season_type": season_type, "min_poss": min_poss},
    )


# ---------------------------------------------------------------------------
# Helper: HTML exec metric card (with optional image)
# ---------------------------------------------------------------------------

def _exec_card(label: str, value: str, sub: str = "",
               accent: str = "rgba(232,70,42,0.6)",
               img_url: str = "", img_round: bool = False) -> str:
    img_html = ""
    if img_url:
        shape = "border-radius:50%;" if img_round else "border-radius:4px;"
        img_html = (
            f'<div style="margin-bottom:6px">'
            f'<img src="{img_url}" '
            f'style="height:34px;width:auto;max-width:60px;object-fit:contain;{shape}" '
            f'onerror="this.style.display=\'none\'">'
            f'</div>'
        )
    return (
        f'<div class="exec-card" style="border-left-color:{accent}">'
        f'{img_html}'
        f'<div class="ec-label">{label}</div>'
        f'<div class="ec-value">{value}</div>'
        f'{"<div class=ec-sub>" + sub + "</div>" if sub else ""}'
        f'</div>'
    )


def _fmt(v, spec: str) -> str:
    try:
        return f"{float(v):{spec}}"
    except Exception:
        return "—"


# ---------------------------------------------------------------------------
# Global filter bar
# ---------------------------------------------------------------------------

st.markdown(
    "<h1 style='margin-bottom:2px'>🏀 NBA Basketball Intelligence</h1>"
    "<p style='color:rgba(160,165,175,0.75);font-size:0.92rem;margin-top:0'>"
    "2.68 million field goal attempts · 12 seasons (2014-15 → 2025-26) · "
    "Shot quality modelling, impact ratings, lineup analytics</p>",
    unsafe_allow_html=True,
)

flt_c1, flt_c2, flt_c3 = st.columns([2, 2, 6])
focus_season = flt_c1.selectbox(
    "Focus Season",
    ["2025-26", "2024-25", "2023-24", "2022-23", "2021-22", "2020-21",
     "2019-20", "2018-19", "2017-18", "2016-17", "2015-16", "2014-15"],
    index=0, key="home_season",
)
season_type = flt_c2.selectbox(
    "Season Type", ["Regular Season", "Playoffs"], key="home_stype"
)

# ---------------------------------------------------------------------------
# Section 1 — Executive Snapshot
# ---------------------------------------------------------------------------

st.markdown('<div class="section-label">Executive Snapshot</div>', unsafe_allow_html=True)

snap_df, best_team_df, worst_team_df, top_player_df = load_snapshot(focus_season, season_type)
records = load_team_records(focus_season, season_type)

def _record_str(tricode: str) -> str:
    rec = records.get(tricode)
    return f"{rec['w']}–{rec['l']}" if rec else ""

if not snap_df.empty:
    s  = snap_df.iloc[0]
    bt = best_team_df.iloc[0]  if not best_team_df.empty  else None
    wt = worst_team_df.iloc[0] if not worst_team_df.empty else None
    tp = top_player_df.iloc[0] if not top_player_df.empty else None

    # ── Row 1: league-wide metrics (no images) ──────────────────────────
    row1 = '<div class="exec-cards">'
    row1 += _exec_card(
        "League Avg xShot", _fmt(s["avg_xshot"], ".3f"),
        "Predicted make probability",
    )
    row1 += _exec_card(
        "League FG%", _fmt(s["fg_pct"], ".3f"),
        f"eFG%: {_fmt(s['efg_pct'], '.3f')}",
        accent="rgba(46,204,113,0.6)",
    )
    row1 += _exec_card(
        "3-Point Rate", _fmt(float(s["three_rate"]) * 100, ".1f") + "%",
        "of all FGA from beyond arc",
        accent="rgba(76,155,232,0.6)",
    )
    row1 += _exec_card(
        "Rim Frequency", _fmt(float(s["rim_rate"]) * 100, ".1f") + "%",
        "at-rim / restricted area",
        accent="rgba(241,196,15,0.6)",
    )
    row1 += "</div>"
    st.markdown(row1, unsafe_allow_html=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ── Row 2: best team, worst team, top player (with images) ──────────
    row2 = '<div class="exec-cards">'

    if bt is not None:
        bt_rec   = _record_str(str(bt["team"]))
        bt_logo  = team_logo_url(str(bt["team"])) or ""
        bt_color = _team_color(str(bt["team"]))
        row2 += _exec_card(
            "Best Team — Net xShot",
            f"+{int(bt['net_pts_above_expected'])} pts",
            f"{bt['team_name']}  {bt_rec}",
            accent=bt_color,
            img_url=bt_logo,
        )

    if wt is not None:
        wt_rec   = _record_str(str(wt["team"]))
        wt_logo  = team_logo_url(str(wt["team"])) or ""
        wt_color = _team_color(str(wt["team"]))
        row2 += _exec_card(
            "Worst Team — Net xShot",
            f"{int(wt['net_pts_above_expected'])} pts",
            f"{wt['team_name']}  {wt_rec}",
            accent=wt_color,
            img_url=wt_logo,
        )

    if tp is not None:
        pid        = int(tp["person_id"])
        hs_url     = player_headshot_url(pid)
        tp_color   = _team_color(str(tp["team"]))
        row2 += _exec_card(
            "Top xRAPM Player",
            f"{tp['full_name']}",
            f"{tp['team']} · xRAPM +{_fmt(tp['xrapm'], '.2f')}",
            accent=tp_color,
            img_url=hs_url,
            img_round=True,
        )

    row2 += "</div>"
    st.markdown(row2, unsafe_allow_html=True)

else:
    st.info(f"No data available for {focus_season} {season_type}.")

# ---------------------------------------------------------------------------
# Section 2 — League Trends Overview
# ---------------------------------------------------------------------------

st.markdown('<div class="section-label">League Trends Overview</div>', unsafe_allow_html=True)
st.caption(
    f"Showing **{season_type}** data across all 12 seasons. "
    "Charts illustrate the structural evolution of NBA offence since 2014-15."
)

trends_df = load_league_trends(season_type)

_CHART_LAYOUT = dict(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    hovermode="x unified",
    legend=dict(orientation="h", y=1.08),
    height=380,
    margin=dict(l=20, r=20, t=40, b=20),
)
_GRID = dict(showgrid=True, gridcolor="rgba(80,80,80,0.25)", zeroline=False)
_XSEASON = dict(showgrid=False, title="Season")
_MODEBAR = {"modeBarButtonsToAdd": ["downloadImage"], "displaylogo": False}


# ── A: Shot Profile Evolution ──────────────────────────────────────────────────
st.markdown("**📐 Shot Profile Evolution**")
st.caption(
    "The NBA's analytical revolution in a single chart. "
    "Mid-range frequency collapsed from **45.7% → 25.5%** as analytics departments "
    "quantified the cost of long 2s. 3-point rate rose from **26.8% → 42.1%**."
)

if not trends_df.empty:
    df_t = trends_df.copy()
    fig_shot = go.Figure()
    fig_shot.add_trace(go.Scatter(
        x=df_t["season"], y=(df_t["three_rate"] * 100).round(1),
        mode="lines+markers", name="3-Point Rate",
        line=dict(color="#E8462A", width=2.5), marker=dict(size=7),
        hovertemplate="%{x}: <b>%{y:.1f}%</b> 3PT rate<extra></extra>",
    ))
    fig_shot.add_trace(go.Scatter(
        x=df_t["season"], y=(df_t["rim_rate"] * 100).round(1),
        mode="lines+markers", name="At-Rim Rate",
        line=dict(color="#2ECC71", width=2.5), marker=dict(size=7),
        hovertemplate="%{x}: <b>%{y:.1f}%</b> at-rim rate<extra></extra>",
    ))
    fig_shot.add_trace(go.Scatter(
        x=df_t["season"], y=(df_t["midrange_rate"] * 100).round(1),
        mode="lines+markers", name="Mid-Range Rate",
        line=dict(color="#AAB7B8", width=2, dash="dash"), marker=dict(size=7),
        hovertemplate="%{x}: <b>%{y:.1f}%</b> mid-range rate<extra></extra>",
    ))
    fig_shot.update_layout(
        **_CHART_LAYOUT,
        xaxis=_XSEASON,
        yaxis=dict(**_GRID, title="% of All FGA", tickformat=".0f", ticksuffix="%"),
    )
    st.plotly_chart(fig_shot, use_container_width=True, config=_MODEBAR)
else:
    st.info("No trend data available.")

st.markdown("<br>", unsafe_allow_html=True)

# ── B: League Efficiency Trends ───────────────────────────────────────────────
st.markdown("**📈 League Efficiency Trends**")
st.caption(
    "League-wide efficiency has improved steadily as teams moved to higher-value shots. "
    "**eFG%** adjusts FG% for the 3-point bonus (a made 3 = 1.5x a made 2). "
    "**Avg xShot** tracks eFG% closely — confirming the model is well-calibrated."
)

if not trends_df.empty:
    df_e = trends_df.copy()
    fig_eff = go.Figure()
    fig_eff.add_trace(go.Scatter(
        x=df_e["season"], y=(df_e["efg_pct"] * 100).round(2),
        mode="lines+markers", name="eFG%",
        line=dict(color="#E8462A", width=2.5), marker=dict(size=7),
        hovertemplate="%{x}: <b>%{y:.2f}%</b> eFG%<extra></extra>",
    ))
    fig_eff.add_trace(go.Scatter(
        x=df_e["season"], y=(df_e["avg_xshot"] * 100).round(2),
        mode="lines+markers", name="Avg xShot (expected eFG% proxy)",
        line=dict(color="#4C9BE8", width=2.5, dash="dash"), marker=dict(size=7),
        hovertemplate="%{x}: <b>%{y:.2f}%</b> avg xShot<extra></extra>",
    ))
    fig_eff.add_trace(go.Scatter(
        x=df_e["season"], y=(df_e["fg_pct"] * 100).round(2),
        mode="lines+markers", name="Raw FG%",
        line=dict(color="#AAB7B8", width=1.5, dash="dot"), marker=dict(size=5),
        hovertemplate="%{x}: <b>%{y:.2f}%</b> FG%<extra></extra>",
    ))
    fig_eff.update_layout(
        **_CHART_LAYOUT,
        xaxis=_XSEASON,
        yaxis=dict(**_GRID, title="Efficiency (%)", tickformat=".1f", ticksuffix="%"),
    )
    st.plotly_chart(fig_eff, use_container_width=True, config=_MODEBAR)
else:
    st.info("No trend data available.")

st.markdown("<br>", unsafe_allow_html=True)

# ── C: RAPM Distribution ──────────────────────────────────────────────────────
st.markdown("**⚖️ RAPM Distribution**")
st.caption(
    f"Distribution of RAPM and xRAPM across all qualified players — "
    f"**{focus_season} {season_type}** (≥300 stint possessions). "
    "Most players cluster near 0. Elite players sit at +1 to +2."
)

rapm_df = load_rapm_dist(focus_season, season_type, min_poss=300)

if not rapm_df.empty:
    rapm_vals  = rapm_df["rapm"].dropna().values
    xrapm_vals = rapm_df["xrapm"].dropna().values

    fig_dist = go.Figure()

    for vals, name, color in [
        (rapm_vals,  "RAPM",  "rgba(232,70,42,0.55)"),
        (xrapm_vals, "xRAPM", "rgba(76,155,232,0.45)"),
    ]:
        if len(vals) < 5:
            continue
        fig_dist.add_trace(go.Histogram(
            x=vals, name=name, nbinsx=28,
            marker_color=color, marker_line_width=0, opacity=0.7,
            hovertemplate=f"{name}: %{{x:.2f}}<br>Players: %{{y}}<extra></extra>",
        ))
        kde = gaussian_kde(vals, bw_method=0.4)
        x_range = np.linspace(vals.min() - 0.3, vals.max() + 0.3, 200)
        bin_width = (vals.max() - vals.min()) / 28
        y_scaled = kde(x_range) * len(vals) * bin_width
        solid = color.replace("0.55", "0.9").replace("0.45", "0.9")
        fig_dist.add_trace(go.Scatter(
            x=x_range, y=y_scaled, mode="lines",
            line=dict(color=solid, width=2),
            showlegend=False, hoverinfo="skip",
        ))

    fig_dist.add_vline(x=0,    line_dash="dot", line_color="rgba(200,200,200,0.4)",
                       annotation_text="League avg",
                       annotation_font_color="rgba(180,180,180,0.6)",
                       annotation_position="top right")
    fig_dist.add_vline(x=1.0,  line_dash="dot", line_color="rgba(46,204,113,0.3)",
                       annotation_text="+1.0", annotation_position="top",
                       annotation_font_color="rgba(46,204,113,0.5)")
    fig_dist.add_vline(x=-1.0, line_dash="dot", line_color="rgba(231,76,60,0.3)",
                       annotation_text="−1.0", annotation_position="top",
                       annotation_font_color="rgba(231,76,60,0.5)")

    top3 = rapm_df.nlargest(3, "rapm")
    for _, r in top3.iterrows():
        try:
            fig_dist.add_annotation(
                x=float(r["rapm"]), y=0,
                text=r["full_name"].split()[-1],
                showarrow=True, arrowhead=2,
                font=dict(size=9, color="rgba(232,70,42,0.85)"),
                ax=0, ay=40,
            )
        except (TypeError, ValueError):
            pass

    # RAPM distribution uses closest hover (not x unified — it's a histogram)
    dist_layout = {**_CHART_LAYOUT, "hovermode": "closest"}
    dist_layout.pop("hovermode") if "hovermode" in _CHART_LAYOUT else None
    fig_dist.update_layout(
        **_CHART_LAYOUT,
        barmode="overlay",
        xaxis=dict(**_GRID, title="RAPM / xRAPM (pts/100 poss vs avg)"),
        yaxis=dict(**_GRID, title="Player Count"),
    )
    fig_dist.update_layout(hovermode="closest")   # override after base layout

    st.plotly_chart(fig_dist, use_container_width=True, config=_MODEBAR)

    n = len(rapm_df)
    above_0 = int((rapm_df["rapm"].dropna() > 0).sum())
    median_rapm = float(rapm_df["rapm"].dropna().median())
    std_rapm    = float(rapm_df["rapm"].dropna().std())
    st.caption(
        f"**{n}** qualified players · "
        f"**{above_0}** above 0 ({above_0/n*100:.0f}%) · "
        f"Median RAPM: **{median_rapm:+.2f}** · "
        f"Std dev: **{std_rapm:.2f}** pts/100 poss"
    )
else:
    st.info(f"No RAPM data available for {focus_season} {season_type}.")


# ---------------------------------------------------------------------------
# Section 3 — League Intelligence Feed  (placeholder)
# ---------------------------------------------------------------------------

st.markdown('<div class="section-label">League Intelligence Feed</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="intel-placeholder">'
    '<div style="font-size:1.5rem;margin-bottom:10px">🧠</div>'
    '<div style="font-weight:600;color:rgba(200,205,215,0.75);margin-bottom:6px">'
    'Auto-Generated Insights — Coming Soon</div>'
    'This section will surface automatically generated analytical findings:<br>'
    '"Oklahoma City generated the highest shot quality differential in the league."<br>'
    '"Shai Gilgeous-Alexander\'s xRAPM improved most over the last 3 seasons."<br>'
    '"Mid-range attempts are at a new 12-season low."'
    '</div>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Section 4 — Quick Access Tiles
# ---------------------------------------------------------------------------

st.markdown('<div class="section-label">Navigation</div>', unsafe_allow_html=True)

_TILES = [
    ("pages/1_Leaderboards.py",    "📊", "Leaderboards",
     "RAPM, xRAPM, O-RAPM, D-RAPM rankings. Single-season and multi-year pooled."),
    ("pages/2_Player_Profile.py",  "👤", "Player Profile",
     "Percentile profile, shot chart, career trends, archetype & stability flags."),
    ("pages/3_Team_Analytics.py",  "🏟️", "Team Analytics",
     "Shot quality offence vs defence. Team percentile profile & season trends."),
    ("pages/5_Compare.py",         "⚖️", "Compare Players",
     "Side-by-side percentile, shot profile, shot chart & stability analysis."),
    ("pages/4_Glossary.py",        "📖", "Glossary",
     "Plain-English definitions of every metric used in this platform."),
]

tile_cols = st.columns(len(_TILES))
for col, (page, icon, title, desc) in zip(tile_cols, _TILES):
    with col:
        st.page_link(
            page,
            label=f"{icon}  **{title}**",
            use_container_width=True,
        )
        st.caption(desc)

# ---------------------------------------------------------------------------
# Footer: how this works
# ---------------------------------------------------------------------------

st.markdown("---")
with st.expander("ℹ️  How this system works"):
    st.markdown("""
**Step 1 — Shot Quality (xShot)**
Every field goal attempt is scored by an XGBoost model trained on location, shot type,
and game context. Output is a 0–1 probability of the shot being made. A restricted-area
dunk scores ~0.95; a contested pull-up mid-range scores ~0.35.

**Step 2 — Shot-Making Over Expected (FG% vs Expected)**
Comparing xShot predictions to outcomes reveals which players consistently over- or
under-perform the difficulty of their attempts. This isolates shot-making skill from
shot selection and volume.

**Step 3 — Player Impact (RAPM / xRAPM / O-RAPM / D-RAPM)**
Every game is parsed into lineup stints — periods where both 5-player lineups are stable.
Ridge regression over all ~421k stints estimates each player's marginal contribution to
team scoring margin per 100 possessions, controlling for teammates and opponents simultaneously.
xRAPM uses xShot-derived points instead of actual points — a process-based impact metric.

**Step 4 — Multi-Year Pooling + Box-Score Prior (v2)**
Rolling 3-season windows reduce single-season noise. A box-score prior anchors
estimates toward historical baselines, correctly elevating stars whose impact is
measurable from traditional stats.

**Data:** NBA Stats API · 2014-15 through 2025-26 · Regular Season + Playoffs
    """)
