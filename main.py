from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from starlette.middleware.sessions import SessionMiddleware
from databases.database import Base, engine
import google.generativeai as genai
import os

from routes import auth, upload

# === Konfigurasi ENV dan Gemini ===
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# === Inisialisasi FastAPI ===
app = FastAPI()

# === Middleware CORS ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://match-cv.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Middleware Session ===
app.add_middleware(SessionMiddleware, secret_key="SUPERSECRET")

# === Router ===
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(upload.router, prefix="/cv", tags=["CV Upload"])

Base.metadata.create_all(bind=engine)