"""
Rules-based player archetype classifier.

Phase 1: Threshold-based classification using available metrics.
Phase 2: Replace with UMAP + HDBSCAN cluster-based system using shot profile,
         usage proxies, RAPM splits, and defensive indicators.

Design intent: each archetype should answer the question
  "How would a scout/coach describe this player's role and impact?"

Output is deterministic and interpretable — no black-box classifications.
"""

from __future__ import annotations

import pandas as pd

# ---------------------------------------------------------------------------
# Archetype definitions
# Each entry: (label, icon, hex_color, one-sentence description)
# ---------------------------------------------------------------------------
_ARCHETYPES: dict[str, tuple[str, str, str]] = {
    "Two-Way Star":      ("⭐", "#F4D03F",
                          "Elite impact on both ends — rare transcendent player"),
    "Offensive Anchor":  ("🎯", "#E8462A",
                          "Primary offensive force — high O-RAPM, primary creator"),
    "Shot Creator":      ("🔥", "#E67E22",
                          "Creates and converts difficult shots efficiently"),
    "Elite Finisher":    ("💪", "#2ECC71",
                          "High-percentage interior scorer — elite shot quality at rim"),
    "Floor General":     ("🎪", "#4C9BE8",
                          "High assist playmaker with positive offensive impact"),
    "3-and-D":          ("🛡️", "#1A9E4E",
                          "Defensive anchor who converts open looks above expectation"),
    "Interior Anchor":   ("🏰", "#9B59B6",
                          "Defensive hub — rim protection, rebounding, interior presence"),
    "Playmaking Scorer": ("⚡", "#A569BD",
                          "Scores and creates — balanced offensive threat"),
    "Role Player":       ("👥", "#607D8B",
                          "Positive but modest impact — complementary contributor"),
    "Developing":        ("📈", "#AAB7B8",
                          "Limited two-way data — emerging or limited-minutes player"),
}


def classify(row: "pd.Series | dict") -> dict:
    """
    Classify a player row (from player_career_stats / deduped CTE) into an archetype.

    Parameters
    ----------
    row : Series or dict with keys:
        o_rapm, d_rapm, rapm, xrapm, apg, rpg, spg, bpg, ppg, mpg,
        fg_pct_above_expected, mean_xshot, possessions

    Returns
    -------
    dict with keys: label, icon, color, description, confidence
    """
    def _f(k, default=0.0):
        v = row.get(k) if isinstance(row, dict) else (
            row[k] if k in row.index else None
        )
        if v is None or pd.isna(v):
            return default
        return float(v)

    o_rapm   = _f("o_rapm")
    d_rapm   = _f("d_rapm")
    rapm     = _f("rapm")
    xrapm    = _f("xrapm")
    apg      = _f("apg")
    rpg      = _f("rpg")
    bpg      = _f("bpg")
    ppg      = _f("ppg")
    fge      = _f("fg_pct_above_expected")
    xshot    = _f("mean_xshot", 0.40)
    poss     = _f("possessions", 0)

    # Not enough data to classify meaningfully
    if poss < 500 or (o_rapm == 0 and d_rapm == 0 and rapm == 0):
        label = "Developing"
        return _make(label, "Low possession sample — archetype pending")

    # Two-Way Star: genuinely elite on both ends
    if o_rapm >= 0.8 and d_rapm >= 0.8:
        return _make("Two-Way Star")

    # Offensive Anchor: dominant offensive impact, high usage
    if o_rapm >= 1.0 or (o_rapm >= 0.7 and ppg >= 22):
        if d_rapm < 0.3:
            return _make("Offensive Anchor")
        return _make("Two-Way Star")

    # Floor General: elite playmaking + positive O-RAPM
    if apg >= 7.0 and o_rapm >= 0.3:
        return _make("Floor General")
    if apg >= 8.0:
        return _make("Floor General")

    # Interior Anchor: rim protection + rebounding + defensive value
    if rpg >= 9.0 and (d_rapm >= 0.4 or bpg >= 1.8):
        return _make("Interior Anchor")

    # 3-and-D: positive D-RAPM, shoots well above expected (good shooter)
    if d_rapm >= 0.5 and fge >= 0.01:
        return _make("3-and-D")
    if d_rapm >= 0.4 and fge >= 0.02:
        return _make("3-and-D")

    # Shot Creator: makes difficult shots, high O-RAPM
    if o_rapm >= 0.5 and fge >= 0.015 and xshot >= 0.42:
        return _make("Shot Creator")

    # Elite Finisher: outstanding at-rim efficiency, positive offensive impact
    if fge >= 0.025 and xshot <= 0.42 and o_rapm >= 0.3:
        return _make("Elite Finisher")

    # Playmaking Scorer: balanced
    if apg >= 5.0 and ppg >= 15:
        return _make("Playmaking Scorer")

    # Positive overall impact but doesn't fit a clear role
    if rapm >= 0.5 or xrapm >= 0.5:
        return _make("Role Player")

    # Default
    return _make("Role Player")


def _make(label: str, override_desc: str = "") -> dict:
    icon, color, desc = _ARCHETYPES.get(label, ("?", "#888", "Unknown"))
    return {
        "label": label,
        "icon": icon,
        "color": color,
        "description": override_desc if override_desc else desc,
    }


def stability_flags(row: "pd.Series | dict") -> list[dict]:
    """
    Generate stability / regression / process-vs-results flags for a player row.

    Returns a list of flag dicts: {text, color, help}
    Each flag surfaces a specific analytical concern or noteworthy signal.
    """
    def _f(k, default=0.0):
        v = row.get(k) if isinstance(row, dict) else (
            row[k] if k in row.index else None
        )
        if v is None or pd.isna(v):
            return default
        return float(v)

    rapm  = _f("rapm")
    xrapm = _f("xrapm")
    fge   = _f("fg_pct_above_expected")
    poss  = _f("possessions", 0)

    flags = []

    if poss < 750:
        flags.append({
            "text": "⚠ Small sample",
            "color": "#AAB7B8",
            "help": f"Only {poss:.0f} stint possessions — estimates are noisy",
        })

    gap = rapm - xrapm
    if gap > 0.8:
        flags.append({
            "text": "🔺 Outperforming process",
            "color": "#E67E22",
            "help": (
                f"RAPM ({rapm:+.2f}) is {gap:.2f} pts/100 above xRAPM ({xrapm:+.2f}). "
                "Actual outcomes better than shot quality suggests — possible regression risk."
            ),
        })
    elif gap < -0.8:
        flags.append({
            "text": "🔻 Underperforming process",
            "color": "#4C9BE8",
            "help": (
                f"xRAPM ({xrapm:+.2f}) is {abs(gap):.2f} pts/100 above RAPM ({rapm:+.2f}). "
                "Shot quality better than outcomes — possible positive regression candidate."
            ),
        })

    if fge > 0.04:
        flags.append({
            "text": "🎯 Elite shot-maker",
            "color": "#1A9E4E",
            "help": f"FG% is {fge*100:+.1f}pp above model expectation — elite conversion ability",
        })
    elif fge < -0.04:
        flags.append({
            "text": "📉 Shot-making drag",
            "color": "#E74C3C",
            "help": f"FG% is {fge*100:.1f}pp below model expectation — converting shots below difficulty expectation",
        })

    return flags
