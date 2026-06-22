"""
Decision Support — player categorisation for basketball operations.

Derives categories from xRAPM, RAPM, and process gap:
  - Undervalued / Buy-Low: xRAPM >> RAPM (process better than outcomes)
  - Overrated / Sell-High: RAPM >> xRAPM (outcomes better than process)
  - Hidden Contributors:   D-RAPM strong, PPG low (box-score undervalued defenders)
  - Breakout Candidates:   improving xRAPM year-over-year
  - Elite Process Players: xRAPM ≥ 90th percentile
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
from scipy.stats import percentileofscore

from dashboard.utils.db import get_seasons, get_season_types
from dashboard.utils.queries import get_decision_support, get_player_trajectory
from dashboard.utils.nba_static import player_headshot_url, team_color
from dashboard.utils.theme import (
    inject_global_css, page_header, section_label, art_section,
    finding, chart_caption, metric_card, metric_row, insight_card,
    ACCENT, ACCENT_BLUE, ACCENT_GREEN, ACCENT_GOLD, ACCENT_PURPLE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, SURFACE, BORDER, GRID, MODEBAR,
)

st.set_page_config(
    page_title="Decision Support · NBA Impact Dashboard",
    page_icon="",
    layout="wide",
)
inject_global_css()


def _fmt(v, spec: str) -> str:
    try:
        return f"{float(v):{spec}}"
    except (TypeError, ValueError):
        return "—"

st.markdown(
    page_header(
        "Decision Support",
        "Player categorisation for roster construction decisions. "
        "Derived from xRAPM, RAPM, and process gap — not from box-score statistics alone. "
        "All outputs should be treated as one data point, not a final verdict.",
    ),
    unsafe_allow_html=True,
)

st.markdown(
    f'<div style="background:rgba(245,158,11,0.07);border:1px solid rgba(245,158,11,0.25);'
    f'border-radius:8px;padding:10px 16px;margin-bottom:16px;font-size:0.82rem;color:{TEXT_SECONDARY}">'
    f'⚠️ These categories are quantitative models, not scouting reports. '
    f'Always supplement with qualitative context: injury history, contract situation, '
    f'team system fit, age curve.</div>',
    unsafe_allow_html=True,
)

# ── Filters ───────────────────────────────────────────────────────────────────
f1, f2, f3 = st.columns([2, 2, 1])
seasons      = get_seasons()
def_s        = "2025-26" if "2025-26" in seasons else seasons[0]
season       = f1.selectbox("Season", seasons, index=seasons.index(def_s))
season_type  = f2.selectbox("Season Type", get_season_types())
min_poss     = f3.number_input("Min Possessions", 300, 3000, 500, 100)

# ── Data ──────────────────────────────────────────────────────────────────────
with st.spinner("Loading player data…"):
    df = get_decision_support(season, season_type, int(min_poss))

if df.empty:
    st.markdown(
        f'<div style="text-align:center;padding:48px;color:{TEXT_SECONDARY}">'
        f'No data for this selection.</div>',
        unsafe_allow_html=True,
    )
    st.stop()

# ── Compute league percentiles ─────────────────────────────────────────────────
xrapm_vals = df["xrapm"].dropna().values.astype(float)
rapm_vals  = df["rapm"].dropna().values.astype(float)
gap_vals   = df["rapm_vs_xrapm"].dropna().values.astype(float)
drapm_vals = df["d_rapm"].dropna().values.astype(float)


def pct(series, val):
    clean = series[~np.isnan(series)]
    return percentileofscore(clean, float(val), kind="rank") if len(clean) >= 5 else 50.0


df["xrapm_pct"]      = df["xrapm"].apply(lambda x: pct(xrapm_vals, x) if pd.notna(x) else None)
df["rapm_pct"]       = df["rapm"].apply(lambda x: pct(rapm_vals, x) if pd.notna(x) else None)
df["gap_pct"]        = df["rapm_vs_xrapm"].apply(lambda x: pct(-gap_vals, x) if pd.notna(x) else None)
df["drapm_pct"]      = df["d_rapm"].apply(lambda x: pct(drapm_vals, x) if pd.notna(x) else None)

# ── Category thresholds ───────────────────────────────────────────────────────
PROCESS_PCT     = 50   # xRAPM percentile to be "above average process"
OUTCOMES_PCT    = 50   # RAPM percentile to be "above average outcomes"
BUY_GAP         = 0.7  # min xRAPM - RAPM gap to be flagged as buy-low
SELL_GAP        = 0.7  # min RAPM - xRAPM gap to be flagged as sell-high
DEFENDER_DRAPM  = 0.5  # D-RAPM threshold for hidden contributor
DEFENDER_PPG    = 12.0 # max PPG for "hidden" (not getting scoring credit)
ELITE_XRAPM     = 85   # xRAPM percentile for elite process

elite_mask       = df["xrapm_pct"] >= ELITE_XRAPM
buy_mask         = (df["rapm_vs_xrapm"] <= -BUY_GAP) & (df["xrapm_pct"] >= PROCESS_PCT)
sell_mask        = (df["rapm_vs_xrapm"] >=  SELL_GAP) & (df["rapm_pct"] >= OUTCOMES_PCT)
hidden_mask      = (df["d_rapm"] >= DEFENDER_DRAPM) & ((df["ppg"].fillna(0)) <= DEFENDER_PPG)
regression_mask  = sell_mask

df_elite   = df[elite_mask].sort_values("xrapm",          ascending=False).head(15)
df_buy     = df[buy_mask].sort_values("rapm_vs_xrapm",    ascending=True).head(15)
df_sell    = df[sell_mask].sort_values("rapm_vs_xrapm",   ascending=False).head(15)
df_hidden  = df[hidden_mask].sort_values("d_rapm",        ascending=False).head(15)

n_buy  = len(df[buy_mask])
n_sell = len(df[sell_mask])

# ── Overview KPIs ─────────────────────────────────────────────────────────────
st.markdown(
    metric_row(
        metric_card("Buy-Low Candidates",  str(n_buy),  f"xRAPM ≫ RAPM by ≥{BUY_GAP}", ACCENT_GREEN),
        metric_card("Sell-High Candidates", str(n_sell), f"RAPM ≫ xRAPM by ≥{SELL_GAP}", "#EF4444"),
        metric_card("Elite Process Players", str(len(df_elite)), f"xRAPM ≥ {ELITE_XRAPM}th percentile", ACCENT),
        metric_card("Hidden Contributors",   str(len(df[hidden_mask])),
                    f"D-RAPM ≥ {DEFENDER_DRAPM} & PPG ≤ {DEFENDER_PPG}", ACCENT_PURPLE),
        metric_card("Qualifying Players",    str(len(df)), f"≥{min_poss} poss", TEXT_MUTED),
    ),
    unsafe_allow_html=True,
)

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_buy, tab_sell, tab_elite, tab_hidden, tab_scatter, tab_trajectory = st.tabs([
    "Buy-Low", "Sell-High", "Elite Process", "Hidden Contributors", "Scatter Map", "Trajectories",
])


def _player_row(rank: int, row: pd.Series, main_metric: str, main_fmt: str, main_label: str,
                sub_metric: str | None, sub_fmt: str, sub_label: str,
                accent: str, note: str = "") -> None:
    tcolor = team_color(str(row.get("team", "")))
    val    = float(row[main_metric]) if pd.notna(row.get(main_metric)) else None
    sval   = float(row[sub_metric])  if sub_metric and pd.notna(row.get(sub_metric)) else None
    val_s  = f"{val:{main_fmt}}" if val is not None else "—"
    sval_s = f"{sval:{sub_fmt}}"  if sval is not None else "—"
    poss_v = f'{int(row["possessions"]):,}' if str(row.get("possessions", "")) not in ("", "nan") else "—"

    st.markdown(
        f'<div style="display:flex;align-items:center;gap:12px;'
        f'background:{SURFACE};border:1px solid {BORDER};border-radius:7px;'
        f'padding:9px 14px;margin-bottom:5px">'
        f'<div style="font-size:0.72rem;font-weight:700;color:{TEXT_MUTED};'
        f'min-width:26px;text-align:center">#{rank}</div>'
        f'<div style="flex:1">'
        f'<div style="font-size:0.88rem;font-weight:600;color:{TEXT_PRIMARY}">{row["full_name"]}</div>'
        f'<div style="font-size:0.72rem;font-weight:600;color:{tcolor}">{row["team"]}</div>'
        f'{"<div style=font-size:0.72rem;color:" + TEXT_MUTED + ">" + note + "</div>" if note else ""}'
        f'</div>'
        f'<div style="font-size:0.72rem;color:{TEXT_MUTED};min-width:55px;text-align:right">'
        f'{poss_v}<br>poss</div>'
        f'<div style="text-align:right;min-width:90px">'
        f'<div style="font-size:1.0rem;font-weight:700;color:{accent}">{val_s}</div>'
        f'<div style="font-size:0.65rem;color:{TEXT_MUTED}">{main_label}</div>'
        f'</div>'
        f'<div style="text-align:right;min-width:80px">'
        f'<div style="font-size:0.9rem;font-weight:600;color:{TEXT_SECONDARY}">{sval_s}</div>'
        f'<div style="font-size:0.65rem;color:{TEXT_MUTED}">{sub_label}</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


# ── BUY-LOW ───────────────────────────────────────────────────────────────────
with tab_buy:
    st.markdown(
        finding(
            "These players' <strong>process quality (xRAPM) significantly exceeds their observed outcomes (RAPM)</strong>. "
            "The model expects them to be better than their traditional impact metrics suggest. "
            f"Buy-low criterion: RAPM − xRAPM ≤ −{BUY_GAP} and xRAPM ≥ 50th percentile.",
            variant="green",
        ),
        unsafe_allow_html=True,
    )
    if df_buy.empty:
        st.info("No qualifying buy-low candidates this season with current thresholds.")
    else:
        for i, (_, r) in enumerate(df_buy.iterrows(), 1):
            gap_str = f"{float(r['rapm_vs_xrapm']):.2f}" if pd.notna(r.get("rapm_vs_xrapm")) else "—"
            _player_row(
                i, r,
                main_metric="rapm_vs_xrapm", main_fmt="+.2f", main_label="RAPM−xRAPM",
                sub_metric="xrapm",          sub_fmt="+.2f",  sub_label="xRAPM",
                accent=ACCENT_GREEN,
                note=f"xRAPM {float(r['xrapm_pct']):.0f}th pct" if pd.notna(r.get("xrapm_pct")) else "",
            )

# ── SELL-HIGH ─────────────────────────────────────────────────────────────────
with tab_sell:
    st.markdown(
        finding(
            "These players' <strong>outcomes (RAPM) significantly exceed their process quality (xRAPM)</strong>. "
            "The model expects some regression — they are outscoring their process. "
            f"Sell-high criterion: RAPM − xRAPM ≥ +{SELL_GAP} and RAPM ≥ 50th percentile.",
        ),
        unsafe_allow_html=True,
    )
    if df_sell.empty:
        st.info("No qualifying regression candidates this season with current thresholds.")
    else:
        for i, (_, r) in enumerate(df_sell.iterrows(), 1):
            _player_row(
                i, r,
                main_metric="rapm_vs_xrapm", main_fmt="+.2f", main_label="RAPM−xRAPM",
                sub_metric="rapm",           sub_fmt="+.2f",  sub_label="RAPM",
                accent="#EF4444",
                note=f"RAPM {float(r['rapm_pct']):.0f}th pct" if pd.notna(r.get("rapm_pct")) else "",
            )

# ── ELITE PROCESS ─────────────────────────────────────────────────────────────
with tab_elite:
    st.markdown(
        finding(
            f"Players in the <strong>top {100 - ELITE_XRAPM}th percentile for xRAPM</strong> — "
            "elite process quality. Regardless of outcome variance, these players consistently "
            "generate positive expected-value plays.",
            variant="blue",
        ),
        unsafe_allow_html=True,
    )
    for i, (_, r) in enumerate(df_elite.iterrows(), 1):
        _player_row(
            i, r,
            main_metric="xrapm",  main_fmt="+.2f", main_label="xRAPM",
            sub_metric="rapm",    sub_fmt="+.2f",  sub_label="RAPM",
            accent=ACCENT,
            note=f"xRAPM {float(r['xrapm_pct']):.0f}th pct" if pd.notna(r.get("xrapm_pct")) else "",
        )

# ── HIDDEN CONTRIBUTORS ───────────────────────────────────────────────────────
with tab_hidden:
    st.markdown(
        finding(
            f"Players with <strong>strong defensive impact (D-RAPM ≥ {DEFENDER_DRAPM})</strong> "
            f"but modest scoring (<strong>PPG ≤ {DEFENDER_PPG}</strong>). "
            "These players are easy to overlook in box-score analysis but contribute "
            "meaningfully on the defensive end.",
            variant="blue",
        ),
        unsafe_allow_html=True,
    )
    if df_hidden.empty:
        st.info("No qualifying hidden contributors with current thresholds.")
    else:
        for i, (_, r) in enumerate(df_hidden.iterrows(), 1):
            ppg_str = f"{float(r['ppg']):.1f} PPG" if pd.notna(r.get("ppg")) else ""
            _player_row(
                i, r,
                main_metric="d_rapm", main_fmt="+.2f", main_label="D-RAPM",
                sub_metric="xrapm",   sub_fmt="+.2f",  sub_label="xRAPM",
                accent=ACCENT_PURPLE,
                note=ppg_str,
            )

# ── SCATTER MAP ───────────────────────────────────────────────────────────────
with tab_scatter:
    st.markdown("**xRAPM vs RAPM — All Qualifying Players**")
    st.caption(
        "Horizontal axis = process quality (xRAPM). Vertical axis = actual impact (RAPM). "
        "Players above the diagonal are outscoring their process. "
        "Players below are underscoring their process."
    )
    scatter_min = min(float(df["xrapm"].min()), float(df["rapm"].min())) - 0.5
    scatter_max = max(float(df["xrapm"].max()), float(df["rapm"].max())) + 0.5

    gaps = df["rapm_vs_xrapm"].fillna(0).values

    fig_ds = go.Figure()
    fig_ds.add_trace(go.Scatter(
        x=[scatter_min, scatter_max], y=[scatter_min, scatter_max],
        mode="lines", line=dict(color="rgba(200,200,200,0.20)", dash="dot", width=1.5),
        showlegend=False, hoverinfo="skip",
    ))
    fig_ds.add_trace(go.Scatter(
        x=df["xrapm"], y=df["rapm"],
        mode="markers",
        marker=dict(
            color=gaps,
            colorscale=[[0, "#EF4444"], [0.5, "#3F3F46"], [1, "#22C55E"]],
            cmin=-2.5, cmax=2.5,
            size=8, opacity=0.75,
            colorbar=dict(title="RAPM−xRAPM", len=0.7, tickfont=dict(size=10)),
            line=dict(width=0.5, color=BORDER),
        ),
        text=df["full_name"] + " (" + df["team"] + ")",
        hovertemplate=(
            "<b>%{text}</b><br>"
            "xRAPM: %{x:+.2f}<br>"
            "RAPM: %{y:+.2f}<br>"
            "Gap: %{marker.color:+.2f}<extra></extra>"
        ),
    ))
    fig_ds.add_vline(x=0, line_dash="dot", line_color="rgba(200,200,200,0.25)", line_width=1)
    fig_ds.add_hline(y=0, line_dash="dot", line_color="rgba(200,200,200,0.25)", line_width=1)

    fig_ds.update_layout(
        height=500,
        xaxis=dict(title="xRAPM (process quality)", showgrid=True, gridcolor=GRID, zeroline=False),
        yaxis=dict(title="RAPM (actual outcomes)",  showgrid=True, gridcolor=GRID, zeroline=False),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=16, b=20),
        hovermode="closest",
        font=dict(color=TEXT_SECONDARY, size=11),
        hoverlabel=dict(bgcolor="#111114", font_color=TEXT_PRIMARY),
    )
    st.plotly_chart(fig_ds, use_container_width=True, config=MODEBAR, key="ds_scatter")
    st.markdown(
        chart_caption(
            "Green = RAPM > xRAPM (lucky, may regress). "
            "Red = xRAPM > RAPM (unlucky, may improve). "
            "Diagonal = perfect process-outcome alignment."
        ),
        unsafe_allow_html=True,
    )

# ── TRAJECTORIES ─────────────────────────────────────────────────────────────
with tab_trajectory:
    st.markdown("**Biggest Year-Over-Year xRAPM Improvements**")
    st.caption(
        "Most-improved players by xRAPM delta across consecutive seasons. "
        "Improvement in process quality (not just outcomes) is a stronger signal of true development."
    )

    with st.spinner("Loading trajectory data…"):
        try:
            df_traj = get_player_trajectory(season_type, min_poss=300)
        except Exception:
            df_traj = pd.DataFrame()

    if df_traj.empty:
        st.info("Trajectory data unavailable.")
    else:
        df_traj_top = df_traj.head(20)
        for i, (_, r) in enumerate(df_traj_top.iterrows(), 1):
            delta = float(r["xrapm_delta"]) if pd.notna(r.get("xrapm_delta")) else 0
            tcolor = team_color(str(r.get("team", "")))
            delta_color = ACCENT_GREEN if delta > 0 else "#EF4444"

            st.markdown(
                f'<div style="display:flex;align-items:center;gap:12px;'
                f'background:{SURFACE};border:1px solid {BORDER};border-radius:7px;'
                f'padding:9px 14px;margin-bottom:5px">'
                f'<div style="font-size:0.72rem;font-weight:700;color:{TEXT_MUTED};'
                f'min-width:26px;text-align:center">#{i}</div>'
                f'<div style="flex:1">'
                f'<div style="font-size:0.88rem;font-weight:600;color:{TEXT_PRIMARY}">{r["full_name"]}</div>'
                f'<div style="font-size:0.72rem;font-weight:600;color:{tcolor}">{r["team"]}</div>'
                f'<div style="font-size:0.72rem;color:{TEXT_MUTED}">'
                f'{r["season_a"]} → {r["season_b"]}</div>'
                f'</div>'
                f'<div style="text-align:right;min-width:80px">'
                f'<div style="font-size:0.9rem;font-weight:600;color:{TEXT_SECONDARY}">'
                f'{_fmt(r["xrapm_a"], "+.2f")} → {_fmt(r["xrapm_b"], "+.2f")}</div>'
                f'<div style="font-size:0.65rem;color:{TEXT_MUTED}">xRAPM</div>'
                f'</div>'
                f'<div style="text-align:right;min-width:75px">'
                f'<div style="font-size:1.0rem;font-weight:700;color:{delta_color}">'
                f'{delta:+.2f}</div>'
                f'<div style="font-size:0.65rem;color:{TEXT_MUTED}">Δ xRAPM</div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )

        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        st.markdown("**Biggest Year-Over-Year Declines**")
        df_traj_bot = df_traj.tail(15).iloc[::-1]
        for i, (_, r) in enumerate(df_traj_bot.iterrows(), 1):
            delta = float(r["xrapm_delta"]) if pd.notna(r.get("xrapm_delta")) else 0
            tcolor = team_color(str(r.get("team", "")))
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:12px;'
                f'background:{SURFACE};border:1px solid {BORDER};border-radius:7px;'
                f'padding:9px 14px;margin-bottom:5px">'
                f'<div style="font-size:0.72rem;font-weight:700;color:{TEXT_MUTED};'
                f'min-width:26px;text-align:center">#{i}</div>'
                f'<div style="flex:1">'
                f'<div style="font-size:0.88rem;font-weight:600;color:{TEXT_PRIMARY}">{r["full_name"]}</div>'
                f'<div style="font-size:0.72rem;color:{TEXT_MUTED}">'
                f'{r["season_a"]} → {r["season_b"]}</div>'
                f'</div>'
                f'<div style="text-align:right;min-width:80px">'
                f'<div style="font-size:0.9rem;font-weight:600;color:{TEXT_SECONDARY}">'
                f'{_fmt(r["xrapm_a"], "+.2f")} → {_fmt(r["xrapm_b"], "+.2f")}</div>'
                f'</div>'
                f'<div style="text-align:right;min-width:75px">'
                f'<div style="font-size:1.0rem;font-weight:700;color:#EF4444">'
                f'{delta:+.2f}</div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
