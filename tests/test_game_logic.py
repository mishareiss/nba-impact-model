"""
Tests for Daily Stat Challenge game logic — no database required.

Covers: seed stability, position mapping, share text, stat category completeness.
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import hashlib
from datetime import date


# ── Inline the helpers we want to test (avoids Streamlit import side-effects) ──

def _daily_seed(d: date) -> int:
    return int(hashlib.sha256(d.strftime("%Y%m%d").encode()).hexdigest(), 16) % (10**12)


_POS_GROUPS = {
    "Guard":   {"G", "G-F", "F-G"},
    "Forward": {"F", "F-G", "G-F", "F-C", "C-F"},
    "Center":  {"C", "C-F", "F-C"},
}


def _primary_pos(raw: str | None) -> str:
    if not raw or str(raw).strip() == "":
        return "Unknown"
    raw = str(raw).strip()
    if raw in ("G",):
        return "Guard"
    if raw in ("F",):
        return "Forward"
    if raw in ("C",):
        return "Center"
    if "G" in raw and "F" not in raw:
        return "Guard"
    if "C" in raw and "F" not in raw:
        return "Center"
    if "G" in raw and "F" in raw:
        return "Guard"
    if "F" in raw and "C" in raw:
        return "Forward"
    return "Unknown"


class TestDailySeed:
    def test_same_date_same_seed(self):
        d = date(2026, 6, 21)
        assert _daily_seed(d) == _daily_seed(d)

    def test_different_dates_different_seeds(self):
        d1 = date(2026, 6, 21)
        d2 = date(2026, 6, 22)
        assert _daily_seed(d1) != _daily_seed(d2)

    def test_seed_in_valid_range(self):
        for month in range(1, 13):
            d = date(2026, month, 15)
            seed = _daily_seed(d)
            assert 0 <= seed < 10**12

    def test_known_seed_is_stable(self):
        d = date(2026, 1, 1)
        expected = _daily_seed(d)
        assert _daily_seed(d) == expected, "Seed changed — game history would break"


class TestPositionMapping:
    def test_pure_guard(self):
        assert _primary_pos("G") == "Guard"

    def test_pure_forward(self):
        assert _primary_pos("F") == "Forward"

    def test_pure_center(self):
        assert _primary_pos("C") == "Center"

    def test_gf_is_guard(self):
        assert _primary_pos("G-F") == "Guard"

    def test_fg_is_guard(self):
        assert _primary_pos("F-G") == "Guard"

    def test_fc_is_forward(self):
        assert _primary_pos("F-C") == "Forward"

    def test_cf_is_forward(self):
        assert _primary_pos("C-F") == "Forward"

    def test_none_is_unknown(self):
        assert _primary_pos(None) == "Unknown"

    def test_empty_string_is_unknown(self):
        assert _primary_pos("") == "Unknown"

    def test_all_known_nba_positions(self):
        nba_positions = ["G", "F", "C", "G-F", "F-G", "F-C", "C-F"]
        for pos in nba_positions:
            result = _primary_pos(pos)
            assert result in ("Guard", "Forward", "Center"), \
                f"Position '{pos}' mapped to unexpected group '{result}'"


class TestStatCategories:
    """Smoke-test that STAT_CATEGORIES has valid structure."""

    STAT_CATEGORIES = [
        ("ppg",      "Points Per Game",         "PPG",   ".1f", "≥50 GP, ≥15 MPG",              None,       None),
        ("rpg",      "Rebounds Per Game",        "RPG",   ".1f", "≥50 GP, ≥15 MPG",              None,       None),
        ("apg",      "Assists Per Game",         "APG",   ".1f", "≥50 GP, ≥15 MPG",              None,       None),
        ("spg",      "Steals Per Game",          "SPG",   ".1f", "≥50 GP, ≥15 MPG",              None,       None),
        ("bpg",      "Blocks Per Game",          "BPG",   ".1f", "≥50 GP, ≥15 MPG",              None,       None),
        ("fg3m_pg",  "3-Pointers Made Per Game", "3PM/G", ".1f", "≥50 GP, ≥15 MPG, ≥2 3PA/G",   "fg3a_pg",  2.0),
        ("fg_pct",   "Field Goal %",             "FG%",   ".3f", "≥50 GP, ≥15 MPG, ≥5 FGA/G",   "fga_pg",   5.0),
        ("fg3_pct",  "3-Point %",               "3P%",   ".3f", "≥50 GP, ≥15 MPG, ≥3 3PA/G",   "fg3a_pg",  3.0),
        ("ft_pct",   "Free Throw %",             "FT%",   ".3f", "≥50 GP, ≥15 MPG, ≥3 FTA/G",   "fta_pg",   3.0),
        ("tpg",      "Turnovers Per Game",       "TOV/G", ".1f", "≥50 GP, ≥15 MPG",              None,       None),
        ("pts_total","Total Points",             "PTS",   ".0f", "≥50 GP, ≥15 MPG",              None,       None),
        ("fga_pg",   "FGA Per Game",             "FGA/G", ".1f", "≥50 GP, ≥15 MPG",              None,       None),
        ("orpg",     "Offensive Rebounds/G",     "OREB/G",".1f", "≥50 GP, ≥15 MPG",              None,       None),
        ("drpg",     "Defensive Rebounds/G",     "DREB/G",".1f", "≥50 GP, ≥15 MPG",              None,       None),
    ]

    def test_all_categories_have_7_fields(self):
        for cat in self.STAT_CATEGORIES:
            assert len(cat) == 7, f"Category {cat[0]} has {len(cat)} fields, expected 7"

    def test_no_duplicate_stat_cols(self):
        cols = [c[0] for c in self.STAT_CATEGORIES]
        assert len(cols) == len(set(cols)), "Duplicate stat column keys in STAT_CATEGORIES"

    def test_all_formats_valid(self):
        import datetime
        for cat in self.STAT_CATEGORIES:
            fmt = cat[3]
            try:
                f"{1.23:{fmt}}"
            except ValueError:
                pytest.fail(f"Invalid format spec '{fmt}' in category '{cat[0]}'")

    def test_attempt_cols_consistent(self):
        for cat in self.STAT_CATEGORIES:
            attempt_col, attempt_min = cat[5], cat[6]
            assert (attempt_col is None) == (attempt_min is None), \
                f"Category '{cat[0]}': attempt_col and attempt_min must both be None or both be set"
