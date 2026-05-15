import os
import sys
from datetime import datetime

from celery import Celery
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import models
from config import REDIS_URL, get_sync_database_url
from backend import ranking

SYNC_URL = get_sync_database_url()
if SYNC_URL.startswith("sqlite"):
    engine = create_engine(SYNC_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(SYNC_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

celery_app = Celery("dating_tasks", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.beat_schedule = {
    "recalculate-ratings-every-10-min": {
        "task": "backend.tasks.recalculate_all_ratings_task",
        "schedule": 600.0,
    }
}
celery_app.conf.timezone = "UTC"


@celery_app.task(name="backend.tasks.recalculate_all_ratings_task")
def recalculate_all_ratings_task() -> dict:
    db = SessionLocal()
    try:
        profiles = db.query(models.Profile).filter(models.Profile.is_active == True).all()
        updated = 0
        for profile in profiles:
            primary = ranking.get_primary_score(profile, viewer=None)
            behavioral = ranking.get_behavioral_score(db, profile.id)
            user = db.query(models.User).filter(models.User.id == profile.user_id).first()
            ref = ranking.get_referral_boost(user)
            combined = ranking.get_combined_score(primary, behavioral, ref)
            profile.rating_score = combined
            db.add(models.ProfileRating(
                profile_id=profile.id,
                primary_score=primary,
                behavioral_score=behavioral,
                combined_score=combined,
                calculated_at=datetime.utcnow(),
            ))
            updated += 1
        db.commit()
        return {"updated_profiles": updated}
    finally:
        db.close()


@celery_app.task(name="backend.tasks.warmup_queue_task")
def warmup_queue_task(telegram_id: int) -> dict:
    return {"status": "queued", "telegram_id": telegram_id}
