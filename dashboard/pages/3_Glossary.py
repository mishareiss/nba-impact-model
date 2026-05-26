"""
Glossary page: plain-English explanations of every metric in the dashboard.
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st

st.set_page_config(page_title="Glossary · NBA Impact", page_icon="📖", layout="wide")
st.title("📖 Glossary")
st.caption(
    "Plain-English definitions for every metric used in this dashboard. "
    "Most metrics are process-based — they attempt to measure *quality of play* "
    "rather than raw outcomes, which are more stable and predictive than one-season results."
)

# ── Shot Quality ──────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Shot Quality Metrics")

with st.expander("**xShot** — Expected Shot Value", expanded=True):
    st.markdown("""
**What it is:**  
The model-predicted probability that any given field goal attempt is made, given only
pre-shot information: shot location, shot type (dunk, layup, pull-up jump shot, etc.),
and game context. Analogous to *expected goals (xG)* in soccer.

**Range:** 0.0 – 1.0 (but typically 0.30 – 0.95 for non-dunks)

**Examples:**
- Dunk from the restricted area → ~0.95
- Open corner 3 → ~0.40
- Contested mid-range fadeaway → ~0.32

**Why it matters:**  
Raw FG% mixes shot selection with shot-making ability. xShot separates them.
A player who only attempts layups will have a high FG% regardless of skill.
A player who consistently drains difficult pull-up jumpers is more impressive even
if their raw FG% is similar. xShot provides the context to make that distinction.

**Limitation:** The model has no information about shot contest level (defender proximity).
A wide-open 3 and a heavily contested 3 receive the same xShot if taken from the same location.
    """)

with st.expander("**Mean xShot (Avg Shot Quality)** — Shot Difficulty Profile"):
    st.markdown("""
**What it is:**  
The average xShot value across all of a player's or team's field goal attempts.

**Interpretation:**
- **Higher** = taking more difficult shots (pull-up jumpers, long 2s, contested attempts)
- **Lower** = taking higher-percentage shots (layups, dunks, spot-up 3s with good spacing)

**Important:** Mean xShot alone does *not* tell you if a player is good or bad.
It measures shot difficulty, not shot-making. A player could have a high mean xShot
because they're a volume pull-up shooter, or because their team forces them into tough looks.

**Use it together with FG% vs Expected** to understand the full picture:
a player with high mean xShot and positive FG% vs Expected is both taking and converting difficult shots.
    """)

with st.expander("**FG% vs Expected (SMOE)** — Shot-Making Over Expected"):
    st.markdown("""
**What it is:**  
The difference between a player's actual field goal percentage and their model-predicted
field goal percentage given the shots they actually attempted.

```
FG% vs Expected = Actual FG% − Average xShot for that player's attempts
```

**Interpretation:**
- **Positive** = consistently makes harder shots than the model predicts. Elite shot-makers.
- **Negative** = underperforms the expected value of their own shot attempts.
- **Near zero** = makes shots at exactly the difficulty-adjusted expectation.

**Examples (2025-26 Regular Season):**
- Nikola Jokić: ~+0.115 — converts at far above expected on all shot types
- Elite finishers and shooters consistently positive year-over-year

**Limitation:** This metric can be noisy over small samples (<100 attempts).
Over a full season (500+ attempts) it becomes meaningful.

**Why "SMOE"?** Shot-Making Over Expected — the analogue to xG overperformance in soccer.
    """)

with st.expander("**Points Above Expected** — Volume-Adjusted Shot Quality"):
    st.markdown("""
**What it is:**  
Total points scored above (or below) xShot expectation for the season.

```
Points Above Expected = Σ (shot_made × shot_value) − Σ xshot_points
```

where `xshot_points = xshot × shot_value` for each attempt.

**Interpretation:**
- Positive = scored more than the model predicted based on shot difficulty
- Negative = scored less than expected

**Why it differs from FG% vs Expected:**  
FG% vs Expected is a *per-shot rate* — it tells you the quality of each attempt.
Points Above Expected is a *volume metric* — it combines rate with the number of attempts.
A player who takes 1,000 shots per season with +0.05 FG% vs Expected accumulates
far more Points Above Expected than a player who takes 200 shots at the same rate.

**Use case:** Identifying high-volume, high-efficiency scorers. Elite season-long contributors
will rank high on both metrics.
    """)

# ── Player Impact ─────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Player Impact Metrics (RAPM Family)")

with st.expander("**RAPM** — Regularized Adjusted Plus-Minus", expanded=True):
    st.markdown("""
