from sqlalchemy.orm import Session
import models
from datetime import datetime, timedelta

def get_primary_score(profile: models.Profile, matches_preferences: bool = False) -> float:
    completeness = profile.completeness_score or 0.0
    photo_bonus = min((len(profile.photos) if profile.photos else 0) * 5, 15)
    preference_bonus = 10 if matches_preferences else 0
    return round(min(completeness + photo_bonus + preference_bonus, 100), 2)

def get_behavioral_score(db: Session, profile_id: int) -> float:
    likes = db.query(models.Like).filter(models.Like.to_id == profile_id, models.Like.action == 'like').count()
    skips = db.query(models.Like).filter(models.Like.to_id == profile_id, models.Like.action == 'skip').count()
    total = likes + skips
    likes_ratio = (likes / total) * 100 if total > 0 else 50.0

    reciprocal_likes = db.query(models.Like).filter(
        models.Like.from_id == profile_id,
        models.Like.action == "like"
    ).count()
    match_rate = min(reciprocal_likes * 10, 25)

    profile = db.query(models.Profile).filter(models.Profile.id == profile_id).first()
    dialogs_bonus = min((profile.dialogs_started if profile else 0) * 5, 15)

    active_bonus = 0
    if profile and profile.last_active_at:
        if profile.last_active_at >= datetime.utcnow() - timedelta(hours=6):
            active_bonus = 10
        elif profile.last_active_at >= datetime.utcnow() - timedelta(days=1):
            active_bonus = 5

    return round(min(likes_ratio * 0.6 + match_rate + dialogs_bonus + active_bonus, 100), 2)

def get_combined_score(primary: float, behavioral: float) -> float:
    return round(0.6 * primary + 0.4 * behavioral, 2)