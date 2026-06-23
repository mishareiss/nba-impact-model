"""
Daily Stat Challenge — 3-strikes Wordle-style game.

Mechanics:
  - 5 ranked slots shown at all times. Correct ranks are hidden until guessed.
  - One guess at a time. Immediate feedback.
  - Correct guess → fills that player's actual rank slot with their stat value.
  - Wrong guess → strike consumed, player added to wrong-guesses list.
  - Already guessed → friendly warning, no strike consumed.
  - Game ends when: all 5 slots filled (WIN) or 3 strikes reached (LOSS).
  - Help popup via st.dialog (not a dropdown/expander).
  - Deterministic daily seed: same challenge for everyone on the same day.
  - State persists within-session via date-keyed session_state.
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]  # repo root
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import hashlib
import json
from datetime import date

import pandas as pd
import streamlit as st
from streamlit_javascript import st_javascript

from game.utils.queries import get_daily_challenge_stats
from game.utils.theme import (
    inject_global_css, page_header,
    ACCENT, ACCENT_GREEN, ACCENT_GOLD,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED, SURFACE, BORDER,
)

st.set_page_config(
    page_title="Daily Stat Challenge · NBA Impact Dashboard",
    page_icon="",
    layout="centered",
)
inject_global_css()

# ── Additional game-specific CSS ───────────────────────────────────────────────
st.markdown("""
<style>
/* Slot rows */
.slot-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    border-radius: 8px;
    margin-bottom: 6px;
    border: 1px solid;
    transition: background 0.2s;
}
.slot-row.found {
    background: rgba(34, 197, 94, 0.08);
    border-color: rgba(34, 197, 94, 0.40);
}
.slot-row.empty {
    background: rgba(255,255,255,0.02);
    border-color: #27272A;
}
.slot-rank {
    font-size: 0.88rem;
    font-weight: 700;
    color: #60A5FA;
    min-width: 28px;
}
.slot-name {
    flex: 1;
    font-size: 1.0rem;
    font-weight: 600;
    color: #FAFAFA;
}
.slot-placeholder {
    flex: 1;
    font-size: 0.88rem;
    color: #A1A1AA;
    letter-spacing: 0.08em;
}
.slot-value {
    font-size: 1.0rem;
    font-weight: 700;
    color: #FAFAFA;
}
.slot-unit {
    font-size: 0.72rem;
    color: #A1A1AA;
    margin-left: 5px;
}
/* Strike display */
.strike-pip {
    display: inline-block;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    margin: 0 3px;
}
.strike-used   { background: #EF4444; }
.strike-unused { background: #27272A; border: 2px solid #3F3F46; }
/* Wrong guesses */
.wrong-guess {
    display: inline-block;
    background: rgba(239,68,68,0.08);
    border: 1px solid rgba(239,68,68,0.25);
    border-radius: 4px;
    padding: 3px 9px;
    font-size: 0.82rem;
    color: #EF4444;
    margin: 2px 3px;
    text-decoration: line-through;
}
/* Pulse animation for just-found slots */
@keyframes pop {
    0%   { transform: scale(1); }
    40%  { transform: scale(1.04); }
    100% { transform: scale(1); }
}
.slot-row.just-found {
    animation: pop 0.3s ease-out;
}
</style>
""", unsafe_allow_html=True)

# ── Stat category registry ─────────────────────────────────────────────────────
# (col, display_name, short_label, format, min_qualifier_label, attempt_col, attempt_min)
# attempt_col / attempt_min: if set, _load_top5 further filters on that column >= min
BASE_QUAL = "≥50 GP, ≥15 MPG"
STAT_CATEGORIES = [
    ("ppg",      "Points Per Game",         "PPG",   ".1f", BASE_QUAL,              None,       None),
    ("rpg",      "Rebounds Per Game",        "RPG",   ".1f", BASE_QUAL,              None,       None),
    ("apg",      "Assists Per Game",         "APG",   ".1f", BASE_QUAL,              None,       None),
    ("spg",      "Steals Per Game",          "SPG",   ".1f", BASE_QUAL,              None,       None),
    ("bpg",      "Blocks Per Game",          "BPG",   ".1f", BASE_QUAL,              None,       None),
    ("fg3m_pg",  "3-Pointers Made Per Game", "3PM/G", ".1f", BASE_QUAL + ", ≥2 3PA/G", "fg3a_pg", 2.0),
    ("fg_pct",   "Field Goal %",             "FG%",   ".3f", BASE_QUAL + ", ≥5 FGA/G", "fga_pg",  5.0),
    ("fg3_pct",  "3-Point %",               "3P%",   ".3f", BASE_QUAL + ", ≥3 3PA/G", "fg3a_pg", 3.0),
    ("ft_pct",   "Free Throw %",             "FT%",   ".3f", BASE_QUAL + ", ≥3 FTA/G", "fta_pg",  3.0),
    ("tpg",      "Turnovers Per Game",       "TOV/G", ".1f", BASE_QUAL,              None,       None),
    ("pts_total","Total Points",             "PTS",   ".0f", BASE_QUAL,              None,       None),
    ("fga_pg",   "FGA Per Game",             "FGA/G", ".1f", BASE_QUAL,              None,       None),
    ("orpg",     "Offensive Rebounds/G",     "OREB/G",".1f", BASE_QUAL,              None,       None),
    ("drpg",     "Defensive Rebounds/G",     "DREB/G",".1f", BASE_QUAL,              None,       None),
]

AVAILABLE_SEASONS = [
    "2014-15","2015-16","2016-17","2017-18","2018-19",
    "2019-20","2020-21","2021-22","2022-23","2023-24","2024-25","2025-26",
]

TOP_N   = 5
STRIKES = 3


def _daily_seed(d: date) -> int:
    return int(hashlib.sha256(d.strftime("%Y%m%d").encode()).hexdigest(), 16) % (10**12)


def _get_challenge(d: date) -> dict:
    seed       = _daily_seed(d)
    season_idx = seed % len(AVAILABLE_SEASONS)
    cat_idx    = (seed // len(AVAILABLE_SEASONS)) % len(STAT_CATEGORIES)
    season     = AVAILABLE_SEASONS[season_idx]
    col, full, short, fmt, min_lbl, attempt_col, attempt_min = STAT_CATEGORIES[cat_idx]
    return {
        "date": d, "season": season,
        "col": col, "full_name": full, "short": short, "fmt": fmt,
        "min_label": min_lbl,
        "attempt_col": attempt_col, "attempt_min": attempt_min,
    }


def _fmtv(v, spec: str) -> str:
    try:
        return f"{float(v):{spec}}"
    except (TypeError, ValueError):
        return "—"


# ── Today's challenge ──────────────────────────────────────────────────────────
today  = date.today()
ch     = _get_challenge(today)
sk     = f"dc_{today.strftime('%Y%m%d')}_"   # session-state key prefix
LS_KEY = f"nba_challenge_{today.strftime('%Y%m%d')}"


# ── localStorage restore (runs before defaults so saved state wins) ────────────
# st_javascript returns integer 0 on its very first call (JS hasn't executed yet).
# The real localStorage value arrives on the next rerun as a string.
# We track two flags:
#   LS_READ_DONE  — localStorage read has completed (string returned, not 0)
#   LS_LOADED     — state has been restored (or confirmed empty) from localStorage
LS_LOADED    = f"{sk}ls_loaded"
LS_READ_DONE = f"{sk}ls_read_done"
_ls_raw = st_javascript(f'localStorage.getItem("{LS_KEY}") || ""', key="ls_read")

_ls_read_complete = isinstance(_ls_raw, str)  # 0 (int) on first call → not done yet

if _ls_read_complete and LS_LOADED not in st.session_state:
    if len(_ls_raw) > 2:
        try:
            _saved = json.loads(_ls_raw)
            for _k, _v in _saved.items():
                st.session_state[_k] = _v
        except Exception:
            pass
    # Mark done regardless of whether there was saved data
    st.session_state[LS_LOADED]    = True
    st.session_state[LS_READ_DONE] = True


# ── Session state defaults (skipped for keys already restored) ─────────────────
defaults = {
    f"{sk}slots":       [None] * TOP_N,   # None or player name at that rank
    f"{sk}strikes":     0,
    f"{sk}wrong":       [],               # wrong guesses (player names)
    f"{sk}all_guesses": [],               # every guess in order
    f"{sk}game_over":   False,
    f"{sk}win":         False,
    f"{sk}last_result": None,             # "correct" | "wrong" | "duplicate"
    f"{sk}last_guess":  "",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

slots       = st.session_state[f"{sk}slots"]
strikes     = st.session_state[f"{sk}strikes"]
wrong       = st.session_state[f"{sk}wrong"]
all_guesses = st.session_state[f"{sk}all_guesses"]
game_over   = st.session_state[f"{sk}game_over"]
win         = st.session_state[f"{sk}win"]
last_result = st.session_state[f"{sk}last_result"]
last_guess  = st.session_state[f"{sk}last_guess"]


# ── Load challenge data ────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def _load_top5(
    season: str, col: str,
    attempt_col: str | None = None,
    attempt_min: float | None = None,
) -> pd.DataFrame:
    """Return the top-5 players for *col* after applying all qualifier filters."""
    df = get_daily_challenge_stats(season)
    if df.empty or col not in df.columns:
        return pd.DataFrame()
    # Per-stat attempt minimum (for shooting %)
    if attempt_col and attempt_min is not None and attempt_col in df.columns:
        df = df[df[attempt_col] >= attempt_min]
    keep_cols = ["full_name", col, "gp", "mpg"]
    # Also keep the attempt column in output so the help modal can show it
    if attempt_col and attempt_col in df.columns:
        keep_cols.append(attempt_col)
    return (
        df.sort_values(col, ascending=False, na_position="last")
        .head(TOP_N)[keep_cols]
        .reset_index(drop=True)
    )


@st.cache_data(ttl=3600)
def _all_players(season: str) -> list[str]:
    df = get_daily_challenge_stats(season)
    return sorted(df["full_name"].dropna().tolist()) if not df.empty else []


@st.cache_data(ttl=3600)
def _stat_lookup(
    season: str, col: str,
    attempt_col: str | None = None,
    attempt_min: float | None = None,
) -> dict[str, str]:
    """Map every qualifying player name → formatted stat value for *col*."""
    df = get_daily_challenge_stats(season)
    if df.empty or col not in df.columns:
        return {}
    if attempt_col and attempt_min is not None and attempt_col in df.columns:
        df = df[df[attempt_col] >= attempt_min]
    fmt = next(
        (c[3] for c in STAT_CATEGORIES if c[0] == col), ".1f"
    )
    return {
        row["full_name"]: _fmtv(row[col], fmt)
        for _, row in df[["full_name", col]].iterrows()
        if pd.notna(row[col])
    }


with st.spinner("Loading today's challenge…"):
    df_top5     = _load_top5(
        ch["season"], ch["col"],
        attempt_col=ch.get("attempt_col"),
        attempt_min=ch.get("attempt_min"),
    )
    player_pool = _all_players(ch["season"])
    lookup      = _stat_lookup(
        ch["season"], ch["col"],
        attempt_col=ch.get("attempt_col"),
        attempt_min=ch.get("attempt_min"),
    )

if df_top5.empty:
    st.warning(
        f"No data for {ch['season']} — {ch['full_name']}. "
        "Ensure ingestion has run for this season."
    )
    st.stop()

answer = df_top5["full_name"].tolist()   # rank order [rank1, rank2, ..., rank5]


# ── HELP DIALOG ───────────────────────────────────────────────────────────────
@st.dialog("How to Play")
def show_help():
    st.markdown("""
**Goal:** Guess all 5 players who led the NBA in the day's stat category.

---

**How it works**
1. Type or select a player name from the dropdown and press **Guess**.
2. If the player is **anywhere in the Top 5**, their correct rank slot is revealed with their stat value. ✅
3. If the player is **not in the Top 5**, you get a strike and see what value they had for that stat. ❌
4. You have **3 strikes** — use them wisely.

**The leaderboard slots**

Slots fill in as you find each player. The rank shown is their actual rank, not the order you guessed them.

```
#1  Nikola Jokić   ✓   29.6
#2  ?
#3  LeBron James   ✓   28.9
#4  ?
#5  ?
```

**Qualifiers** — All stats require ≥50 games and ≥15 MPG. Shooting percentages also require a minimum attempt rate so short-sample flukes don't appear.

**Duplicate guess** — Guessing the same player twice does not cost a strike.

**Daily reset** — A new challenge appears every day at midnight. Everyone sees the same challenge.
    """)
    if st.button("Got it!", use_container_width=True):
        st.rerun()




# ── SHARE TEXT builder ─────────────────────────────────────────────────────────
def _build_share_text() -> str:
    emoji_line = "".join(
        "✅" if g in answer else "❌"
        for g in all_guesses
    )
    result_line = (
        f"🏆 {found_count}/{TOP_N} found · {len(wrong)} wrong"
        if win else
        f"😔 {found_count}/{TOP_N} found · 3 strikes"
    )
    return (
        f"NBA Stat Challenge 📊\n"
        f"{today.strftime('%b %d, %Y')} · {ch['short']} · {ch['season']}\n\n"
        f"{emoji_line}\n"
        f"{result_line}"
    )


# ── PROCESS GUESS ─────────────────────────────────────────────────────────────
def process_guess(guess: str):
    guess = guess.strip()
    if not guess:
        return

    if guess in all_guesses:
        st.session_state[f"{sk}last_result"] = "duplicate"
        st.session_state[f"{sk}last_guess"]  = guess
        return

    all_guesses.append(guess)
    st.session_state[f"{sk}all_guesses"] = all_guesses

    if guess in answer:
        rank = answer.index(guess)
        slots[rank] = guess
        st.session_state[f"{sk}slots"]       = slots
        st.session_state[f"{sk}last_result"] = "correct"
        st.session_state[f"{sk}last_guess"]  = guess
        if all(s is not None for s in slots):
            st.session_state[f"{sk}game_over"] = True
            st.session_state[f"{sk}win"]       = True
    else:
        new_strikes = strikes + 1
        wrong.append(guess)
        st.session_state[f"{sk}wrong"]       = wrong
        st.session_state[f"{sk}strikes"]     = new_strikes
        st.session_state[f"{sk}last_result"] = "wrong"
        st.session_state[f"{sk}last_guess"]  = guess
        if new_strikes >= STRIKES:
            st.session_state[f"{sk}game_over"] = True
            st.session_state[f"{sk}win"]       = False


# ── PAGE HEADER ───────────────────────────────────────────────────────────────
hdr_col, help_col = st.columns([5, 1])
with hdr_col:
    st.markdown(
        f'<h1 style="margin-bottom:2px;font-size:1.8rem;color:#FAFAFA">Daily Stat Challenge</h1>'
        f'<div style="font-size:0.82rem;color:{TEXT_SECONDARY}">'
        f'📅 {today.strftime("%A, %B %d %Y")}</div>',
        unsafe_allow_html=True,
    )
with help_col:
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    if st.button("How to Play", use_container_width=True):
        show_help()

# ── CHALLENGE BANNER ──────────────────────────────────────────────────────────
found_count = sum(1 for s in slots if s is not None)

st.markdown(
    f'<div style="background:{SURFACE};border:1px solid {BORDER};'
    f'border-left:3px solid {ACCENT};border-radius:8px;'
    f'padding:16px 20px;margin:14px 0">'
    f'<div style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:8px">'
    f'<div>'
    f'<div style="font-size:0.65rem;font-weight:700;letter-spacing:0.12em;'
    f'color:{TEXT_SECONDARY};text-transform:uppercase;margin-bottom:4px">Today\'s Category</div>'
    f'<div style="font-size:1.5rem;font-weight:700;color:#FAFAFA">'
    f'{ch["full_name"]}</div>'
    f'<div style="font-size:0.82rem;color:{TEXT_SECONDARY};margin-top:2px">'
    f'{ch["season"]} Regular Season · {ch["min_label"]}</div>'
    f'</div>'
    f'<div style="text-align:right">'
    f'<div style="font-size:0.65rem;font-weight:700;letter-spacing:0.1em;'
    f'color:{TEXT_SECONDARY};text-transform:uppercase;margin-bottom:6px">Strikes</div>'
    f'<div>'
    + "".join(
        f'<span class="strike-pip {"strike-used" if i < strikes else "strike-unused"}"></span>'
        for i in range(STRIKES)
    )
    + f'</div>'
    f'<div style="font-size:0.75rem;color:{TEXT_SECONDARY};margin-top:4px">'
    f'{found_count}/{TOP_N} found</div>'
    f'</div></div>'
    f'</div>',
    unsafe_allow_html=True,
)

# ── FEEDBACK BANNER ───────────────────────────────────────────────────────────
if last_result == "correct":
    rank_idx = answer.index(last_guess) + 1 if last_guess in answer else "?"
    st.markdown(
        f'<div style="background:rgba(34,197,94,0.10);border:1px solid rgba(34,197,94,0.35);'
        f'border-radius:7px;padding:10px 16px;margin-bottom:8px;'
        f'font-size:0.88rem;font-weight:600;color:#22C55E">'
        f'✅ {last_guess} is #{rank_idx}!</div>',
        unsafe_allow_html=True,
    )
elif last_result == "wrong":
    remaining  = STRIKES - strikes
    end_phrase = "No strikes remaining — game over." if remaining <= 0 else \
                 f"{remaining} strike{'s' if remaining != 1 else ''} remaining."
    # Look up this player's stat value so the user can learn from the miss
    guessed_val = lookup.get(last_guess)
    val_note = (
        f' ({last_guess} had {guessed_val} {ch["short"]} — not quite enough.)'
        if guessed_val else ""
    )
    st.markdown(
        f'<div style="background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.30);'
        f'border-radius:7px;padding:10px 16px;margin-bottom:8px;'
        f'font-size:0.88rem;font-weight:600;color:#EF4444">'
        f'❌ {last_guess} is not in the Top 5.{val_note} {end_phrase}</div>',
        unsafe_allow_html=True,
    )
elif last_result == "duplicate":
    st.markdown(
        f'<div style="background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.25);'
        f'border-radius:7px;padding:10px 16px;margin-bottom:8px;'
        f'font-size:0.88rem;color:{ACCENT_GOLD}">'
        f'⚠️ You already guessed {last_guess}. No strike used.</div>',
        unsafe_allow_html=True,
    )

# ── GUESS INPUT (only while game is active) ───────────────────────────────────
# Rendered BEFORE the slots so the dropdown opens downward into the slot area
if not game_over:
    st.markdown(
        f'<div style="font-size:0.65rem;font-weight:700;letter-spacing:0.12em;'
        f'color:{TEXT_SECONDARY};text-transform:uppercase;margin-bottom:6px;margin-top:4px">'
        f'Make a guess</div>',
        unsafe_allow_html=True,
    )
    available = [p for p in player_pool if p not in all_guesses]
    with st.form("guess_form", clear_on_submit=True):
        guess_input = st.selectbox(
            "Player name",
            [""] + available,
            index=0,
            label_visibility="collapsed",
            placeholder="Search for a player…",
        )
        submitted = st.form_submit_button(
            "Guess →",
            use_container_width=True,
            type="primary",
        )
    if submitted and guess_input:
        process_guess(guess_input)
        st.rerun()
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

# ── TOP 5 SLOTS ───────────────────────────────────────────────────────────────
st.markdown(
    f'<div style="font-size:0.65rem;font-weight:700;letter-spacing:0.12em;'
    f'color:{TEXT_SECONDARY};text-transform:uppercase;margin-bottom:8px">'
    f'Top 5 — {ch["full_name"]} ({ch["short"]})</div>',
    unsafe_allow_html=True,
)

for rank_idx, slot_name in enumerate(slots, start=1):
    if slot_name is not None:
        stat_val   = _fmtv(df_top5.iloc[rank_idx - 1][ch["col"]], ch["fmt"])
        just_found = (last_result == "correct" and last_guess == slot_name)
        css_class  = "slot-row found" + (" just-found" if just_found else "")
        st.markdown(
            f'<div class="{css_class}">'
            f'<div class="slot-rank">#{rank_idx}</div>'
            f'<div class="slot-name">{slot_name}</div>'
            f'<div style="text-align:right">'
            f'<span class="slot-value">{stat_val}</span>'
            f'<span class="slot-unit">{ch["short"]}</span>'
            f'</div></div>',
            unsafe_allow_html=True,
        )
    else:
        if game_over and not win:
            true_name = df_top5.iloc[rank_idx - 1]["full_name"]
            stat_val  = _fmtv(df_top5.iloc[rank_idx - 1][ch["col"]], ch["fmt"])
            st.markdown(
                f'<div class="slot-row" style="background:rgba(239,68,68,0.06);'
                f'border-color:rgba(239,68,68,0.25);">'
                f'<div class="slot-rank">#{rank_idx}</div>'
                f'<div style="flex:1;font-size:1.0rem;font-weight:600;color:#A1A1AA">{true_name}</div>'
                f'<div style="text-align:right">'
                f'<span class="slot-value" style="color:#A1A1AA">{stat_val}</span>'
                f'<span class="slot-unit">{ch["short"]}</span>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="slot-row empty">'
                f'<div class="slot-rank">#{rank_idx}</div>'
                f'<div class="slot-placeholder">— — — — —</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

# ── WRONG GUESSES ─────────────────────────────────────────────────────────────
if wrong:
    st.markdown(
        f'<div style="margin-top:12px;margin-bottom:4px;font-size:0.65rem;'
        f'font-weight:700;color:{TEXT_SECONDARY};letter-spacing:0.1em;text-transform:uppercase">'
        f'Wrong guesses ({len(wrong)}/{STRIKES} strikes used)</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        "".join(f'<span class="wrong-guess">{w}</span>' for w in wrong),
        unsafe_allow_html=True,
    )

# ── GAME OVER SCREEN ──────────────────────────────────────────────────────────
if game_over:
    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    if win:
        st.markdown(
            f'<div style="background:rgba(34,197,94,0.08);border:1px solid rgba(34,197,94,0.30);'
            f'border-radius:12px;padding:24px;text-align:center;margin-top:8px">'
            f'<div style="font-size:2.5rem;margin-bottom:8px">🏆</div>'
            f'<div style="font-size:1.2rem;font-weight:700;color:#FAFAFA;margin-bottom:4px">'
            f'You got them all!</div>'
            f'<div style="font-size:0.88rem;color:{TEXT_SECONDARY}">'
            f'{len(wrong)} wrong guess{"es" if len(wrong) != 1 else ""} · '
            f'{len(all_guesses)} total guesses</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div style="background:rgba(239,68,68,0.07);border:1px solid rgba(239,68,68,0.25);'
            f'border-radius:12px;padding:24px;text-align:center;margin-top:8px">'
            f'<div style="font-size:2.5rem;margin-bottom:8px">😔</div>'
            f'<div style="font-size:1.2rem;font-weight:700;color:#FAFAFA;margin-bottom:4px">'
            f'3 strikes — better luck tomorrow</div>'
            f'<div style="font-size:0.88rem;color:{TEXT_SECONDARY}">'
            f'You found {found_count} of {TOP_N} players</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── SHARE ─────────────────────────────────────────────────────────────────
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    st.markdown(
        f'<div style="font-size:0.65rem;font-weight:700;letter-spacing:0.1em;'
        f'color:{TEXT_SECONDARY};text-transform:uppercase;margin-bottom:6px">Share your result</div>',
        unsafe_allow_html=True,
    )
    st.code(_build_share_text(), language=None)

    # ── RESET ─────────────────────────────────────────────────────────────────
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    if st.button("↩ Reset (practice mode)", use_container_width=True):
        for k in list(defaults.keys()) + [LS_LOADED, LS_READ_DONE]:
            if k in st.session_state:
                del st.session_state[k]
        st_javascript(f'localStorage.removeItem("{LS_KEY}"); 1', key="ls_clear")
        st.rerun()

# ── Persist current state to localStorage — only after read has confirmed done ─
# On run 1, st_javascript hasn't returned a real value yet; writing here would
# overwrite existing saved progress with blank defaults before we ever read it.
if st.session_state.get(LS_LOADED):
    _state_snapshot = {k: st.session_state.get(k) for k in defaults.keys()}
    st_javascript(
        f"localStorage.setItem('{LS_KEY}', JSON.stringify({json.dumps(_state_snapshot)})); 1",
        key="ls_write",
    )