**What it is:**  
A player's estimated marginal contribution to their team's scoring margin per 100 possessions,
after statistically controlling for every teammate and every opponent on the floor.

**How it's calculated (simplified):**  
Every game is broken into lineup *stints* — periods where both 5-player lineups are unchanged.
Ridge regression fits coefficients for every player to explain the observed scoring margin
across all stints, simultaneously accounting for the quality of teammates and opponents.

**Units:** Points per 100 possessions (relative to a league-average player)

**Scale examples:**
| Value | Meaning |
|-------|---------|
| +3.0 | All-NBA level — dominant impact |
| +1.5 | All-Star caliber |
| +0.5 | Quality starter |
| 0.0 | Replacement-level |
| −1.0 | Negative impact when on court |

**Why "Regularized"?**  
Players who share a lot of court time (e.g., star-laden teams) have correlated estimates.
Ridge regression penalizes extreme values, shrinking role player estimates toward average
and reducing the inflation caused by being on a great team.

**Limitation:**  
Single-season RAPM can still be noisy for players who are injured, traded mid-season,
or play in limited lineup variety. The v2 pooled model addresses this.
    """)

with st.expander("**xRAPM** — Expected RAPM"):
    st.markdown("""
**What it is:**  
The same ridge regression as RAPM, but using **expected points** (xShot × shot value)
instead of **actual points** scored.

**Why use it?**  
Actual points include shooting variance — hot and cold stretches, lucky bounces, clutch
makes or misses. Over a single season, a player might outperform or underperform their
expected point production significantly.

xRAPM measures the *quality of opportunities created and allowed* rather than outcomes.
It is:
- **More stable** season-to-season
- **Better for evaluating process-based play** (spacing, cutting, defensive positioning)
- **Less reactive to shooting streaks**

**When RAPM > xRAPM:**  
The player is outscoring their process — excellent at converting high-leverage moments,
free throw drawing, clutch shot-making. Suggests elite finishing ability.

**When xRAPM > RAPM:**  
The process is better than outcomes — good decision-making but may be finishing below
expected value. This could indicate variance, tough luck, or limited finishing ability.

**Typical range:** −2.0 to +2.0 in single-season; −1.0 to +1.5 for most players
    """)

with st.expander("**RAPM − xRAPM** — Outcome vs Process Gap"):
    st.markdown("""
**What it is:**  
The numerical gap between a player's actual RAPM and their xRAPM.

**Interpretation:**
- **Large positive** (>+0.5): Outscores expected lineup margins significantly.
  Could indicate elite finishing, free throw volume, or clutch performance.
- **Near zero** (±0.2): Consistent player whose outcomes match their process.
- **Large negative** (<−0.5): Generates good shots but struggles to convert.
  May be an inefficient finisher or one subject to bad variance.

**Analyst note:**  
Use this as a *stability flag*. A player with a large positive RAPM-xRAPM gap
may regress toward their xRAPM in future seasons — outcomes normalize to process over time.
    """)

with st.expander("**RAPM+Prior (v2)** — Multi-Year Pooled RAPM with Box-Score Prior"):
    st.markdown("""
**What it is:**  
A refined player impact estimate from the v2 model that addresses two core limitations
of single-season RAPM:

1. **Multi-year pooling:** Stints are pooled across 3 rolling seasons, tripling the data
   available per player and reducing lineup collinearity.

2. **Box-score prior:** Each player's estimate is shrunk toward a prior derived from their
   historical plus/minus baseline (`γ = (plus_minus / min) × 48 × 0.12`, centered to mean 0).
   This anchors noisy estimates and correctly elevates star players whose impact is
   independently measurable through traditional stats.

**Why it's the recommended metric:**
- Less sensitive to single-season lineup luck
- Correctly distinguishes stars on winning teams from role players riding their coattails
- Better for cross-season comparisons

**Trade-off:** Because it pools 3 seasons, it reflects a player's *average* over that window,
not their peak or decline in the most recent year alone. For current-season analysis,
combine it with single-season RAPM.

**Limitation:** Prior scale is era-dependent. A +1.0 box-score plus/minus in a high-pace,
high-scoring era differs from the same number in a slower era.
    """)

# ── Traditional Stats ─────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Traditional Stats (As Used in This Dashboard)")

with st.expander("**GP, PPG, RPG, APG, MPG** — Per-Game Box Score"):
    st.markdown("""
All counting stats in this dashboard are **per game** (not season totals).

