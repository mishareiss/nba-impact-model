"""
Export everything the public dashboard needs from the local Postgres DB into
small static JSON files under site/data/.

The public site never talks to a database: run this once locally after the
pipeline has been run, commit site/data/, and GitHub Pages serves the result.

    python scripts/export_static.py            # writes site/data/
    python scripts/export_static.py --out /tmp/x

Files written
-------------
  meta.json             dataset counts, model metrics, calibration, feature importance
  seasons.json          one row per player x season x season type (shot-making + single-season RAPM/xRAPM)
  pooled.json           one row per player x 3-season window (pooled xRAPM, more stable)
  players/<id>.json     binned shot chart per season + season list, loaded on demand

All tables are columnar-compact: {"cols": [...], "rows": [[...], ...]}.
No credentials are written anywhere; the DB URL is read from .env (DB_URL).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ingestion.db import engine  # noqa: E402  (reads DB_URL from .env)

MODELS = ROOT / "models"

# Shot chart binning: NBA "legacy" coordinates are tenths of a foot,
# hoop at (0, 0), x in [-250, 250], y up to ~420 at half court.
BIN = 20               # 2 ft x 2 ft bins
MAX_Y = 400            # drop heaves past ~40 ft from the baseline-ish origin
MIN_FGA_PLAYER_FILE = 100   # player gets a profile file if any season has >= this many FGA


def q(sql: str, **params) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return round(v, 4)
    if hasattr(v, "item"):  # numpy scalar
        return _clean(v.item())
    return v


def columnar(df: pd.DataFrame) -> dict:
    df = df.astype(object).where(pd.notnull(df), None)
    return {
        "cols": list(df.columns),
        "rows": [[_clean(v) for v in row] for row in df.itertuples(index=False, name=None)],
    }


def write(path: Path, obj) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    path.write_text(data, encoding="utf-8")
    return len(data)


# ---------------------------------------------------------------------------
# Player-season table (shot-making + single-season impact)
# Traded players have one row per team in player_career_stats; collapse to one
# row per (person, season, season_type) the same way the Streamlit app does.
# ---------------------------------------------------------------------------
SEASONS_SQL = """
SELECT
    person_id                                                       AS id,
    MAX(full_name)                                                  AS name,
    CASE WHEN COUNT(DISTINCT team) > 1
         THEN COUNT(DISTINCT team)::text || 'TM' ELSE MAX(team) END AS team,
    season,
    season_type                                                     AS stype,
    SUM(shots_attempted)::int                                       AS fga,
    SUM(shots_attempted * actual_fg_pct) / NULLIF(SUM(shots_attempted), 0) AS fg,
    SUM(shots_attempted * mean_xshot)    / NULLIF(SUM(shots_attempted), 0) AS xfg,
    SUM(shot_pts_above_expected)::float                             AS pae,
    MAX(xrapm)        AS xrapm,
    MAX(rapm)         AS rapm,
    MAX(o_rapm)       AS orapm,
    MAX(d_rapm)       AS drapm,
    MAX(possessions)  AS poss,
    MAX(gp)           AS gp,
    MAX(min)          AS min
FROM player_career_stats
GROUP BY person_id, season, season_type
"""

POOLED_SQL = """
SELECT
    p.person_id      AS id,
    pl.full_name     AS name,
    p.end_season     AS season,
    p.season_type    AS stype,
    p.window_seasons AS window,
    p.xrapm, p.rapm, p.rapm_prior AS rapm_prior, p.possessions AS poss
FROM player_impact_pooled p
LEFT JOIN players pl ON pl.person_id = p.person_id
"""

# Minutes and primary team per player-season, used to give pooled rows a
# "minutes over window" filter value and a current team label.
MINUTES_SQL = """
SELECT DISTINCT ON (person_id, season, season_type)
    person_id AS id, season, season_type AS stype, min, team_id
FROM player_season_stats
WHERE min > 0
ORDER BY person_id, season, season_type, min DESC
"""

SHOT_BINS_SQL = f"""
SELECT
    sp.person_id                         AS id,
    sp.season,
    sp.season_type                       AS stype,
    FLOOR(s.x_legacy / {BIN})::int        AS bx,
    FLOOR(s.y_legacy / {BIN})::int        AS by,
    COUNT(*)::int                         AS att,
    SUM(sp.shot_made::int)::int           AS made,
    SUM(sp.xshot)::float                  AS xs
FROM shot_predictions sp
JOIN shots s ON s.game_id = sp.game_id AND s.action_id = sp.action_id
WHERE s.y_legacy <= {MAX_Y} AND s.x_legacy BETWEEN -250 AND 250
GROUP BY 1, 2, 3, 4, 5
"""

LEAGUE_SQL = """
SELECT season, season_type AS stype,
       COUNT(*)::int AS fga,
       AVG(shot_made::int)::float AS fg,
       AVG(xshot)::float AS xfg
