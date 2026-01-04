from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# This finds the root of your project directory
BASE_DIR = Path(__file__).resolve().parent.parent

# This is the actual SQLite file
DB_PATH = BASE_DIR / "data" / "finance.db"

# SQLite connection string
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Create the engine (this opens the database file)
engine = create_engine(DATABASE_URL, echo=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)