import time
from nba_api.stats.endpoints import playbyplayv3, leaguegamefinder
import pandas as pd
from src.utils.logging import get_logger

logger = get_logger(__name__)

def get_game_ids(season: str = "2025-26", season_type: str = "Regular Season") -> list[str]:
    games = leaguegamefinder.LeagueGameFinder(
        season_nullable=season,
        season_type_nullable=season_type,
        league_id_nullable="00",
    ).get_data_frames()[0]
    ids = games["GAME_ID"].unique().tolist()
    logger.info(f"Found {len(ids)} games for {season} {season_type}")
    return ids

def fetch_pbp(game_id: str, retries: int = 3, delay: float = 1.0) -> pd.DataFrame:
    for attempt in range(1, retries + 1):
        try:
            df = playbyplayv3.PlayByPlayV3(game_id=game_id).get_data_frames()[0]
            if df.empty:
                logger.warning(f"API returned empty DataFrame for game {game_id}")
                return df
            logger.debug(f"Fetched {len(df)} rows for game {game_id}")
            return df
        except KeyboardInterrupt:
            raise
        except Exception as e:
            logger.warning(f"Attempt {attempt}/{retries} failed for {game_id}: {e}")
            if attempt < retries:
                time.sleep(delay * (2 ** (attempt - 1)))  # true exponential backoff
    raise RuntimeError(f"Failed to fetch PBP for {game_id} after {retries} attempts")