| Label | Full Name | Notes |
|-------|-----------|-------|
| GP | Games Played | Total games in the season |
| PPG | Points Per Game | Total season points ÷ GP |
| RPG | Rebounds Per Game | |
| APG | Assists Per Game | |
| SPG | Steals Per Game | |
| BPG | Blocks Per Game | |
| MPG | Minutes Per Game | Total season minutes ÷ GP |
| +/- | Season Plus-Minus | Raw cumulative +/- (not per-game) |

**Note:** The raw season plus-minus (+/-) in the stats table is the *total* for the season,
not per-game. A player who plays 80 games will naturally accumulate a larger absolute +/-
than a player who plays 40 games, even at the same per-game impact. For impact comparison,
use RAPM, which normalizes by possession count and controls for teammate quality.
    """)

with st.expander("**Possessions (Stint Poss)** — RAPM Sample Size"):
    st.markdown("""
**What it is:**  
The total number of possessions tracked across lineup stints for a given player.
Used as the denominator in RAPM calculation.

Possessions ≈ FGA + 0.44 × FTA + Turnovers (per team per stint)

**Why it matters:**  
RAPM estimates are only shown for players with ≥1,000 stint possessions (v1)
or ≥2,000 pooled possessions (v2). Below this threshold, estimates are
too noisy to be meaningful.

A player with 3,000+ possessions has a highly stable RAPM estimate.
A player with exactly 1,000 possessions is at the minimum reliable threshold.
    """)

# ── Analytical Notes ──────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Analytical Notes for Practitioners")

with st.expander("Why process metrics beat box scores for prediction"):
    st.markdown("""
Traditional box score stats (PTS, REB, AST) are strongly influenced by:
- **Role and usage** — a high-usage player will score more regardless of efficiency
- **Team context** — good teams create better opportunities for all players
- **Scheme** — a team that plays slow pace will have fewer counting stats across the board
- **Variance** — a single hot shooting stretch can inflate a player's season average

Process-based metrics like xShot and xRAPM are designed to be more stable:
- **xShot** controls for shot selection by evaluating each attempt on its own difficulty
- **xRAPM** controls for teammates and opponents via the ridge regression framework
- **RAPM+Prior** reduces the noise from single-season lineup collinearity

**Empirical finding:** xRAPM is more stable year-over-year than raw RAPM.
RAPM+Prior (v2) is more stable than either single-season variant.
For predicting next-season performance, process metrics should be weighted more heavily.
    """)

with st.expander("Understanding the relationship between xRAPM and RAPM"):
    st.markdown("""
Think of a player's impact as having two components:

1. **Process component** — the quality of shots they help generate (offense) and prevent (defense).
   Captured by xRAPM.

2. **Execution component** — how much the team outscores expected margins when that player is on court.
   The gap (RAPM − xRAPM) reflects execution above process.

**Interpretation guide for analysts:**

| Scenario | Likely Interpretation |
|----------|----------------------|
| High RAPM, High xRAPM | Genuinely elite — both process and outcomes are outstanding |
| High RAPM, Low xRAPM | High variance season — may regress. Check if shooting rates are unusually high |
| Low RAPM, High xRAPM | Unlucky season or poor finishing — process is better than results suggest |
| Low RAPM, Low xRAPM | Genuinely below-average impact. Consistent across both measures |

The most reliable assessment uses all three: RAPM, xRAPM, and RAPM+Prior.
When all three agree, the signal is strong. When they diverge significantly,
look for context (injuries, role changes, team changes, shooting variance).
    """)

with st.expander("Known limitations of this system"):
    st.markdown("""
1. **No defender context in xShot.** Shot contest level is not available from play-by-play data.
   A wide-open 3 and a heavily contested 3 from the same spot receive the same xShot.

2. **RAPM collinearity on dominant teams.** When 4-5 players on a great team all share most
   of their court time together, ridge regression cannot fully separate their individual contributions.
   The 2016-17 Warriors are the extreme case — Curry, Durant, Green, Thompson, and Iguodala
   all appear in the top 5 of any pooled window that includes that season.

3. **Stints are only as good as the substitution parsing.** Lineup stints are derived from
   play-by-play substitution events. Occasional data errors in the source data may create
   slightly incorrect lineups. Validation shows 96%+ of stints have valid 5-player lineups.

4. **Era drift.** The NBA has changed significantly since 2014-15 (3-point revolution, pace,
   rule changes). Models trained across all seasons absorb era-level shifts as noise.

5. **Rookies and limited-sample players.** Players with fewer than 1,000 stint possessions
   do not appear in the RAPM leaderboard. This excludes rookies and injury-limited veterans
   who may be genuinely impactful.
    """)
