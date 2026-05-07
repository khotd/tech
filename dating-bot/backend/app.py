"""
Backend API - FastAPI
"""
import sys
import os
import logging
from datetime import datetime
sys.path.append('..')

from fastapi import FastAPI, HTTPException, Body, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
import models
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

import ranking
import cache as redis_cache
from backend.tasks import recalculate_all_ratings_task, warmup_queue_task

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "..", "dating_bot.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("dating_backend")

REQUEST_COUNT = Counter("dating_api_requests_total", "Total API requests", ["method", "endpoint", "status"])
REQUEST_LATENCY = Histogram("dating_api_latency_seconds", "API latency", ["method", "endpoint"])

app = FastAPI(title="Dating Bot API - Stage 4")

class UserRegister(BaseModel):
    telegram_id: int
    username: Optional[str] = None

class ProfileCreate(BaseModel):
    user_id: int
    name: Optional[str] = ""
    bio: Optional[str] = ""
    age: Optional[int] = None
    gender: Optional[str] = None
    city: Optional[str] = None
    preferred_gender: Optional[str] = "any"
    preferred_age_min: Optional[int] = 18
    preferred_age_max: Optional[int] = 100

class InteractionRequest(BaseModel):
    from_telegram_id: int
    to_profile_id: int


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    bio: Optional[str] = None
    city: Optional[str] = None
    preferred_gender: Optional[str] = None
    preferred_age_min: Optional[int] = None
    preferred_age_max: Optional[int] = None


class PhotoUpload(BaseModel):
    user_id: int
    file_id: str


class PhotoDelete(BaseModel):
    user_id: int
    photo_id: int


