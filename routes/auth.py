from fastapi import APIRouter, Request, HTTPException, status, Form
from fastapi.responses import JSONResponse
from fastapi import Depends
from sqlalchemy.orm import Session
from databases.database import get_db
from databases.models import User

router = APIRouter()

# === Register ===
@router.post("/register")
def register(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    existing_user = db.query(User).filter((User.username == username) | (User.email == email)).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username atau email sudah digunakan.")

    user = User(username=username, email=email, password=password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "Registrasi berhasil."}

# === Login ===
@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == username, User.password == password).first()
    if not user:
        raise HTTPException(status_code=401, detail="Username atau password salah.")

    request.session["user"] = {"id": user.id, "username": user.username}
    return {"message": "Login berhasil."}

# === Logout ===
@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"message": "Logout berhasil."}

# === Get current user ===
@router.get("/me")
def get_me(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Belum login")

    return {"user": user}