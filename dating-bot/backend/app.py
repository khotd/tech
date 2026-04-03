"""
Backend API - FastAPI
Основная логика, работа с БД
"""
import sys
sys.path.append('..')

from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, Session
import models
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# Синхронный движок для SQLite
DATABASE_URL = "sqlite:///dating_bot.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

app = FastAPI(title="Dating Bot API")


# === Pydantic модели ===
class UserRegister(BaseModel):
    telegram_id: int
    username: Optional[str] = None


class ProfileCreate(BaseModel):
    user_id: int
    bio: Optional[str] = ""
    age: Optional[int] = None
    gender: Optional[str] = None
    city: Optional[str] = None


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
async def startup():
    """Создание таблиц при запуске"""
    models.Base.metadata.create_all(bind=engine)
    print("Database initialized")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/user/register")
async def register_user(user_data: UserRegister):
    """Регистрация пользователя по telegram_id"""
    db = SessionLocal()
    try:
        # Проверяем, есть ли уже
        user = db.query(models.User).filter(models.User.telegram_id == user_data.telegram_id).first()
        
        if user:
            return {"user_id": user.id, "telegram_id": user.telegram_id, "exists": True}
        
        # Создаём нового
        new_user = models.User(
            telegram_id=user_data.telegram_id,
            username=user_data.username
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        return {"user_id": new_user.id, "telegram_id": new_user.telegram_id, "exists": False}
    finally:
        db.close()


@app.get("/user/{telegram_id}")
async def get_user(telegram_id: int):
    """Получить пользователя по telegram_id"""
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.telegram_id == telegram_id).first()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {
            "id": user.id,
            "telegram_id": user.telegram_id,
            "username": user.username,
            "created_at": str(user.created_at)
        }
    finally:
        db.close()


@app.post("/profile/create")
async def create_profile(profile_data: ProfileCreate):
    """Создание анкеты"""
    db = SessionLocal()
    try:
        profile = models.Profile(
            user_id=profile_data.user_id,
            bio=profile_data.bio,
            age=profile_data.age,
            gender=profile_data.gender,
            city=profile_data.city,
            completeness_score=calculate_completeness(profile_data)
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        
        return {"profile_id": profile.id, "completeness_score": profile.completeness_score}
    finally:
        db.close()


@app.get("/profile/{user_id}")
async def get_profile(user_id: int):
    """Получить анкету пользователя"""
    db = SessionLocal()
    try:
        profile = db.query(models.Profile).filter(models.Profile.user_id == user_id).first()
        
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        
        return {
            "id": profile.id,
            "user_id": profile.user_id,
            "bio": profile.bio,
            "age": profile.age,
            "gender": profile.gender,
            "city": profile.city,
            "rating_score": profile.rating_score
        }
    finally:
        db.close()


def calculate_completeness(profile_data: ProfileCreate) -> float:
    """Расчёт полноты анкеты (Уровень 1 рейтинга)"""
    score = 0.0
    max_score = 4.0
    
    if profile_data.bio and len(profile_data.bio) > 10:
        score += 1.0
    if profile_data.age:
        score += 1.0
    if profile_data.gender:
        score += 1.0
    if profile_data.city:
        score += 1.0
    
    return (score / max_score) * 100


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
