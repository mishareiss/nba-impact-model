# Deploying the Daily Stat Challenge

The game is a self-contained Streamlit app in `game/` that only needs two database tables: `players` and `player_season_stats` (~9k rows total). It does not require the full analytics pipeline.

## Railway (recommended)

### 1. Export game data from local database

```bash
chmod +x scripts/export_game_data.sh
./scripts/export_game_data.sh
# Creates: game_data_export.sql
```

### 2. Create a Railway project

1. Go to [railway.app](https://railway.app) and create a new project
2. Add a **PostgreSQL** service from the Railway dashboard
3. Note the `DATABASE_URL` from the PostgreSQL service's "Connect" tab

### 3. Import game data to Railway

```bash
psql $RAILWAY_DATABASE_URL < game_data_export.sql
```

Or use Railway's built-in import via the PostgreSQL service → Data tab.

### 4. Deploy the app

```bash
# Install Railway CLI
npm install -g @railway/cli

# Link and deploy
railway login
railway link          # select your project
railway up            # deploys using railway.toml
```

### 5. Set environment variables in Railway

In your Railway project dashboard, add:
```
DATABASE_URL = <your Railway PostgreSQL connection string>
```

Railway automatically injects this if you link the PostgreSQL service to your app service.

### 6. Add a custom domain (optional)

In Railway: your service → Settings → Networking → Generate Domain or add a custom domain.

---

## What the game needs

| Table | Rows | Purpose |
|-------|------|---------|
| `players` | ~4,500 | Player name lookup |
| `player_season_stats` | ~9,000 | Per-season traditional stats |

That's it — no play-by-play, no ML predictions, no lineup stints needed.

## Updating game data each season

Run the ingestion script locally:
```bash
python -m src.ingestion.load_player_stats
```

Then re-export and re-import:
```bash
./scripts/export_game_data.sh
psql $RAILWAY_DATABASE_URL < game_data_export.sql
```

## Local development of the game app

```bash
# Set DATABASE_URL in .env, then:
streamlit run game/Home.py
```
