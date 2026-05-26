"""
Leaderboards — single-season and multi-year pooled impact ratings.
Metric tabs: Overall · Offense · Defense · Shooting.
Distribution context shows where each value sits across the league.
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import numpy as np
import streamlit as st
import plotly.graph_objects as go
from scipy.stats import percentileofscore, gaussian_kde

from dashboard.utils.db import get_seasons, get_season_types
from dashboard.utils.queries import get_single_season_leaderboard, get_pooled_leaderboard
from dashboard.utils.nba_static import player_headshot_url, team_color
from dashboard.utils.theme import (
    ACCENT, ACCENT_BLUE, ACCENT_GREEN, ACCENT_GOLD, MUTED, MUTED_LIGHT,
    GRID, ZERO_LINE, section_label, MODEBAR,
)

st.set_page_config(
    page_title="Leaderboards · NBA xShot + RAPM",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Impact Leaderboards")
st.caption(
    "Model outputs ranked by player. Each metric is derived from the xShot or RAPM/xRAPM models — "
    "not box score statistics. All values are per 100 lineup-stint possessions vs a league-average player."
)

# ---------------------------------------------------------------------------
# Metric tab definitions
# ---------------------------------------------------------------------------

METRIC_TABS = {
    "Overall": [
        ("RAPM — Net Impact",          "rapm",                    ACCENT),
        ("xRAPM — Process Impact",     "xrapm",                   ACCENT_BLUE),
        ("RAPM − xRAPM  (Gap)",        "rapm_vs_xrapm",           ACCENT_GOLD),
    ],
    "Offense": [
        ("O-RAPM — Offensive Impact",  "o_rapm",                  ACCENT),
        ("Points Above Expected",      "shot_pts_above_expected",  ACCENT_GREEN),
        ("Avg Shot Difficulty (xShot)","mean_xshot",              ACCENT_GOLD),
    ],
    "Defense": [
        ("D-RAPM — Defensive Impact",  "d_rapm",                  ACCENT_BLUE),
    ],
    "Shooting": [
        ("FG% Above Expected",         "fg_pct_above_expected",   ACCENT_GREEN),
        ("Avg xShot (Shot Difficulty)","mean_xshot",              ACCENT_GOLD),
        ("Points Above Expected",      "shot_pts_above_expected",  ACCENT),
    ],
}

METRIC_HELP = {
    "rapm":                    "Net actual pts/100 poss vs avg, controlling for teammates & opponents",
    "xrapm":                   "Net expected pts/100 poss using xShot — process quality, less variance",
    "rapm_vs_xrapm":           "RAPM minus xRAPM — positive = outscoring process (finishing or variance)",
    "o_rapm":                  "Offensive pts/100 poss added above average player",
    "d_rapm":                  "Defensive pts/100 poss saved above average (positive = better)",
    "shot_pts_above_expected": "Total season points scored above the xShot baseline",
    "fg_pct_above_expected":   "Actual FG% minus model-predicted FG% — isolates shot-making skill",
    "mean_xshot":              "Average predicted make probability across all FGA (shot difficulty)",
    "ppg":                     "Points per game (raw box score, provided for context)",
}


def _fmt_val(v, col: str) -> str:
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return "—"
    if col in ("rapm", "xrapm", "rapm_vs_xrapm", "o_rapm", "d_rapm"):
        return f"{fv:+.2f}"
    if col in ("fg_pct_above_expected", "mean_xshot"):
        return f"{fv:+.3f}" if col == "fg_pct_above_expected" else f"{fv:.3f}"
    if col == "shot_pts_above_expected":
        return f"{fv:+.0f}"
    return f"{fv:.1f}"


# ---------------------------------------------------------------------------
# Common filter bar
# ---------------------------------------------------------------------------

tab_single, tab_pooled = st.tabs(["Single Season  (v1)", "3-Year Pooled + Prior  (v2)"])


# ===========================================================================
# SINGLE SEASON
# ===========================================================================

with tab_single:
    f1, f2, f3, f4 = st.columns([2, 2, 1, 1])
    seasons     = get_seasons()
    def_s       = "2024-25" if "2024-25" in seasons else seasons[0]
    season      = f1.selectbox("Season", seasons, index=seasons.index(def_s), key="ss_season")
    season_type = f2.selectbox("Season Type", get_season_types(), key="ss_stype")
    min_poss    = f3.number_input("Min Poss", min_value=100, max_value=5000,
                                  value=500, step=100, key="ss_minposs")
    top_n       = f4.number_input("Top N", min_value=5, max_value=50,
                                  value=20, step=5, key="ss_topn")

    df = get_single_season_leaderboard(season, season_type, int(min_poss))

    if df.empty:
        st.warning("No data for this selection.")
    else:
        # Team filter
        all_teams = sorted(df["team"].dropna().unique())
        sel_teams = st.multiselect("Filter by team  (blank = all)", all_teams, key="ss_teams")
        if sel_teams:
            df = df[df["team"].isin(sel_teams)]

        # ── Metric tabs ──────────────────────────────────────────────────────
        st.markdown(section_label("Rankings by Metric"), unsafe_allow_html=True)

        m_tabs = st.tabs(list(METRIC_TABS.keys()))

        for m_tab, (tab_name, metrics) in zip(m_tabs, METRIC_TABS.items()):
            with m_tab:
                if not metrics:
                    st.info("No metrics defined for this tab.")
                    continue

                # Default sort = first metric in the tab
                sort_opts = {label: col for label, col, _ in metrics}
                sort_label = st.selectbox(
                    "Sort by", list(sort_opts.keys()),
                    key=f"ss_sort_{tab_name}"
                )
                sort_col   = sort_opts[sort_label]
                sort_color = next(c for l, col, c in metrics if col == sort_col)

                df_sorted = (
                    df.sort_values(sort_col, ascending=False, na_position="last")
                    .reset_index(drop=True)
                )
                chart_df = df_sorted.head(int(top_n))

                if chart_df[sort_col].dropna().empty:
                    st.info(f"Column **{sort_col}** has no data — re-run the model to populate.")
                    continue

                hover_text = [
                    f"<b>{name}</b>  ({team})<br>"
                    f"RAPM: {_fmt_val(row['rapm'], 'rapm')} | "
                    f"xRAPM: {_fmt_val(row['xrapm'], 'xrapm')}<br>"
                    f"GP: {int(row['gp']) if str(row['gp']) not in ('', 'nan') else '—'} | "
                    f"Poss: {int(row['possessions'])}"
                    for name, team, row in zip(
                        chart_df["full_name"], chart_df["team"],
                        chart_df.to_dict("records"),
                    )
                ]

                fig = go.Figure(go.Bar(
                    x=chart_df[sort_col],
                    y=chart_df["full_name"],
                    orientation="h",
                    marker_color=[team_color(str(t)) for t in chart_df["team"]],
                    marker_line_color="rgba(255,255,255,0.10)",
                    marker_line_width=0.5,
                    text=[_fmt_val(v, sort_col) for v in chart_df[sort_col]],
                    textposition="outside",
                    cliponaxis=False,
                    hovertext=hover_text,
                    hoverinfo="text",
                ))
                fig.add_vline(x=0, line_dash="dot", line_color=ZERO_LINE)
                fig.update_layout(
                    title=f"Top {int(top_n)} — {sort_label}  ·  {season} {season_type}",
                    yaxis=dict(autorange="reversed", automargin=True, tickfont=dict(size=12)),
                    xaxis=dict(title=sort_label, showgrid=True, gridcolor=GRID, zeroline=False),
                    height=max(420, int(top_n) * 28),
                    margin=dict(l=20, r=100, t=50, b=20),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig, use_container_width=True, config=MODEBAR)

        # ── Distribution context ─────────────────────────────────────────────
        st.markdown(section_label("Distribution Context"), unsafe_allow_html=True)
        st.caption(
            "How extreme are these values? The histogram below shows the full league "
            "distribution. Select players to see vertical markers showing where they fall."
        )

        dist_metric_label = st.selectbox(
            "Show distribution for",
            {l: c for tab_m in METRIC_TABS.values() for l, c, _ in tab_m},
            key="ss_dist_metric",
        )
        dist_col = {l: c for tab_m in METRIC_TABS.values() for l, c, _ in tab_m}[dist_metric_label]

        selected_players = st.multiselect(
            "Highlight players  (up to 3)",
            df["full_name"].tolist() if not df.empty else [],
            max_selections=3,
            key="ss_dist_players",
        )

        if not df[dist_col].dropna().empty:
            vals = df[dist_col].dropna().values.astype(float)
            fig_dist = go.Figure()
            fig_dist.add_trace(go.Histogram(
                x=vals, nbinsx=28,
                marker_color="rgba(76,155,232,0.45)", marker_line_width=0,
                name=dist_metric_label,
                hovertemplate=f"{dist_metric_label}: %{{x:.2f}}<br>Players: %{{y}}<extra></extra>",
            ))
            if len(vals) >= 5:
                kde = gaussian_kde(vals, bw_method=0.4)
                x_range = np.linspace(vals.min() - 0.3, vals.max() + 0.3, 200)
                bw = (vals.max() - vals.min()) / 28
                fig_dist.add_trace(go.Scatter(
                    x=x_range, y=kde(x_range) * len(vals) * bw,
                    mode="lines", line=dict(color=ACCENT_BLUE, width=2),
                    showlegend=False, hoverinfo="skip",
                ))
            fig_dist.add_vline(x=0, line_dash="dot", line_color=ZERO_LINE)

            pal = [ACCENT_GOLD, ACCENT_GREEN, ACCENT]
            for i, name in enumerate(selected_players[:3]):
                row = df[df["full_name"] == name]
                if row.empty or row.iloc[0][dist_col] is None:
                    continue
                pv = float(row.iloc[0][dist_col])
                pct = percentileofscore(vals, pv, kind="rank")
                c = pal[i % len(pal)]
                fig_dist.add_vline(
                    x=pv, line_dash="solid", line_color=c, line_width=2,
                    annotation_text=f"{name.split()[-1]}  {_fmt_val(pv, dist_col)}  ({pct:.0f}th)",
                    annotation_font_color=c, annotation_font_size=10,
                    annotation_position="top left" if i % 2 == 0 else "top right",
                )
            fig_dist.update_layout(
                barmode="overlay",
                xaxis=dict(title=dist_metric_label, showgrid=True, gridcolor=GRID, zeroline=False),
                yaxis=dict(title="Player count", showgrid=True, gridcolor=GRID, zeroline=False),
                height=300,
                margin=dict(l=20, r=20, t=30, b=30),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                hovermode="closest",
            )
            st.plotly_chart(fig_dist, use_container_width=True, config=MODEBAR)

        # ── Full table ──────────────────────────────────────────────────────
        st.markdown(section_label("Full Rankings Table"), unsafe_allow_html=True)

        df_display = df.sort_values("rapm", ascending=False, na_position="last").reset_index(drop=True)
        df_display.insert(0, "Rank", range(1, len(df_display) + 1))
        df_display["headshot"] = df_display["person_id"].apply(player_headshot_url)

        st.dataframe(
            df_display[[
                "headshot", "Rank", "full_name", "team",
                "rapm", "xrapm", "rapm_vs_xrapm", "o_rapm", "d_rapm",
                "fg_pct_above_expected", "mean_xshot",
                "shot_pts_above_expected", "ppg", "possessions",
            ]],
            use_container_width=True,
            height=480,
            hide_index=True,
            column_config={
                "headshot":   st.column_config.ImageColumn(" ", width="small"),
                "Rank":       st.column_config.NumberColumn("#", width="small"),
                "full_name":  st.column_config.TextColumn("Player", width="medium"),
                "team":       st.column_config.TextColumn("Team", width="small"),
                "rapm":       st.column_config.NumberColumn(
                                  "RAPM", format="%.2f", width="small",
                                  help=METRIC_HELP["rapm"]),
                "xrapm":      st.column_config.NumberColumn(
                                  "xRAPM", format="%.2f", width="small",
                                  help=METRIC_HELP["xrapm"]),
                "rapm_vs_xrapm": st.column_config.NumberColumn(
                                  "RAPM−xRAPM", format="%.2f", width="small",
                                  help=METRIC_HELP["rapm_vs_xrapm"]),
                "o_rapm":     st.column_config.NumberColumn(
                                  "O-RAPM", format="%.2f", width="small",
                                  help=METRIC_HELP["o_rapm"]),
                "d_rapm":     st.column_config.NumberColumn(
                                  "D-RAPM", format="%.2f", width="small",
                                  help=METRIC_HELP["d_rapm"]),
                "fg_pct_above_expected": st.column_config.NumberColumn(
                                  "FG% vs Exp", format="+.3f", width="small",
                                  help=METRIC_HELP["fg_pct_above_expected"]),
                "mean_xshot": st.column_config.NumberColumn(
                                  "Avg xShot", format="%.3f", width="small",
                                  help=METRIC_HELP["mean_xshot"]),
                "shot_pts_above_expected": st.column_config.NumberColumn(
                                  "Pts Above Exp", format="%.0f", width="small",
                                  help=METRIC_HELP["shot_pts_above_expected"]),
                "ppg":        st.column_config.NumberColumn("PPG", format="%.1f", width="small"),
                "possessions": st.column_config.NumberColumn(
                                  "Poss", format="%.0f", width="small",
                                  help="Total stint possessions (RAPM sample size)"),
            },
        )


# ===========================================================================
# POOLED (v2)
# ===========================================================================

with tab_pooled:
    with st.expander("ℹ️ About the 3-year pooled model", expanded=False):
        st.markdown(
            "**Why pool 3 seasons?** More possessions per player reduce RAPM's collinearity "
            "and small-sample noise. **What is the box-score prior?** Each player's prior "
            "is their per-minute plus/minus scaled to per-100 possessions — a stable, "
            "volume-independent baseline. The ridge regression is run on `y − prior`, "
            "then the prior is added back. **RAPM+Prior is recommended** for cross-player "
            "comparisons as it correctly anchors estimates for players with sparse stints."
        )

    p1, p2, p3, p4 = st.columns([2, 2, 2, 1])
    pooled_stype = p1.selectbox("Season Type", get_season_types(), key="v2_stype")
    min_poss_v2  = p2.number_input("Min Pooled Poss", min_value=500, max_value=10000,
                                    value=1500, step=500, key="v2_minposs")
    top_n_v2     = p4.number_input("Top N", min_value=5, max_value=50,
                                    value=20, step=5, key="v2_topn")

    df_v2 = get_pooled_leaderboard(int(min_poss_v2))
    if not df_v2.empty:
        df_v2 = df_v2[df_v2["season_type"] == pooled_stype]

    if df_v2.empty:
        st.warning("No pooled data available.")
    else:
        windows = sorted(df_v2["window_label"].unique(), reverse=True)
        selected_window = p3.selectbox("3-Yr Window (end season)", windows, key="v2_window")
        df_w = (
            df_v2[df_v2["window_label"] == selected_window]
            .sort_values("rapm_prior", ascending=False)
            .reset_index(drop=True)
        )

        all_teams_v2 = sorted(df_w["team"].dropna().unique())
        sel_teams_v2 = st.multiselect("Filter by team", all_teams_v2, key="v2_teams")
        if sel_teams_v2:
            df_w = df_w[df_w["team"].isin(sel_teams_v2)]

        chart_v2 = df_w.head(int(top_n_v2))
        hover_v2 = [
            f"<b>{name}</b>  ({team})<br>"
            f"RAPM+Prior: {_fmt_val(rp, 'rapm')} | "
            f"xRAPM: {_fmt_val(x, 'xrapm')} | "
            f"RAPM raw: {_fmt_val(r, 'rapm')}<br>"
            f"Pooled Poss: {int(p)}"
            for name, team, rp, x, r, p in zip(
                chart_v2["full_name"], chart_v2["team"],
                chart_v2["rapm_prior"].fillna(0),
                chart_v2["xrapm"].fillna(0),
                chart_v2["rapm"].fillna(0),
                chart_v2["possessions"].fillna(0),
            )
        ]

        fig2 = go.Figure(go.Bar(
            x=chart_v2["rapm_prior"],
            y=chart_v2["full_name"],
            orientation="h",
            marker_color=[team_color(str(t)) for t in chart_v2["team"]],
            marker_line_color="rgba(255,255,255,0.10)",
            marker_line_width=0.5,
            text=[f"{v:+.2f}" for v in chart_v2["rapm_prior"]],
            textposition="outside",
            cliponaxis=False,
            hovertext=hover_v2,
            hoverinfo="text",
        ))
        fig2.add_vline(x=0, line_dash="dot", line_color=ZERO_LINE)
        fig2.update_layout(
            title=f"RAPM + Prior  ·  {selected_window}  {pooled_stype}",
            yaxis=dict(autorange="reversed", automargin=True, tickfont=dict(size=12)),
            xaxis=dict(title="RAPM + Box-Score Prior (pts/100 poss)",
                       showgrid=True, gridcolor=GRID, zeroline=False),
            height=max(420, int(top_n_v2) * 28),
            margin=dict(l=20, r=100, t=50, b=20),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig2, use_container_width=True, config=MODEBAR)

        st.dataframe(
            df_w[[
                "full_name", "team", "rapm_prior", "xrapm",
                "rapm", "rapm_vs_xrapm", "possessions",
            ]],
            use_container_width=True,
            height=460,
            hide_index=True,
            column_config={
                "full_name":     st.column_config.TextColumn("Player", width="medium"),
                "team":          st.column_config.TextColumn("Team", width="small"),
                "rapm_prior":    st.column_config.NumberColumn(
                                     "RAPM+Prior", format="%.2f", width="small",
                                     help="Pooled RAPM shrunk toward box-score baseline"),
                "xrapm":         st.column_config.NumberColumn("xRAPM", format="%.2f", width="small"),
                "rapm":          st.column_config.NumberColumn("RAPM (raw)", format="%.2f", width="small"),
                "rapm_vs_xrapm": st.column_config.NumberColumn("RAPM−xRAPM", format="%.2f", width="small"),
                "possessions":   st.column_config.NumberColumn("Pooled Poss", format="%.0f", width="small"),
            },
        )
