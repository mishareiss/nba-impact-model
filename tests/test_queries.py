"""
Tests for dashboard SQL query functions.

These tests run against the live local PostgreSQL database.
They verify schema, column presence, and basic row counts — not ML correctness.
"""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import pytest
import pandas as pd
from dashboard.utils.queries import (
    get_single_season_leaderboard,
    get_pooled_leaderboard,
    get_daily_challenge_stats,
    get_lineup_leaderboard,
)


SEASON = "2025-26"
SEASON_TYPE = "Regular Season"

LEADERBOARD_REQUIRED_COLS = {
    "person_id", "full_name", "team", "season", "season_type",
    "xrapm", "rapm", "o_rapm", "d_rapm",
    "gp", "mpg", "position",
}

CHALLENGE_REQUIRED_COLS = {
    "person_id", "full_name", "gp", "mpg",
    "ppg", "rpg", "apg", "spg", "bpg",
    "fg_pct", "fg3_pct", "ft_pct",
}

LINEUP_REQUIRED_COLS = {
    "season", "team", "net_pts", "possessions",
}


class TestSingleSeasonLeaderboard:
    def test_returns_dataframe(self):
        df = get_single_season_leaderboard(SEASON, SEASON_TYPE)
        assert isinstance(df, pd.DataFrame)

    def test_has_required_columns(self):
        df = get_single_season_leaderboard(SEASON, SEASON_TYPE)
        missing = LEADERBOARD_REQUIRED_COLS - set(df.columns)
        assert not missing, f"Missing columns: {missing}"

    def test_nonempty_for_current_season(self):
        df = get_single_season_leaderboard(SEASON, SEASON_TYPE)
        assert len(df) > 50, f"Expected >50 players, got {len(df)}"

    def test_position_populated(self):
        df = get_single_season_leaderboard(SEASON, SEASON_TYPE)
        assert "position" in df.columns
        pct_with_pos = df["position"].notna().mean()
        assert pct_with_pos > 0.8, f"Only {pct_with_pos:.0%} of rows have position"

    def test_min_possessions_filter_works(self):
        # Use an extreme value to guarantee the strict filter cuts more than the loose one
        df_loose = get_single_season_leaderboard(SEASON, SEASON_TYPE, min_poss=1)
        df_strict = get_single_season_leaderboard(SEASON, SEASON_TYPE, min_poss=50_000)
        assert len(df_strict) < len(df_loose), \
            "min_poss=50000 should return fewer rows than min_poss=1"

    def test_xrapm_is_numeric(self):
        df = get_single_season_leaderboard(SEASON, SEASON_TYPE)
        assert pd.api.types.is_numeric_dtype(df["xrapm"])
        assert df["xrapm"].between(-20, 20).all(), "xRAPM values look unreasonable"

    def test_playoffs_returns_dataframe(self):
        """Verify playoffs query runs without error (data depends on full pipeline having run)."""
        df = get_single_season_leaderboard(SEASON, "Playoffs", min_poss=50)
        assert isinstance(df, pd.DataFrame)  # may be empty if pipeline hasn't run yet


class TestPooledLeaderboard:
    def test_returns_dataframe(self):
        df = get_pooled_leaderboard()
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_has_impact_columns(self):
        df = get_pooled_leaderboard()
        assert "xrapm" in df.columns or "net_xrapm" in df.columns


class TestDailyChallenge:
    def test_returns_dataframe(self):
        df = get_daily_challenge_stats(SEASON)
        assert isinstance(df, pd.DataFrame)

    def test_min_gp_enforced(self):
        df = get_daily_challenge_stats(SEASON, min_gp=50, min_mpg=15.0)
        assert (df["gp"] >= 50).all(), "min_gp=50 not enforced"

    def test_min_mpg_enforced(self):
        df = get_daily_challenge_stats(SEASON, min_gp=50, min_mpg=15.0)
        assert (df["mpg"] >= 15.0).all(), "min_mpg=15 not enforced"

    def test_has_required_columns(self):
        df = get_daily_challenge_stats(SEASON)
        missing = CHALLENGE_REQUIRED_COLS - set(df.columns)
        assert not missing, f"Missing columns: {missing}"

    def test_sufficient_player_pool(self):
        df = get_daily_challenge_stats(SEASON, min_gp=50, min_mpg=15.0)
        assert len(df) >= 50, f"Pool too small: {len(df)} players (need ≥50 for a good game)"

    def test_no_duplicate_players(self):
        df = get_daily_challenge_stats(SEASON)
        assert df["full_name"].is_unique, "Duplicate player names in challenge pool"


class TestLineupLeaderboard:
    def test_returns_dataframe(self):
        df = get_lineup_leaderboard(season=SEASON, season_type=SEASON_TYPE)
        assert isinstance(df, pd.DataFrame)

    def test_min_possessions_filter(self):
        df = get_lineup_leaderboard(season=SEASON, season_type=SEASON_TYPE, min_poss=100)
        if not df.empty:
            # column is total_poss in the lineup leaderboard
            poss_col = "total_poss" if "total_poss" in df.columns else "possessions"
            assert (df[poss_col] >= 100).all()
