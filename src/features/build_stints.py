import re
import bisect
import pandas as pd
from sqlalchemy import text
from src.ingestion.db import engine
from src.utils.logging import get_logger

logger = get_logger(__name__)

PERIOD_DURATION = {**{p: 720 for p in range(1, 5)}, **{p: 300 for p in range(5, 20)}}

def period_start_time(period: int) -> float:
    return sum(PERIOD_DURATION.get(p, 300) for p in range(1, period))

def clock_to_seconds(clock_str: str) -> float | None:
    if not clock_str or clock_str == 'NaN':
        return None
    m = re.match(r'PT(\d+)M([\d.]+)S', str(clock_str))
    if not m:
        return None
    return int(m.group(1)) * 60 + float(m.group(2))

def to_absolute_time(period: int, clock_str: str) -> float | None:
    remaining = clock_to_seconds(clock_str)
    if remaining is None:
        return None
    duration = PERIOD_DURATION.get(period, 300)
    elapsed = duration - remaining
    return period_start_time(period) + elapsed

def load_game_ids() -> list[str]:
    with engine.connect() as conn:
        return [r[0] for r in conn.execute(
            text(
                """
                SELECT game_id FROM games ORDER BY game_id
                """
            )
        )]

def load_game_meta(game_id: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT home_team_id, away_team_id, season, season_type FROM games WHERE game_id = :g"),
                {"g": game_id}
            ).fetchone()
        if not row:
            return None
        return {
            "home_team_id": row[0], 
            "away_team_id": row[1], 
            "season": row[2], 
            "season_type": row[3]
        }

