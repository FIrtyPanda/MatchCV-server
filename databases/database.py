import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from dotenv import load_dotenv

# Muat .env
load_dotenv()

# Ambil dari environment
DATABASE_URL = os.getenv("DATABASE_URL")

# Buat engine koneksi
engine = create_engine(DATABASE_URL)

# Session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base model
Base = declarative_base()

# Dependency DB
def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()