"""
Glossary — definitions for all metrics and concepts used in this dashboard.
Written for basketball decision-makers, not statisticians.
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st

from dashboard.utils.theme import (
    inject_global_css, page_header, section_label,
    ACCENT, ACCENT_BLUE, ACCENT_GREEN, ACCENT_GOLD, ACCENT_PURPLE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, SURFACE, BORDER,
)

st.set_page_config(
    page_title="Glossary · NBA Impact Dashboard",
    page_icon="",
    layout="wide",
)
inject_global_css()

st.markdown(
    page_header(
        "Glossary",
        "Definitions for all metrics, terms, and concepts used in this dashboard. "
        "Written for basketball decision-makers.",
    ),
    unsafe_allow_html=True,
)


def term_card(term: str, definition: str, example: str = "", accent: str = ACCENT) -> None:
    ex_html = (
        f'<div style="font-size:0.78rem;color:{ACCENT_GREEN};margin-top:6px;'
        f'font-style:italic">{example}</div>'
    ) if example else ""
    st.markdown(
        f'<div style="background:{SURFACE};border:1px solid {BORDER};'
        f'border-left:3px solid {accent};border-radius:8px;padding:14px 18px;margin-bottom:8px">'
        f'<div style="font-size:0.95rem;font-weight:700;color:{TEXT_PRIMARY};'
        f'margin-bottom:6px">{term}</div>'
        f'<div style="font-size:0.85rem;color:{TEXT_SECONDARY};line-height:1.6">{definition}</div>'
        f'{ex_html}</div>',
        unsafe_allow_html=True,
    )


# ── CORE MODEL METRICS ────────────────────────────────────────────────────────
st.markdown(section_label("Core Model Metrics"), unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    term_card(
        "xShot",
        "The model-predicted probability that a specific field goal attempt will be made, "
        "given only pre-shot observable information: shot location (x/y coordinates, zone, distance), "
        "shot type (dunk, layup, pull-up, etc.), game clock, period, and playoff indicator. "
        "xShot does not know who is shooting — it measures <strong>shot difficulty</strong>, not shooter quality.",
        "Example: A corner three from 22 feet might have xShot = 0.38. "
        "A layup at the rim might have xShot = 0.62.",
        ACCENT,
    )
    term_card(
        "Shot Quality",
        "A general term for the expected value of a shot attempt based on its difficulty. "
        "High shot quality = high xShot (easier shot). Low shot quality = low xShot (harder shot). "
        "A team that generates high-quality shots creates more expected points per possession.",
        "",
        ACCENT,
    )
    term_card(
        "FG% Above Expected (SMOE)",
        "A player's actual field goal percentage minus their average xShot across all attempts. "
        "Positive values indicate the player converts shots at above-model-expectation rates — "
        "isolating shot-making skill from shot selection. "
        "Analogous to batting average on balls in play (BABIP) in baseball.",
        "Example: A player with actual FG% = 0.52 and avg xShot = 0.48 has FG% Above Expected = +0.040.",
        ACCENT_GREEN,
    )
    term_card(
        "Points Above Expected",
        "The cumulative season total of points scored above xShot expectation: "
        "Σ(made − xshot) × shot_value. Positive = scored more than expected "
        "given shot selection. Large totals indicate either elite finishing or aggressive shot volume.",
        "",
        ACCENT_GREEN,
    )

with col2:
    term_card(
        "RAPM (Regularised Adjusted Plus-Minus)",
        "A player's marginal contribution to team scoring margin per 100 possessions, "
        "estimated via Ridge regression over lineup stints. Measures <em>actual outcomes</em> — "
        "real points scored and allowed. Controls simultaneously for all teammates and opponents "
        "on the court. Value of 0.0 = exactly league-average contribution.",
        "Example: RAPM = +2.5 means the lineup is 2.5 pts/100 better with this player than average.",
        ACCENT_GOLD,
    )
    term_card(
        "xRAPM (Expected RAPM)",
        "Same Ridge regression as RAPM, but the target is <em>expected</em> scoring margin "
        "derived from xShot predictions instead of actual makes and misses. "
        "Removes shot-making variance and measures <strong>process quality</strong>. "
        "More stable year-to-year than RAPM.",
        "Example: xRAPM = +2.0 but RAPM = +3.5 suggests outscoring the process — "
        "possible variance that may regress.",
        ACCENT,
    )
    term_card(
        "RAPM − xRAPM (Process Gap)",
        "The difference between actual outcomes and process quality. "
        "<strong>Positive gap:</strong> player is outscoring their process — "
        "either elite shot-making or positive variance (watch for regression). "
        "<strong>Negative gap:</strong> process is better than outcomes — "
        "positive regression candidate.",
        "",
        "#71717A",
    )
    term_card(
        "RAPM+Prior (Pooled v2)",
        "A 3-year rolling window RAPM anchored toward a box-score prior "
        "(per-minute plus/minus × 0.12). Reduces single-season collinearity noise "
        "by pooling more stints per player. <strong>Recommended metric for comparing players.</strong>",
        "",
        ACCENT_GOLD,
    )

# ── IMPACT COMPONENTS ─────────────────────────────────────────────────────────
st.markdown(section_label("Impact Components"), unsafe_allow_html=True)

col3, col4 = st.columns(2)

with col3:
    term_card(
        "O-RAPM (Offensive RAPM)",
        "The offensive component of RAPM. Estimates how many points per 100 possessions "
        "a player's lineup scores above average when this player is on the court, "
        "controlling for opponents and teammates. Derived from a separate offensive-only regression.",
        "",
        ACCENT_BLUE,
    )
    term_card(
        "D-RAPM (Defensive RAPM)",
        "The defensive component of RAPM. Positive values = better than average defense "
        "(suppressing opponent scoring). Derived from a negated defensive regression. "
        "D-RAPM is harder to estimate reliably than O-RAPM due to smaller individual effects.",
        "",
        ACCENT_PURPLE,
    )

with col4:
    term_card(
        "Avg Shot Difficulty (mean xShot)",
        "A player's average xShot value across all their field goal attempts. "
        "Higher = takes harder shots on average. A player with mean xShot of 0.55 "
        "takes mostly at-rim looks; one with 0.35 takes mostly perimeter shots.",
        "",
        ACCENT_GOLD,
    )
    term_card(
        "Stint Possessions",
        "Total possessions in 5v5 lineup stints where this player participated. "
        "Used as the minimum qualification threshold for RAPM estimates. "
        "Below 1,000 (single-season) or 2,000 (pooled), ridge bias dominates and estimates are not published.",
        "",
        "#3F3F46",
    )

# ── CORE CONCEPTS ─────────────────────────────────────────────────────────────
st.markdown(section_label("Core Concepts"), unsafe_allow_html=True)

col5, col6 = st.columns(2)

with col5:
    term_card(
        "Possession",
        "A possession begins when a team gains control of the ball and ends when they "
        "lose control (via a field goal, turnover, or end of shot clock). "
        "For RAPM, possessions are estimated using the formula: "
        "FGA + 0.44 × FTA + TOV. This is the standard NBA approximation.",
        "",
        "#4B5563",
    )
    term_card(
        "Net Rating",
        "Points scored minus points allowed per 100 possessions. "
        "A positive net rating means a team (or lineup) is outscoring opponents. "
        "RAPM estimates each player's marginal contribution to their lineup's net rating.",
        "",
        "#4B5563",
    )
    term_card(
        "Lineup Stint",
        "Any contiguous period of play during which both 5-player lineups remained unchanged. "
        "Stints end when any player on either team is substituted. "
        "The RAPM regression is built from 421,849 such stints across 12 seasons.",
        "",
        "#4B5563",
    )

with col6:
    term_card(
        "Percentile",
        "Where a player ranks relative to all other qualifying players for a given metric. "
        "The 90th percentile means the player scores higher than 90% of qualifying players. "
        "Percentiles in this dashboard are computed against players with ≥500 possessions in the same season.",
        "",
        "#4B5563",
    )
    term_card(
        "Regularisation (Ridge / L2)",
        "A mathematical technique that prevents overfitting by shrinking model coefficients "
        "toward zero. In RAPM, it handles the collinearity problem: "
        "teammates always appear together, making it hard to separate individual contributions. "
        "Ridge shrinks uncertain estimates toward zero rather than producing extreme values. "
        "λ controls the strength of shrinkage — higher λ = more conservative estimates.",
        "",
        "#4B5563",
    )
    term_card(
        "Process vs Outcomes",
        "A framework for separating what a player <em>did</em> (outcomes) from the "
        "<em>quality of their decisions</em> (process). "
        "RAPM measures outcomes. xRAPM measures process. "
        "The gap between them reveals variance — short-term luck vs sustainable performance.",
        "",
        "#4B5563",
    )