def ensure_schema() -> None:
    with engine.begin() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(profiles)"))}
        if "preferred_gender" not in columns:
            conn.execute(text("ALTER TABLE profiles ADD COLUMN preferred_gender VARCHAR(50) DEFAULT 'any'"))
        if "preferred_age_min" not in columns:
            conn.execute(text("ALTER TABLE profiles ADD COLUMN preferred_age_min INTEGER DEFAULT 18"))
        if "preferred_age_max" not in columns:
            conn.execute(text("ALTER TABLE profiles ADD COLUMN preferred_age_max INTEGER DEFAULT 100"))
        if "dialogs_started" not in columns:
            conn.execute(text("ALTER TABLE profiles ADD COLUMN dialogs_started INTEGER DEFAULT 0"))
        if "last_active_at" not in columns:
            conn.execute(text("ALTER TABLE profiles ADD COLUMN last_active_at DATETIME"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_profiles_active_score ON profiles(is_active, rating_score DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_likes_from_to_action ON likes(from_id, to_id, action)"))


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    method = request.method
    endpoint = request.url.path
    with REQUEST_LATENCY.labels(method=method, endpoint=endpoint).time():
        response = await call_next(request)
    REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=str(response.status_code)).inc()
    return response

@app.on_event("startup")
def startup():
    models.Base.metadata.create_all(bind=engine)
    ensure_schema()
    logger.info("Database initialized and schema checked")


@app.get("/metrics")
def metrics():
    return PlainTextResponse(generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/user/register")
def register_user(user_data: UserRegister):
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.telegram_id == user_data.telegram_id).first()
        if user:
            return {"user_id": user.id, "telegram_id": user.telegram_id, "exists": True}
        new_user = models.User(telegram_id=user_data.telegram_id, username=user_data.username)
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return {"user_id": new_user.id, "telegram_id": new_user.telegram_id, "exists": False}
    finally:
        db.close()

@app.post("/profile/create")
def create_profile(profile_data: ProfileCreate):
    db = SessionLocal()
    try:
        profile = db.query(models.Profile).filter(models.Profile.user_id == profile_data.user_id).first()
        if profile:
            profile.name = profile_data.name
            profile.bio = profile_data.bio
            profile.age = profile_data.age
            profile.gender = profile_data.gender
            profile.city = profile_data.city
            profile.preferred_gender = profile_data.preferred_gender or "any"
            profile.preferred_age_min = profile_data.preferred_age_min or 18
            profile.preferred_age_max = profile_data.preferred_age_max or 100
            profile.last_active_at = datetime.utcnow()
            profile.completeness_score = calculate_completeness(profile_data)
            profile.updated_at = datetime.utcnow()
        else:
            profile = models.Profile(
                user_id=profile_data.user_id,
                name=profile_data.name,
                bio=profile_data.bio,
                age=profile_data.age,
                gender=profile_data.gender,
                city=profile_data.city,
                preferred_gender=profile_data.preferred_gender or "any",
                preferred_age_min=profile_data.preferred_age_min or 18,
                preferred_age_max=profile_data.preferred_age_max or 100,
                last_active_at=datetime.utcnow(),
                completeness_score=calculate_completeness(profile_data)
            )
            db.add(profile)
        db.commit()
        db.refresh(profile)
        
    
        redis_cache.clear_all_queues()
        recalculate_all_ratings_task.delay()
        return {"profile_id": profile.id, "completeness_score": profile.completeness_score}
    finally:
        db.close()

@app.get("/profile/{user_id}")
def get_profile(user_id: int):
    db = SessionLocal()
    try:
        profile = db.query(models.Profile).filter(models.Profile.user_id == user_id).first()
        if not profile: raise HTTPException(status_code=404, detail="Profile not found")
        return {"id": profile.id, "user_id": profile.user_id, "name": profile.name,
                "bio": profile.bio, "age": profile.age, "gender": profile.gender, 
                "city": profile.city, "rating_score": profile.rating_score,
                "preferred_gender": profile.preferred_gender,
                "preferred_age_min": profile.preferred_age_min,
                "preferred_age_max": profile.preferred_age_max,
                "photos": [
                    {"id": p.id, "file_id": p.s3_url, "order_index": p.order_index}
                    for p in sorted(profile.photos, key=lambda ph: ph.order_index)
                ] if profile.photos else [],
                "completeness_score": profile.completeness_score}
    finally:
        db.close()


@app.post("/profile/photo/upload")
def upload_profile_photo(payload: PhotoUpload):
    db = SessionLocal()
    try:
        profile = db.query(models.Profile).filter(models.Profile.user_id == payload.user_id).first()
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        # В учебной версии храним telegram file_id в поле s3_url.
        existing = db.query(models.Photo).filter(
            models.Photo.profile_id == profile.id,
            models.Photo.s3_url == payload.file_id
        ).first()
        if existing:
            return {"status": "exists", "photo_id": existing.id}

        next_idx = db.query(models.Photo).filter(models.Photo.profile_id == profile.id).count()
        photo = models.Photo(profile_id=profile.id, s3_url=payload.file_id, order_index=next_idx)
        db.add(photo)
        db.commit()
        db.refresh(photo)
        redis_cache.clear_all_queues()
        return {"status": "uploaded", "photo_id": photo.id}
    finally:
        db.close()


@app.post("/profile/photo/delete")
def delete_profile_photo(payload: PhotoDelete):
    db = SessionLocal()
    try:
        profile = db.query(models.Profile).filter(models.Profile.user_id == payload.user_id).first()
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        photo = db.query(models.Photo).filter(
            models.Photo.id == payload.photo_id,
            models.Photo.profile_id == profile.id
        ).first()
        if not photo:
            raise HTTPException(status_code=404, detail="Photo not found")

        db.delete(photo)
        db.commit()
        redis_cache.clear_all_queues()
        return {"status": "deleted", "photo_id": payload.photo_id}
    finally:
        db.close()


@app.put("/profile/{user_id}")
def update_profile(user_id: int, payload: ProfileUpdate):
    db = SessionLocal()
    try:
        profile = db.query(models.Profile).filter(models.Profile.user_id == user_id).first()
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        for field, value in payload.model_dump(exclude_none=True).items():
            setattr(profile, field, value)
        profile.updated_at = datetime.utcnow()
        db.commit()
        redis_cache.clear_all_queues()
        return {"status": "updated"}
    finally:
        db.close()


@app.delete("/profile/{user_id}")
def delete_profile(user_id: int):
    db = SessionLocal()
    try:
        profile = db.query(models.Profile).filter(models.Profile.user_id == user_id).first()
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        db.delete(profile)
        db.commit()
        redis_cache.clear_all_queues()
        return {"status": "deleted"}
    finally:
        db.close()

def calculate_completeness(profile_data: ProfileCreate) -> float:
    score = 0.0
    if profile_data.name: score += 1.0
    if profile_data.bio and len(profile_data.bio) > 10: score += 1.0
    if profile_data.age: score += 1.0
    if profile_data.gender: score += 1.0
    if profile_data.city: score += 1.0
    return (score / 5.0) * 100 

def _refill_queue(db: Session, telegram_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    user = db.query(models.User).filter(models.User.telegram_id == telegram_id).first()
    if not user: return []

    total_active = db.query(models.Profile).filter(models.Profile.is_active == True).count()
    logger.info("Matching search for %s, active profiles: %s", telegram_id, total_active)

    excluded = []
    if user.profile:
        my_id = user.profile.id
        viewed = [l.to_id for l in db.query(models.Like).filter(models.Like.from_id == my_id).all()]
        excluded = [my_id] + viewed
        candidates = db.query(models.Profile).filter(
            models.Profile.id.notin_(excluded), models.Profile.is_active == True
        ).all()
    else:
        candidates = db.query(models.Profile).filter(models.Profile.is_active == True).all()

    logger.info("Candidates after filtering: %s", len(candidates))
    if not candidates: return []

    scored = []
    my_profile = user.profile
    for p in candidates:
        matches_preferences = True
        if my_profile:
            if my_profile.preferred_gender and my_profile.preferred_gender != "any":
                matches_preferences = p.gender == my_profile.preferred_gender
            if my_profile.preferred_age_min and p.age:
                matches_preferences = matches_preferences and p.age >= my_profile.preferred_age_min
            if my_profile.preferred_age_max and p.age:
                matches_preferences = matches_preferences and p.age <= my_profile.preferred_age_max
        primary = ranking.get_primary_score(p, matches_preferences=matches_preferences)
        behavioral = ranking.get_behavioral_score(db, p.id)
        combined = ranking.get_combined_score(primary, behavioral)
        scored.append((combined, p, primary, behavioral))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_profiles = scored[:limit]

    profiles_data = []
    for combined, p, primary, behavioral in top_profiles:
        p.rating_score = combined
        db.add(models.ProfileRating(
            profile_id=p.id,
            primary_score=primary,
            behavioral_score=behavioral,
            combined_score=combined
        ))
        profiles_data.append({
            "id": p.id,
            "name": p.name or p.user.username or "Аноним",  
            "age": p.age, "gender": p.gender, "city": p.city,
            "bio": p.bio, "rating_score": p.rating_score,
            "photos_count": len(p.photos) if p.photos else 0,
            "photos": [photo.s3_url for photo in sorted(p.photos, key=lambda ph: ph.order_index)] if p.photos else []
        })

    db.commit()
    redis_cache.push_profiles_to_queue(user.id, profiles_data)
    logger.info("Loaded %s profiles to Redis queue", len(profiles_data))
    return profiles_data

@app.get("/matching/next/{telegram_id}")
def get_next_profile(telegram_id: int):
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.telegram_id == telegram_id).first()
        if not user: raise HTTPException(status_code=404, detail="User not found")
        
        profile = redis_cache.pop_next_profile(user.id)
        if not profile:
            new_batch = _refill_queue(db, telegram_id)
            if not new_batch:
                return {"message": "Анкеты закончились. Нажмите /refresh или зайдите позже."}
            profile = redis_cache.pop_next_profile(user.id)
            warmup_queue_task.delay(user.telegram_id)
        if user.profile:
            user.profile.last_active_at = datetime.utcnow()
            db.commit()
        return profile
    finally:
        db.close()

@app.post("/matching/refresh/{telegram_id}")
def refresh_matching(telegram_id: int):
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.telegram_id == telegram_id).first()
        if not user: raise HTTPException(status_code=404, detail="User not found")
        redis_cache.clear_queue(user.id)  # Очищаем только свою очередь
        return {"status": "success", "message": "Кэш очищен. Нажмите /next для загрузки."}
    finally:
        db.close()

@app.post("/interaction/like")
def record_like(data: InteractionRequest = Body(...)):
    db = SessionLocal()
    try:
        from_user = db.query(models.User).filter(models.User.telegram_id == data.from_telegram_id).first()
        if not from_user or not from_user.profile: raise HTTPException(status_code=404, detail="User not found")
        db.add(models.Like(from_id=from_user.profile.id, to_id=data.to_profile_id, action="like"))
        from_user.profile.last_active_at = datetime.utcnow()
        db.commit()
        
        mutual = db.query(models.Like).filter(
            models.Like.from_id == data.to_profile_id,
            models.Like.to_id == from_user.profile.id,
            models.Like.action == "like"
        ).first()
        
        if mutual:
            mp = db.query(models.Profile).filter(models.Profile.id == data.to_profile_id).first()
            mu = db.query(models.User).filter(models.User.id == mp.user_id).first()
            return {"status": "success", "action": "like", "match": True, "matched_profile": {
                "telegram_id": mu.telegram_id, "telegram_username": mu.username, "name": mp.name or mu.username,
                "age": mp.age, "gender": mp.gender, "city": mp.city, "bio": mp.bio, "rating_score": mp.rating_score
            }}
        return {"status": "success", "action": "like", "match": False}
    finally:
        db.close()

@app.post("/interaction/skip")
def record_skip(data: InteractionRequest = Body(...)):
    db = SessionLocal()
    try:
        from_user = db.query(models.User).filter(models.User.telegram_id == data.from_telegram_id).first()
        if not from_user or not from_user.profile: raise HTTPException(status_code=404, detail="User not found")
        db.add(models.Like(from_id=from_user.profile.id, to_id=data.to_profile_id, action="skip"))
        from_user.profile.last_active_at = datetime.utcnow()
        db.commit()
        return {"status": "success", "action": "skip", "match": False}
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)