from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

# Ganti dengan koneksi PostgreSQL Anda
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:manullang2003@localhost:5432/match_cv")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)