def load_game_events(game_id: str) -> pd.DataFrame:
    query = text("""
        SELECT action_id, period, clock, team_id, person_id,
            player_name, action_type, sub_type, description,
            shot_result, shot_value,
            NULLIF(score_home, 'NaN')::integer AS score_home,
            NULLIF(score_away, 'NaN')::integer AS score_away
        FROM play_by_play
        WHERE game_id = :g
        ORDER BY action_id
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params={"g": game_id})

def load_xshot(game_id: str) -> dict:
    query = text("""
        SELECT action_id, xshot_points, team_id
        FROM shot_predictions
        WHERE game_id = :g
    """)
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"g": game_id})
    return df.set_index("action_id").to_dict(orient='index')

def build_roster_map(df: pd.DataFrame) -> dict:
    """
    {(last_name, team_id): [person_id, ...]}
    Multi-value so same-last-name teammates don't overwrite each other.
    """
    roster = {}
    for _, row in df.iterrows():
      if (pd.notna(row['person_id']) and pd.notna(row['player_name'])
              and str(row['player_name']) not in ('NaN', '')
              and pd.notna(row['team_id'])):
          key = (str(row['player_name']).strip(), int(row['team_id']))
          pid = int(row['person_id'])
          if key not in roster:
              roster[key] = []
          if pid not in roster[key]:
              roster[key].append(pid)
    return roster

def parse_sub(description: str):
    """'SUB: Nance Jr. FOR Johnson' → ('Nance Jr.', 'Johnson')"""
    if not description or str(description) == 'NaN':
        return None, None
    m = re.match(r'SUB:\s+(.+?)\s+FOR\s+(.+)', str(description).strip())
    if not m:
        return None, None
    return m.group(1).strip(), m.group(2).strip()

def identify_starters(df: pd.DataFrame, home_id: int, away_id: int,
                      roster_map: dict) -> dict:
    starters  = {home_id: set(), away_id: set()}
    subbed_in = {home_id: set(), away_id: set()}

    period1 = df[df['period'] == 1]
    subs_p1 = period1[period1['action_type'] == 'Substitution']
    first_sub_id = subs_p1['action_id'].min() if not subs_p1.empty else float('inf')

    # Pass 1: players in non-sub events before first sub in period 1 → starter
    pre_sub = period1[
        (period1['action_id'] < first_sub_id) &
        period1['person_id'].notna() &
        period1['team_id'].isin([home_id, away_id])
    ]
    for _, row in pre_sub.iterrows():
        tid = int(row['team_id'])
        pid = int(row['person_id'])
        if tid in starters and len(starters[tid]) < 5:
            starters[tid].add(pid)

    # Pass 2: subbed OUT in period 1 before being subbed IN → starter
    for _, row in subs_p1.iterrows():
        tid    = int(row['team_id']) if pd.notna(row['team_id']) else None
        if tid not in starters:
            continue
        out_id = int(row['person_id']) if pd.notna(row['person_id']) else None
        in_name, _ = parse_sub(row['description'])
        candidates = roster_map.get((in_name, tid), []) if in_name else []

        if out_id and out_id not in subbed_in[tid] and len(starters[tid]) < 5:
            starters[tid].add(out_id)
        for in_id in candidates:
            subbed_in[tid].add(in_id)

    # Pass 3: fallback — scan all non-sub events for players never subbed in
    if len(starters[home_id]) < 5 or len(starters[away_id]) < 5:
        non_sub = df[df['action_type'] != 'Substitution'].sort_values('action_id')
        for _, row in non_sub.iterrows():
            tid = int(row['team_id']) if pd.notna(row['team_id']) else None
            if tid not in starters or len(starters[tid]) >= 5:
                continue
            pid = int(row['person_id']) if pd.notna(row['person_id']) else None
            if pid and pid not in subbed_in[tid]:
                starters[tid].add(pid)
            if len(starters[home_id]) == 5 and len(starters[away_id]) == 5:
                break

    for tid, name in [(home_id, 'home'), (away_id, 'away')]:
        if len(starters[tid]) != 5:
            logger.warning(
                'Could not identify 5 starters for ' + name +
                ' team ' + str(tid) + ' — found ' + str(len(starters[tid]))
            )

    return starters

def resolve_in_player(in_name: str, tid: int, roster_map: dict, current_lineup: set) -> int | None:
    """Resolve IN player name to person_id using off-court disambiguation."""
    if not in_name:
        return None
    candidates = roster_map.get((in_name, tid), [])
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    off_court = [p for p in candidates if p not in current_lineup]
    if len(off_court) == 1:
        return off_court[0]
    logger.warning(f"Ambiguous sub: '{in_name}' team={tid} candidates={candidates}")
    return candidates[0]  # best guess

def build_stints_from_pbp(game_id: str, df: pd.DataFrame,
                        meta: dict) -> list[dict]:
  home_id = meta['home_team_id']
  away_id = meta['away_team_id']

  roster_map = build_roster_map(df)
  starters   = identify_starters(df, home_id, away_id, roster_map)

  lineup = {
      home_id: set(starters.get(home_id, set())),
      away_id: set(starters.get(away_id, set())),
  }

  subs = df[df['action_type'] == 'Substitution'].copy()
  subs['abs_time'] = subs.apply(
      lambda r: to_absolute_time(int(r['period']), r['clock']), axis=1
  )
  subs = subs.dropna(subset=['abs_time'])

  def make_stint(start, end):
      home_p = sorted(lineup[home_id])
      away_p = sorted(lineup[away_id])
      if len(home_p) != 5 or len(away_p) != 5:
          return None
      return {
          "game_id": game_id, "season": meta['season'],
          "season_type": meta['season_type'],
          "start_time": round(start, 2), "end_time": round(end, 2),
          "duration": round(end - start, 2),
          "home_team_id": home_id, "away_team_id": away_id,
          "home_players": home_p, "away_players": away_p,
          "home_points": 0, "away_points": 0, "net_points": 0,
          "home_poss": 0.0, "away_poss": 0.0, "total_poss": 0.0,
          "home_fga": 0, "away_fga": 0, "home_fgm": 0, "away_fgm": 0,
          "home_fta": 0, "away_fta": 0, "home_ftm": 0, "away_ftm": 0,
          "home_tov": 0, "away_tov": 0, "home_oreb": 0, "away_oreb": 0,
          "home_xshot_pts": 0.0, "away_xshot_pts": 0.0,
      }

  stints = []
  current_start = 0.0

  for abs_time, group in subs.groupby('abs_time', sort=True):
      if abs_time > current_start:
          s = make_stint(current_start, abs_time)
          if s:
              stints.append(s)

      for _, row in group.iterrows():
          tid    = int(row['team_id']) if pd.notna(row['team_id']) else None
          if tid not in lineup:
              continue
          out_id = int(row['person_id']) if pd.notna(row['person_id']) else None
          in_name, _ = parse_sub(row['description'])
          in_id  = resolve_in_player(in_name, tid, roster_map, lineup[tid])

          if out_id and in_id:
            if out_id in lineup[tid] and in_id not in lineup[tid]:
                lineup[tid].discard(out_id)
                lineup[tid].add(in_id)
            else:
                logger.debug(
                    'Skipping inconsistent sub at t=' + str(abs_time) +
                    ': out_on_court=' + str(out_id in lineup[tid]) +
                    ' in_already_on_court=' + str(in_id in lineup[tid])
                )
          elif out_id and not in_id:
            logger.debug('Could not resolve IN player ' + repr(in_name))

      current_start = abs_time

  final_period = int(df['period'].max())
  game_end = period_start_time(final_period) + PERIOD_DURATION.get(final_period, 300)
  if game_end > current_start:
      s = make_stint(current_start, game_end)
      if s:
          stints.append(s)

  return stints


def compute_stint_stats(stints: list[dict], df: pd.DataFrame, xshot_map: dict, home_id: int, away_id: int):

    if not stints:
        return

    df = df.copy()
    df['abs_time'] = df.apply(
        lambda r: to_absolute_time(int(r['period']), r['clock']), axis=1
    )

    # Score timeline for point calculation
    score_df = df[df['score_home'].notna()][
        ['abs_time', 'score_home', 'score_away']
    ].dropna()
    score_times = score_df['abs_time'].tolist()
    score_h = score_df['score_home'].tolist()
    score_a = score_df['score_away'].tolist()

    def score_at (t):
        if not score_times:
            return 0, 0
        idx = bisect.bisect_right(score_times, t) - 1
        if idx < 0:
            return 0, 0
        return score_h[idx], score_a[idx]

    # Points per stint via scoreboard differences
    for s in stints:
        sh0, sa0 = score_at(s['start_time'])
        sh1, sa1 = score_at(s['end_time'])
        s['home_points'] = max(0, sh1 - sh0)
        s['away_points'] = max(0, sa1 - sa0)
        s['net_points'] = s['home_points'] - s['away_points']

    # Fast lookup: action_id → abs_time
    action_time = df.set_index('action_id')['abs_time'].to_dict()
    stint_starts = [s['start_time'] for s in stints]

    def find_stint(t) -> int | None:
        if t is None or pd.isna(t):
            return None
        idx = bisect.bisect_right(stint_starts, t) - 1
        if 0 <= idx < len(stints) and t <= stints[idx]['end_time']:
            return idx
        return None

    # Box stats
    for _, row in df.iterrows():
        t = row['abs_time']
        idx = find_stint(t)
        if idx is None:
            continue
        s = stints[idx]
        tid = int(row['team_id']) if pd.notna(row['team_id']) else None
        action = str(row['action_type']) if pd.notna(row['action_type']) else ''
        prefix = 'home' if tid == home_id else 'away' if tid == away_id else None
        if not prefix:
            continue

        if action in ('Made Shot', 'Missed Shot'):
            s[f'{prefix}_fga'] += 1
            if action == 'Made Shot':
                s[f'{prefix}_fgm'] += 1
        elif action == 'Free Throw':
            s[f'{prefix}_fta'] += 1
            desc = str(row.get('description') or '')
            if 'Made' in desc or str(row.get('shot_result', '')) == 'Made':
                s[f'{prefix}_ftm'] += 1
        elif action == 'Turnover':
            s[f'{prefix}_tov'] += 1
        elif action == 'Rebound':
            sub = str(row.get('sub_type') or '')
            if 'Offensive' in sub:
                s[f'{prefix}_oreb'] += 1

    # xShot per stint
    for action_id, xdata in xshot_map.items():
        t = action_time.get(action_id)
        idx = find_stint(t)
        if idx is None:
            continue
        s = stints[idx]
        tid = xdata.get('team_id')
        prefix = 'home' if tid == home_id else 'away' if tid == away_id else None
        if prefix:
            s[f'{prefix}_xshot_pts'] += xdata.get('xshot_points', 0.0)

    # Possessions
    for s in stints:
        s['home_poss'] = round(s['home_fga'] + 0.44 * s['home_fta'] + s['home_tov'], 2)
        s['away_poss'] = round(s['away_fga'] + 0.44 * s['away_fta'] + s['away_tov'], 2)
        s['total_poss'] = round((s['home_poss'] + s['away_poss']) / 2, 2)

def insert_stints(stints: list[dict]):
    if not stints:
        return
    game_id = stints[0]['game_id']
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM lineup_stints WHERE game_id = :g"), {"g": game_id})
        conn.execute(text("""
        INSERT INTO lineup_stints (
              game_id, season, season_type, start_time, end_time, duration,
              home_team_id, away_team_id, home_players, away_players,
              home_points, away_points, net_points,
              home_poss, away_poss, total_poss,
              home_fga, away_fga, home_fgm, away_fgm,
              home_fta, away_fta, home_ftm, away_ftm,
              home_tov, away_tov, home_oreb, away_oreb,
              home_xshot_pts, away_xshot_pts
          ) VALUES (
              :game_id, :season, :season_type, :start_time, :end_time, :duration,
              :home_team_id, :away_team_id, :home_players, :away_players,
              :home_points, :away_points, :net_points,
              :home_poss, :away_poss, :total_poss,
              :home_fga, :away_fga, :home_fgm, :away_fgm,
              :home_fta, :away_fta, :home_ftm, :away_ftm,
              :home_tov, :away_tov, :home_oreb, :away_oreb,
              :home_xshot_pts, :away_xshot_pts
          )
        """), stints)

def main():
    game_ids = load_game_ids()
    logger.info(f"Processing {len(game_ids):,} games")
    total_stints = 0
    errors = 0

    for i, game_id in enumerate(game_ids, 1):
        try:
            meta = load_game_meta(game_id)
            if not meta:
                logger.warning(f"No meta for {game_id}, skipping")
                continue
            if not meta['home_team_id'] or not meta['away_team_id']:
                logger.warning(f"Skipping {game_id}: invalid team IDs (0)")
                continue

            df    = load_game_events(game_id)
            xshot = load_xshot(game_id)

            stints = build_stints_from_pbp(game_id, df, meta)
            compute_stint_stats(stints, df, xshot, meta['home_team_id'], meta['away_team_id'])
            insert_stints(stints)

            total_stints += len(stints)
            if i % 500 == 0:
                logger.info(f"[{i}/{len(game_ids)}] {total_stints:,} stints so far")

        except Exception as e:
            logger.error(f"Game {game_id} failed: {e}")
            errors += 1

    logger.info(f"Done - {total_stints:,} stints inserted, {errors} errors")

if __name__ == "__main__":
    main()