FROM shot_predictions
GROUP BY 1, 2
ORDER BY 1, 2
"""

COUNTS_SQL = """
SELECT
  (SELECT COUNT(*) FROM shot_predictions)                AS shots,
  (SELECT COUNT(*) FROM lineup_stints)                   AS stints,
  (SELECT COUNT(DISTINCT game_id) FROM shot_predictions) AS games,
  (SELECT COUNT(DISTINCT season) FROM shot_predictions)  AS seasons,
  (SELECT MIN(season) FROM shot_predictions)             AS first_season,
  (SELECT MAX(season) FROM shot_predictions)             AS last_season
"""

TEAMS_SQL = "SELECT team_id, tricode FROM teams"


def load_json(name: str):
    p = MODELS / name
    return json.loads(p.read_text()) if p.exists() else None


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    report = {}

    # ---- meta -------------------------------------------------------------
    counts = q(COUNTS_SQL).iloc[0].to_dict()
    league = q(LEAGUE_SQL)
    meta = {
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counts": {k: _clean(v) for k, v in counts.items()},
        "league": columnar(league),
        "model": load_json("xshot_v1_metadata.json"),
        "calibration": load_json("calibration_data.json"),
        "feature_importance": load_json("feature_importance.json"),
    }
    report["meta.json"] = write(out / "meta.json", meta)

    # ---- player seasons ---------------------------------------------------
    seasons = q(SEASONS_SQL).sort_values(["season", "stype", "xrapm"], ascending=[True, True, False])
    report["seasons.json"] = write(out / "seasons.json", columnar(seasons))

    # ---- pooled 3-year ----------------------------------------------------
    pooled = q(POOLED_SQL)
    mins = q(MINUTES_SQL)
    teams = q(TEAMS_SQL).set_index("team_id")["tricode"].to_dict()

    def window_minutes(row):
        ss = [s.strip() for s in str(row["window"]).strip("[]{}").replace("'", "").split(",")]
        m = mins[(mins.id == row["id"]) & (mins.stype == row["stype"]) & (mins.season.isin(ss))]
        return float(m["min"].sum())

    mins_idx = mins.set_index(["id", "season", "stype"])
    pooled["min"] = pooled.apply(window_minutes, axis=1)
    pooled["team"] = [
        teams.get(mins_idx["team_id"].get((r.id, r.season, r.stype)), None)
        for r in pooled.itertuples()
    ]
    pooled = pooled.drop(columns=["window"]).sort_values(
        ["season", "stype", "xrapm"], ascending=[True, True, False]
    )
    report["pooled.json"] = write(out / "pooled.json", columnar(pooled))

    # ---- per-player shot charts ------------------------------------------
    bins = q(SHOT_BINS_SQL)
    eligible = set(seasons.loc[seasons.fga >= MIN_FGA_PLAYER_FILE, "id"].astype(int))
    names = seasons.groupby("id")["name"].last().to_dict()
    player_index = []
    total = 0
    for pid, g in bins[bins.id.isin(eligible)].groupby("id"):
        charts = {}
        for (season, stype), gg in g.groupby(["season", "stype"]):
            charts.setdefault(stype, {})[season] = [
                [int(r.bx), int(r.by), int(r.att), int(r.made), round(float(r.xs), 2)]
                for r in gg.itertuples()
            ]
        total += write(out / "players" / f"{int(pid)}.json", {"id": int(pid), "bin_ft": BIN / 10, "charts": charts})
        player_index.append(int(pid))
    report["players/*.json"] = total
    report["player files"] = len(player_index)

    # ---- sanity report ----------------------------------------------------
    print("\nExport complete ->", out)
    for k, v in report.items():
        print(f"  {k:<18} {v:>12,}" + ("" if k == "player files" else " bytes"))
    print("\nCounts:", meta["counts"])
    print("Seasons by type:")
    print(league.to_string(index=False))
    last = seasons[(seasons.season == seasons.season.max()) & (seasons.stype == "Regular Season")]
    print(f"\nTop 5 single-season xRAPM, {seasons.season.max()} RS:")
    print(last.nlargest(5, "xrapm")[["name", "team", "xrapm", "rapm", "min"]].to_string(index=False))
    print("\nxRAPM range by season (RS):")
    rs = seasons[seasons.stype == "Regular Season"]
    print(rs.groupby("season")["xrapm"].describe()[["count", "min", "max"]].to_string())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "site" / "data")
    main(ap.parse_args().out)
