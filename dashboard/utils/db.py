"""
Database access for the dashboard.

Reuses src.ingestion.db engine with Streamlit connection caching so
the pool is shared across reruns instead of creating a new connection
on every page load.
"""
import sys
import os
from pathlib import Path

# Ensure the project root is on sys.path when running streamlit from any cwd
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pandas as pd
import streamlit as st
from sqlalchemy import text

from src.ingestion.db import engine


@st.cache_data(ttl=300, show_spinner=False)
def query(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Execute SQL and return a DataFrame. Results cached for 5 minutes."""
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


def get_seasons() -> list[str]:
    df = query("SELECT DISTINCT season FROM player_career_stats ORDER BY season DESC")
    return df["season"].tolist()


def get_season_types() -> list[str]:
    return ["Regular Season", "Playoffs"]
