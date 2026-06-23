#!/usr/bin/env bash
# Export only the tables the Daily Stat Challenge needs.
# Run this locally, then import the dump into your Railway PostgreSQL database.
#
# Usage:
#   chmod +x scripts/export_game_data.sh
#   ./scripts/export_game_data.sh
#
# Then import to Railway:
#   psql <RAILWAY_DATABASE_URL> < game_data_export.sql

set -euo pipefail

source .env   # loads DATABASE_URL

OUTPUT="game_data_export.sql"

echo "Exporting game tables from local database..."

pg_dump "$DATABASE_URL" \
  --no-owner \
  --no-acl \
  --table=players \
  --table=player_season_stats \
  > "$OUTPUT"

echo "Done → $OUTPUT"
echo ""
echo "Row counts in export:"
psql "$DATABASE_URL" -c "SELECT 'players' AS table, COUNT(*) FROM players UNION ALL SELECT 'player_season_stats', COUNT(*) FROM player_season_stats;"
echo ""
echo "To import into Railway:"
echo "  psql \$RAILWAY_DATABASE_URL < $OUTPUT"
