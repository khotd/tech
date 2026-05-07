import os
import sys
from datetime import datetime

from celery import Celery
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models
from config import REDIS_URL
from backend import ranking

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "..", "dating_bot.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
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
            primary = ranking.get_primary_score(profile, matches_preferences=False)
            behavioral = ranking.get_behavioral_score(db, profile.id)
            combined = ranking.get_combined_score(primary, behavioral)
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
    # Заглушка для stage 4: queue warming делается лениво в API, задача фиксирует событие.
    return {"status": "queued", "telegram_id": telegram_id}
