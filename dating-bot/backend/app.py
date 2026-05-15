"""HTTP API (FastAPI)."""
import logging
import os
import secrets
import string
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
for _p in (BASE_DIR, ROOT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel
from sqlalchemy import create_engine, or_, text
from sqlalchemy.orm import Session, joinedload, sessionmaker

import models
import ranking
import cache as redis_cache
from backend.rabbit_events import publish_dating_event
from backend.tasks import recalculate_all_ratings_task, warmup_queue_task

try:
    from backend import minio_storage
except ImportError:
    minio_storage = None

from config import USE_MINIO, get_sync_database_url

SYNC_URL = get_sync_database_url()
if SYNC_URL.startswith("sqlite"):
    engine = create_engine(SYNC_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(SYNC_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("dating_backend")

REQUEST_COUNT = Counter("dating_api_requests_total", "Total API requests", ["method", "endpoint", "status"])
REQUEST_LATENCY = Histogram("dating_api_latency_seconds", "API latency", ["method", "endpoint"])

app = FastAPI(title="Dating Bot API - Stage 4")


class UserRegister(BaseModel):
    telegram_id: int
    username: Optional[str] = None
    invite_code: Optional[str] = None


class ProfileCreate(BaseModel):
    user_id: int
    name: Optional[str] = ""
    bio: Optional[str] = ""
    age: Optional[int] = None
    gender: Optional[str] = None
    city: Optional[str] = None
    interests: Optional[str] = ""
    preferred_city: Optional[str] = ""
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
    interests: Optional[str] = None
    preferred_city: Optional[str] = None
    preferred_gender: Optional[str] = None
    preferred_age_min: Optional[int] = None
    preferred_age_max: Optional[int] = None
    age: Optional[int] = None


class PhotoUpload(BaseModel):
    user_id: int
    file_id: str


class PhotoDelete(BaseModel):
    user_id: int
    photo_id: int


def _gen_referral_code(db: Session) -> str:
    chars = string.ascii_uppercase + string.digits
    for _ in range(40):
        code = "".join(secrets.choice(chars) for _ in range(8))
        if not db.query(models.User).filter(models.User.referral_code == code).first():
            return code
    return secrets.token_hex(4).upper()[:10]


def ensure_schema() -> None:
    dialect = engine.dialect.name
    with engine.begin() as conn:
        if dialect == "sqlite":
            pcolumns = {row[1] for row in conn.execute(text("PRAGMA table_info(profiles)"))}
            if "preferred_gender" not in pcolumns:
                conn.execute(text("ALTER TABLE profiles ADD COLUMN preferred_gender VARCHAR(50) DEFAULT 'any'"))
            if "preferred_age_min" not in pcolumns:
                conn.execute(text("ALTER TABLE profiles ADD COLUMN preferred_age_min INTEGER DEFAULT 18"))
            if "preferred_age_max" not in pcolumns:
                conn.execute(text("ALTER TABLE profiles ADD COLUMN preferred_age_max INTEGER DEFAULT 100"))
            if "dialogs_started" not in pcolumns:
                conn.execute(text("ALTER TABLE profiles ADD COLUMN dialogs_started INTEGER DEFAULT 0"))
            if "last_active_at" not in pcolumns:
                conn.execute(text("ALTER TABLE profiles ADD COLUMN last_active_at DATETIME"))
            if "interests" not in pcolumns:
                conn.execute(text("ALTER TABLE profiles ADD COLUMN interests TEXT DEFAULT ''"))
            if "preferred_city" not in pcolumns:
                conn.execute(text("ALTER TABLE profiles ADD COLUMN preferred_city VARCHAR(255) DEFAULT ''"))

            ucolumns = {row[1] for row in conn.execute(text("PRAGMA table_info(users)"))}
            if "referral_code" not in ucolumns:
                conn.execute(text("ALTER TABLE users ADD COLUMN referral_code VARCHAR(32)"))
            if "referred_by_id" not in ucolumns:
                conn.execute(text("ALTER TABLE users ADD COLUMN referred_by_id INTEGER"))
            if "referrals_count" not in ucolumns:
                conn.execute(text("ALTER TABLE users ADD COLUMN referrals_count INTEGER DEFAULT 0"))

            phcolumns = {row[1] for row in conn.execute(text("PRAGMA table_info(photos)"))}
            if "telegram_file_id" not in phcolumns:
                conn.execute(text("ALTER TABLE photos ADD COLUMN telegram_file_id VARCHAR(255)"))
                conn.execute(text("UPDATE photos SET telegram_file_id = s3_url WHERE telegram_file_id IS NULL"))

        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_profiles_active_score ON profiles(is_active, rating_score DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_likes_from_to_action ON likes(from_id, to_id, action)"))
        if dialect == "sqlite":
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_referral_code ON users(referral_code)"))


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
    if USE_MINIO and minio_storage:
        try:
            minio_storage.ensure_bucket()
        except Exception as exc:
            logger.warning("MinIO bucket init skipped: %s", exc)
    logger.info("Database initialized and schema checked")


@app.get("/metrics")
def metrics():
    return PlainTextResponse(generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
def health():
    return {"status": "ok", "database": engine.dialect.name}


@app.post("/user/register")
def register_user(user_data: UserRegister):
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.telegram_id == user_data.telegram_id).first()
        if user:
            if not user.referral_code:
                user.referral_code = _gen_referral_code(db)
                db.commit()
                db.refresh(user)
            return {
                "user_id": user.id,
                "telegram_id": user.telegram_id,
                "exists": True,
                "referral_code": user.referral_code,
            }
        inviter = None
        code = (user_data.invite_code or "").strip().upper()
        if code:
            inviter = db.query(models.User).filter(models.User.referral_code == code).first()
        new_user = models.User(
            telegram_id=user_data.telegram_id,
            username=user_data.username,
            referral_code=_gen_referral_code(db),
            referred_by_id=inviter.id if inviter else None,
        )
        db.add(new_user)
        db.flush()
        if inviter:
            inviter.referrals_count = (inviter.referrals_count or 0) + 1
        db.commit()
        db.refresh(new_user)
        publish_dating_event(
            "user_registered",
            {"user_id": new_user.id, "telegram_id": new_user.telegram_id, "invite_code": code or None},
        )
        return {
            "user_id": new_user.id,
            "telegram_id": new_user.telegram_id,
            "exists": False,
            "referral_code": new_user.referral_code,
        }
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
            profile.interests = profile_data.interests or ""
            profile.preferred_city = profile_data.preferred_city or ""
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
                interests=profile_data.interests or "",
                preferred_city=profile_data.preferred_city or "",
                preferred_gender=profile_data.preferred_gender or "any",
                preferred_age_min=profile_data.preferred_age_min or 18,
                preferred_age_max=profile_data.preferred_age_max or 100,
                last_active_at=datetime.utcnow(),
                completeness_score=calculate_completeness(profile_data),
            )
            db.add(profile)
        db.commit()
        db.refresh(profile)
        redis_cache.clear_all_queues()
        recalculate_all_ratings_task.delay()
        publish_dating_event("profile_upsert", {"profile_id": profile.id, "user_id": profile_data.user_id})
        return {"profile_id": profile.id, "completeness_score": profile.completeness_score}
    finally:
        db.close()


@app.get("/profile/{user_id}")
def get_profile(user_id: int):
    db = SessionLocal()
    try:
        profile = db.query(models.Profile).filter(models.Profile.user_id == user_id).first()
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        owner = db.query(models.User).filter(models.User.id == profile.user_id).first()
        photos_out = []
        for p in sorted(profile.photos, key=lambda ph: ph.order_index):
            fid = p.telegram_file_id or p.s3_url or ""
            photos_out.append(
                {
                    "id": p.id,
                    "file_id": fid,
                    "order_index": p.order_index,
                    "storage_url": p.s3_url if p.telegram_file_id else None,
                }
            )
        return {
            "id": profile.id,
            "user_id": profile.user_id,
            "name": profile.name,
            "bio": profile.bio,
            "age": profile.age,
            "gender": profile.gender,
            "city": profile.city,
            "interests": profile.interests or "",
            "preferred_city": profile.preferred_city or "",
            "rating_score": profile.rating_score,
            "preferred_gender": profile.preferred_gender,
            "preferred_age_min": profile.preferred_age_min,
            "preferred_age_max": profile.preferred_age_max,
            "photos": photos_out,
            "completeness_score": profile.completeness_score,
            "referral_code": owner.referral_code if owner else None,
        }
    finally:
        db.close()


@app.post("/profile/photo/upload")
def upload_profile_photo(payload: PhotoUpload):
    from config import BOT_TOKEN, USE_MINIO

    db = SessionLocal()
    try:
        profile = db.query(models.Profile).filter(models.Profile.user_id == payload.user_id).first()
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        existing = (
            db.query(models.Photo)
            .filter(
                models.Photo.profile_id == profile.id,
                models.Photo.telegram_file_id == payload.file_id,
            )
            .first()
        )
        if not existing:
            existing = (
                db.query(models.Photo)
                .filter(models.Photo.profile_id == profile.id, models.Photo.s3_url == payload.file_id)
                .first()
            )
        if existing:
            return {"status": "exists", "photo_id": existing.id}

        next_idx = db.query(models.Photo).filter(models.Photo.profile_id == profile.id).count()
        storage_url = payload.file_id
        telegram_fid = payload.file_id

        if USE_MINIO and minio_storage and BOT_TOKEN:
            fetched = minio_storage.fetch_telegram_file_bytes(BOT_TOKEN, payload.file_id)
            if fetched:
                data, ctype = fetched
                _, storage_url = minio_storage.upload_telegram_photo_bytes(data, ctype)
                telegram_fid = payload.file_id
            else:
                logger.warning("MinIO enabled but Telegram download failed; storing file_id only")

        if USE_MINIO and minio_storage and telegram_fid and storage_url != payload.file_id:
            photo = models.Photo(
                profile_id=profile.id,
                s3_url=storage_url,
                telegram_file_id=telegram_fid,
                order_index=next_idx,
            )
        else:
            photo = models.Photo(
                profile_id=profile.id,
                s3_url=payload.file_id,
                telegram_file_id=None,
                order_index=next_idx,
            )

        db.add(photo)
        db.commit()
        db.refresh(photo)
        redis_cache.clear_all_queues()
        publish_dating_event("photo_uploaded", {"profile_id": profile.id, "photo_id": photo.id})
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

        photo = (
            db.query(models.Photo)
            .filter(models.Photo.id == payload.photo_id, models.Photo.profile_id == profile.id)
            .first()
        )
        if not photo:
            raise HTTPException(status_code=404, detail="Photo not found")

        db.delete(photo)
        db.commit()
        redis_cache.clear_all_queues()
        publish_dating_event("photo_deleted", {"profile_id": profile.id, "photo_id": payload.photo_id})
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
        publish_dating_event("profile_patch", {"profile_id": profile.id})
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
        pid = profile.id
        db.query(models.Like).filter(
            or_(models.Like.from_id == pid, models.Like.to_id == pid)
        ).delete(synchronize_session=False)
        db.query(models.ProfileRating).filter(models.ProfileRating.profile_id == pid).delete(
            synchronize_session=False
        )
        db.delete(profile)
        db.commit()
        redis_cache.clear_all_queues()
        publish_dating_event("profile_deleted", {"user_id": user_id})
        return {"status": "deleted"}
    finally:
        db.close()


def calculate_completeness(profile_data: ProfileCreate) -> float:
    score = 0.0
    if profile_data.name:
        score += 1.0
    if profile_data.bio and len(profile_data.bio) > 10:
        score += 1.0
    if profile_data.age:
        score += 1.0
    if profile_data.gender:
        score += 1.0
    if profile_data.city:
        score += 1.0
    if profile_data.interests and len(profile_data.interests.strip()) > 2:
        score += 1.0
    if profile_data.preferred_city and len(profile_data.preferred_city.strip()) > 1:
        score += 1.0
    return (score / 7.0) * 100


def _telegram_photo_token(photo: models.Photo) -> Optional[str]:
    # В ленту — file_id (или legacy file_id в s3_url), не http-URL MinIO.
    if photo.telegram_file_id:
        return photo.telegram_file_id.strip()
    u = (photo.s3_url or "").strip()
    if u and not (u.startswith("http://") or u.startswith("https://")):
        return u
    return None


def _hydrate_queue_card_photos(db: Session, card: Dict[str, Any]) -> Dict[str, Any]:
    # Догрузка фото из БД, если в Redis пусто или только «битые» URL.
    pid = card.get("id")
    if not pid:
        return card
    raw = card.get("photos") or []
    if raw:
        cleaned = []
        for item in raw:
            if isinstance(item, dict):
                t = item.get("file_id") or ""
            else:
                t = str(item) if item else ""
            if t and not (t.startswith("http://") or t.startswith("https://")):
                cleaned.append(t)
        if cleaned:
            card["photos"] = cleaned
            card["photos_count"] = len(cleaned)
            return card
    rows = (
        db.query(models.Photo)
        .filter(models.Photo.profile_id == int(pid))
        .order_by(models.Photo.order_index)
        .all()
    )
    tokens = [t for r in rows if (t := _telegram_photo_token(r))]
    if tokens:
        card["photos"] = tokens
        card["photos_count"] = len(tokens)
    return card


def _refill_queue(db: Session, telegram_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    user = db.query(models.User).filter(models.User.telegram_id == telegram_id).first()
    if not user:
        return []

    total_active = db.query(models.Profile).filter(models.Profile.is_active == True).count()
    logger.info("Matching search for %s, active profiles: %s", telegram_id, total_active)

    base_q = (
        db.query(models.Profile)
        .options(joinedload(models.Profile.photos), joinedload(models.Profile.user))
        .filter(models.Profile.is_active == True)
    )
    excluded = []
    if user.profile:
        my_id = user.profile.id
        viewed = [l.to_id for l in db.query(models.Like).filter(models.Like.from_id == my_id).all()]
        excluded = [my_id] + viewed
        candidates = base_q.filter(models.Profile.id.notin_(excluded)).all()
    else:
        candidates = base_q.all()

    logger.info("Candidates after filtering: %s", len(candidates))
    if not candidates:
        return []

    scored = []
    my_profile = user.profile
    for p in candidates:
        primary = ranking.get_primary_score(p, viewer=my_profile)
        behavioral = ranking.get_behavioral_score(db, p.id)
        owner = p.user or db.query(models.User).filter(models.User.id == p.user_id).first()
        ref = ranking.get_referral_boost(owner)
        combined = ranking.get_combined_score(primary, behavioral, ref)
        scored.append((combined, p, primary, behavioral))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_profiles = scored[:limit]

    profiles_data = []
    for combined, p, primary, behavioral in top_profiles:
        p.rating_score = combined
        db.add(
            models.ProfileRating(
                profile_id=p.id,
                primary_score=primary,
                behavioral_score=behavioral,
                combined_score=combined,
            )
        )
        ordered = sorted(p.photos or [], key=lambda ph: ph.order_index)
        photo_tokens = [t for ph in ordered if (t := _telegram_photo_token(ph))]
        profiles_data.append(
            {
                "id": p.id,
                "name": p.name or (p.user.username if p.user else None) or "Аноним",
                "age": p.age,
                "gender": p.gender,
                "city": p.city,
                "bio": p.bio,
                "rating_score": p.rating_score,
                "photos_count": len(photo_tokens),
                "photos": photo_tokens,
            }
        )

    db.commit()
    redis_cache.push_profiles_to_queue(user.id, profiles_data)
    logger.info("Loaded %s profiles to Redis queue", len(profiles_data))
    return profiles_data


@app.get("/matching/next/{telegram_id}")
def get_next_profile(telegram_id: int):
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.telegram_id == telegram_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        profile = redis_cache.pop_next_profile(user.id)
        if not profile:
            new_batch = _refill_queue(db, telegram_id)
            if not new_batch:
                return {"message": "Анкеты закончились. Нажмите /refresh или зайдите позже."}
            profile = redis_cache.pop_next_profile(user.id)
            warmup_queue_task.delay(user.telegram_id)
        if profile and isinstance(profile, dict) and profile.get("id") is not None:
            profile = _hydrate_queue_card_photos(db, profile)
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
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        redis_cache.clear_queue(user.id)
        publish_dating_event("matching_refresh", {"user_id": user.id})
        return {"status": "success", "message": "Кэш очищен. Нажмите /next для загрузки."}
    finally:
        db.close()


@app.post("/interaction/like")
def record_like(data: InteractionRequest = Body(...)):
    db = SessionLocal()
    try:
        from_user = db.query(models.User).filter(models.User.telegram_id == data.from_telegram_id).first()
        if not from_user or not from_user.profile:
            raise HTTPException(status_code=404, detail="User not found")
        db.add(models.Like(from_id=from_user.profile.id, to_id=data.to_profile_id, action="like"))
        from_user.profile.last_active_at = datetime.utcnow()
        db.commit()

        publish_dating_event(
            "like",
            {"from_profile_id": from_user.profile.id, "to_profile_id": data.to_profile_id},
        )

        mutual = (
            db.query(models.Like)
            .filter(
                models.Like.from_id == data.to_profile_id,
                models.Like.to_id == from_user.profile.id,
                models.Like.action == "like",
            )
            .first()
        )

        if mutual:
            mp = db.query(models.Profile).filter(models.Profile.id == data.to_profile_id).first()
            mu = db.query(models.User).filter(models.User.id == mp.user_id).first()
            from_user.profile.dialogs_started = (from_user.profile.dialogs_started or 0) + 1
            mp.dialogs_started = (mp.dialogs_started or 0) + 1
            db.commit()
            publish_dating_event(
                "match",
                {
                    "profile_a": from_user.profile.id,
                    "profile_b": data.to_profile_id,
                    "telegram_a": from_user.telegram_id,
                    "telegram_b": mu.telegram_id,
                },
            )
            return {
                "status": "success",
                "action": "like",
                "match": True,
                "matched_profile": {
                    "telegram_id": mu.telegram_id,
                    "telegram_username": mu.username,
                    "name": mp.name or mu.username,
                    "age": mp.age,
                    "gender": mp.gender,
                    "city": mp.city,
                    "bio": mp.bio,
                    "rating_score": mp.rating_score,
                },
            }
        return {"status": "success", "action": "like", "match": False}
    finally:
        db.close()


@app.post("/interaction/skip")
def record_skip(data: InteractionRequest = Body(...)):
    db = SessionLocal()
    try:
        from_user = db.query(models.User).filter(models.User.telegram_id == data.from_telegram_id).first()
        if not from_user or not from_user.profile:
            raise HTTPException(status_code=404, detail="User not found")
        db.add(models.Like(from_id=from_user.profile.id, to_id=data.to_profile_id, action="skip"))
        from_user.profile.last_active_at = datetime.utcnow()
        db.commit()
        publish_dating_event(
            "skip",
            {"from_profile_id": from_user.profile.id, "to_profile_id": data.to_profile_id},
        )
        return {"status": "success", "action": "skip", "match": False}
    finally:
        db.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
