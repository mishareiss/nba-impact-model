"""
Lineup Evaluation — actual vs expected net rating for 5-player lineups.

Groups lineup_stints by player combination. Computes:
  - actual net rating (real pts/100 poss margin)
  - expected net rating (xShot-derived pts/100 poss margin)
  - luck = actual - expected (regression/sustainability signal)
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import re
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go

from dashboard.utils.db import get_seasons, get_season_types
from dashboard.utils.queries import (
    get_lineup_leaderboard, get_player_id_name_map,
)
from dashboard.utils.theme import (
    inject_global_css, page_header, section_label, art_section,
    finding, chart_caption, metric_card, metric_row,
    ACCENT, ACCENT_BLUE, ACCENT_GREEN, ACCENT_GOLD,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    SURFACE, BORDER, GRID, ZERO_LINE, MODEBAR,
)

st.set_page_config(
    page_title="Lineup Evaluation · NBA Impact Dashboard",
    page_icon="",
    layout="wide",
)
inject_global_css()

st.markdown(
    page_header(
        "Lineup Evaluation",
        "Compare 5-player lineups' actual net rating against their xShot-expected net rating. "
        "The gap reveals sustainable vs lucky combinations. Positive luck = likely to regress; "
        "negative luck = likely to improve.",
    ),
    unsafe_allow_html=True,
)

st.markdown(
    f'<div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:6px">'
    f'<div style="flex:1;min-width:200px;background:{SURFACE};border:1px solid {BORDER};'
    f'border-radius:7px;padding:12px 14px">'
    f'<div style="font-size:0.72rem;font-weight:700;color:{TEXT_MUTED};'
    f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px">Actual Net Rating</div>'
    f'<div style="font-size:0.82rem;color:{TEXT_SECONDARY};line-height:1.5">'
    f'Points scored minus points allowed per 100 possessions. Includes real outcomes.</div>'
    f'</div>'
    f'<div style="flex:1;min-width:200px;background:{SURFACE};border:1px solid {BORDER};'
    f'border-radius:7px;padding:12px 14px">'
    f'<div style="font-size:0.72rem;font-weight:700;color:{TEXT_MUTED};'
    f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px">Expected Net Rating</div>'
    f'<div style="font-size:0.82rem;color:{TEXT_SECONDARY};line-height:1.5">'
    f'xShot-based expected points margin — measures process quality, not outcomes.</div>'
    f'</div>'
    f'<div style="flex:1;min-width:200px;background:{SURFACE};border:1px solid {BORDER};'
    f'border-left:3px solid {ACCENT_GOLD};border-radius:7px;padding:12px 14px">'
    f'<div style="font-size:0.72rem;font-weight:700;color:{TEXT_MUTED};'
    f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px">Luck = Actual − Expected</div>'
    f'<div style="font-size:0.82rem;color:{TEXT_SECONDARY};line-height:1.5">'
    f'Positive = outscoring process (may regress). Negative = underscoring (may improve).</div>'
    f'</div></div>',
    unsafe_allow_html=True,
)

# ── Filters ───────────────────────────────────────────────────────────────────
f1, f2, f3, f4 = st.columns([2, 2, 1, 1])
seasons      = get_seasons()
def_s        = "2025-26" if "2025-26" in seasons else seasons[0]
season       = f1.selectbox("Season", seasons, index=seasons.index(def_s))
season_type  = f2.selectbox("Season Type", get_season_types())
min_poss     = f3.number_input("Min Possessions", min_value=100, max_value=2000,
                               value=250, step=50)
top_n        = f4.number_input("Show top N", min_value=10, max_value=100,
                               value=30, step=10)

sort_by = st.radio(
    "Sort by",
    ["Actual Net Rating", "Expected Net Rating", "Luck (+ most unsustainable)", "Luck (− most underrated)"],
    horizontal=True,
)

# ── Load data ─────────────────────────────────────────────────────────────────
with st.spinner("Aggregating lineup stints…"):
    df = get_lineup_leaderboard(season, season_type, float(min_poss))

if df.empty:
    st.markdown(
        f'<div style="text-align:center;padding:48px;color:{TEXT_SECONDARY}">'
        f'No lineup data available for this selection. '
        f'Ensure lineup_stints table is populated for {season} {season_type}.</div>',
        unsafe_allow_html=True,
    )
    st.stop()

# ── Player name lookup ────────────────────────────────────────────────────────
id_to_name = get_player_id_name_map()


def _parse_players(player_array_text) -> list[str]:
    """Convert PostgreSQL array text '{1234, 5678}' or a Python list to player names."""
    if player_array_text is None:
        return []
    if isinstance(player_array_text, list):
        ids = [int(x) for x in player_array_text]
    else:
        txt = str(player_array_text).strip("{}")
        if not txt:
            return []
        ids = [int(x.strip()) for x in txt.split(",") if x.strip()]
    return [id_to_name.get(pid, f"#{pid}") for pid in sorted(ids)]


df["player_names"] = df["players"].apply(_parse_players)
df["lineup_display"] = df["player_names"].apply(
    lambda names: " / ".join(n.split()[-1] for n in names)  # last names only for compact view
)
df["lineup_full"] = df["player_names"].apply(lambda names: " · ".join(names))

# ── Player search filter ───────────────────────────────────────────────────────
all_player_names = sorted(
    set(n for names in df["player_names"] for n in names if n)
)
sel_players = st.multiselect(
    "Filter: only show lineups containing these players",
    all_player_names, key="lu_players"
)
if sel_players:
    df = df[df["player_names"].apply(lambda names: all(p in names for p in sel_players))]

# ── Sort ──────────────────────────────────────────────────────────────────────
sort_map = {
    "Actual Net Rating":        ("actual_net_rtg",   False),
    "Expected Net Rating":      ("expected_net_rtg", False),
    "Luck (+ most unsustainable)": ("luck",           False),
    "Luck (− most underrated)": ("luck",              True),
}
sort_col, sort_asc = sort_map[sort_by]
df_sorted = df.sort_values(sort_col, ascending=sort_asc, na_position="last").reset_index(drop=True)
display = df_sorted.head(int(top_n))

# ── Summary KPIs ─────────────────────────────────────────────────────────────
total_lineups = len(df)
avg_actual    = float(df["actual_net_rtg"].mean()) if not df.empty else 0
avg_expected  = float(df["expected_net_rtg"].mean()) if not df.empty else 0

st.markdown(
    metric_row(
        metric_card("Qualifying Lineups",  f"{total_lineups:,}", f"≥{min_poss} poss", ACCENT),
        metric_card("Median Actual NRtg",  f"{float(df['actual_net_rtg'].median()):+.1f}",
                    "pts / 100 poss", ACCENT_BLUE),
        metric_card("Median Expected NRtg", f"{float(df['expected_net_rtg'].median()):+.1f}",
                    "xShot-based", ACCENT_GOLD),
        metric_card("Median Luck",         f"{float(df['luck'].median()):+.1f}",
                    "actual − expected", ACCENT_GREEN),
    ),
    unsafe_allow_html=True,
)

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

# ── Luck scatter ──────────────────────────────────────────────────────────────
st.markdown(art_section("", "Expected vs Actual Net Rating"), unsafe_allow_html=True)
st.caption(
    "Each dot = one lineup. Above the diagonal = outscoring process (luck). "
    "Below diagonal = underperforming process (may improve)."
)

scatter_df = df_sorted.head(min(int(top_n) * 3, 300)).copy()
colors = [ACCENT_GREEN if v > 0 else "#EF4444" for v in scatter_df["luck"]]
diag_range = [
    float(min(scatter_df["expected_net_rtg"].min(), scatter_df["actual_net_rtg"].min())) - 2,
    float(max(scatter_df["expected_net_rtg"].max(), scatter_df["actual_net_rtg"].max())) + 2,
]

fig_scatter = go.Figure()
fig_scatter.add_trace(go.Scatter(
    x=diag_range, y=diag_range,
    mode="lines", line=dict(color=ZERO_LINE, dash="dot", width=1),
    showlegend=False, hoverinfo="skip",
))
fig_scatter.add_trace(go.Scatter(
    x=scatter_df["expected_net_rtg"],
    y=scatter_df["actual_net_rtg"],
    mode="markers",
    marker=dict(
        color=scatter_df["luck"],
        colorscale=[[0, "#EF4444"], [0.5, "#3F3F46"], [1, "#22C55E"]],
        cmin=-10, cmax=10,
        size=np.clip(scatter_df["total_poss"] / 100, 4, 20).tolist(),
        opacity=0.75,
        colorbar=dict(
            title="Luck",
            tickfont=dict(size=10),
            len=0.7,
        ),
        line=dict(width=0.5, color=BORDER),
    ),
    text=scatter_df["lineup_display"],
    hovertemplate=(
        "<b>%{text}</b><br>"
        "Expected: %{x:+.1f}<br>"
        "Actual: %{y:+.1f}<br>"
        "Luck: %{marker.color:+.1f}<extra></extra>"
    ),
))
fig_scatter.update_layout(
    height=420,
    xaxis=dict(title="Expected Net Rating", showgrid=True, gridcolor=GRID, zeroline=False),
    yaxis=dict(title="Actual Net Rating",   showgrid=True, gridcolor=GRID, zeroline=False),
    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=20, r=20, t=16, b=20),
    hovermode="closest",
    font=dict(color=TEXT_SECONDARY, size=11),
    hoverlabel=dict(bgcolor="#111114", font_color=TEXT_PRIMARY),
)
st.plotly_chart(fig_scatter, use_container_width=True, config=MODEBAR, key="lu_scatter")
st.markdown(
    chart_caption(
        "Dot size = lineup possessions. Colour = luck (green = lucky, red = unlucky). "
        "Diagonal line = perfect process-outcome alignment."
    ),
    unsafe_allow_html=True,
)

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

# ── Lineup table ──────────────────────────────────────────────────────────────
st.markdown(art_section("", f"Top {int(top_n)} Lineups — {sort_by}"), unsafe_allow_html=True)

for rank_idx, (_, row) in enumerate(display.iterrows(), start=1):
    actual = float(row["actual_net_rtg"])
    exp    = float(row["expected_net_rtg"])
    luck   = float(row["luck"])
    poss   = float(row["total_poss"])

    actual_col = ACCENT_GREEN if actual > 0 else "#EF4444"
    exp_col    = ACCENT_GOLD
    luck_col   = ACCENT_GREEN if luck > 0 else "#EF4444"

    st.markdown(
        f'<div style="background:{SURFACE};border:1px solid {BORDER};'
        f'border-radius:7px;padding:10px 14px;margin-bottom:6px">'
        f'<div style="display:flex;align-items:flex-start;gap:10px">'
        f'<div style="font-size:0.72rem;font-weight:700;color:{TEXT_MUTED};'
        f'min-width:28px;text-align:center;padding-top:2px">#{rank_idx}</div>'
        f'<div style="flex:1">'
        f'<div style="font-size:0.85rem;font-weight:600;color:{TEXT_PRIMARY};'
        f'margin-bottom:4px">{row["lineup_full"]}</div>'
        f'<div style="font-size:0.72rem;color:{TEXT_SECONDARY}">{poss:.0f} possessions · {int(row["n_stints"])} stints</div>'
        f'</div>'
        f'<div style="display:flex;gap:16px;text-align:right">'
        f'<div>'
        f'<div style="font-size:1.0rem;font-weight:700;color:{actual_col}">{actual:+.1f}</div>'
        f'<div style="font-size:0.65rem;color:{TEXT_SECONDARY};font-weight:700;text-transform:uppercase;letter-spacing:0.05em">Actual</div>'
        f'</div>'
        f'<div>'
        f'<div style="font-size:1.0rem;font-weight:700;color:{exp_col}">{exp:+.1f}</div>'
        f'<div style="font-size:0.65rem;color:{TEXT_SECONDARY};font-weight:700;text-transform:uppercase;letter-spacing:0.05em">Expected</div>'
        f'</div>'
        f'<div>'
        f'<div style="font-size:1.0rem;font-weight:700;color:{luck_col}">{luck:+.1f}</div>'
        f'<div style="font-size:0.65rem;color:{TEXT_SECONDARY};font-weight:700;text-transform:uppercase;letter-spacing:0.05em">Luck</div>'
        f'</div>'
        f'</div></div></div>',
        unsafe_allow_html=True,
    )

with st.expander("Full table (all qualifying lineups)", expanded=False):
    display_df = df_sorted[["lineup_display", "n_stints", "total_poss",
                             "actual_net_rtg", "expected_net_rtg", "luck"]].copy()
    display_df.columns = ["Lineup (last names)", "Stints", "Possessions",
                          "Actual NRtg", "Expected NRtg", "Luck"]
    st.dataframe(
        display_df,
        use_container_width=True, height=520, hide_index=True,
        column_config={
            "Lineup (last names)": st.column_config.TextColumn(width="large"),
            "Stints":              st.column_config.NumberColumn(format="%d",   width="small"),
            "Possessions":         st.column_config.NumberColumn(format="%.0f", width="small"),
            "Actual NRtg":         st.column_config.NumberColumn(format="%+.1f", width="small"),
            "Expected NRtg":       st.column_config.NumberColumn(format="%+.1f", width="small"),
            "Luck":                st.column_config.NumberColumn(format="%+.1f", width="small"),
        },
    )
