"""Database connection for the standalone game app."""
import os
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

_DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not _DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is not set. "
        "Set it to your PostgreSQL connection string, e.g. "
        "postgresql://user:pass@host:5432/dbname"
    )

# Railway and some providers use postgres:// — SQLAlchemy needs postgresql://
if _DATABASE_URL.startswith("postgres://"):
    _DATABASE_URL = _DATABASE_URL.replace("postgres://", "postgresql://", 1)

_engine = create_engine(_DATABASE_URL, pool_pre_ping=True)


@st.cache_data(ttl=3600, show_spinner=False)
def query(sql: str, params: dict | None = None) -> pd.DataFrame:
    with _engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)
