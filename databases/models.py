from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from datetime import datetime
import json

from databases.database import Base  # Ambil Base dari database.py agar konsisten

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class CVUpload(Base):
    __tablename__ = "cv_uploads"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Optional untuk anonymous user
    original_filename = Column(String, nullable=False)
    saved_path = Column(String, nullable=False)
    extracted_text = Column(Text, nullable=False)
    keywords = Column(Text, nullable=False)  # Simpan sebagai JSON string
    created_at = Column(DateTime, default=datetime.utcnow)

    def set_keywords(self, keywords: list[str]):
        self.keywords = json.dumps(keywords)

    def get_keywords(self) -> list[str]:
        return json.loads(self.keywords)

class ChatHistory(Base):
    __tablename__ = "chat_histories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # nullable=True untuk anonymous
    cv_upload_id = Column(Integer, ForeignKey("cv_uploads.id"), nullable=True)  # relasi opsional
    role = Column(String, nullable=False)  # "user" atau "llm"
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)