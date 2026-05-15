from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Set

from sqlalchemy.orm import Session

import models


def _tags(text: Optional[str]) -> Set[str]:
    if not text:
        return set()
    return {t.strip().lower() for t in text.replace(";", ",").split(",") if t.strip()}


def get_primary_score(
    candidate: models.Profile,
    viewer: Optional[models.Profile] = None,
) -> float:
    completeness = candidate.completeness_score or 0.0
    photo_bonus = min((len(candidate.photos) if candidate.photos else 0) * 5, 15)
    preference_bonus = 0.0

    if viewer:
        gender_ok = True
        if viewer.preferred_gender and viewer.preferred_gender != "any":
            gender_ok = candidate.gender == viewer.preferred_gender
        age_ok = True
        if candidate.age:
            if viewer.preferred_age_min and candidate.age < viewer.preferred_age_min:
                age_ok = False
            if viewer.preferred_age_max and candidate.age > viewer.preferred_age_max:
                age_ok = False
        if gender_ok and age_ok:
            preference_bonus += 10.0

        if viewer.preferred_city and candidate.city:
            if viewer.preferred_city.strip().lower() == (candidate.city or "").strip().lower():
                preference_bonus += 8.0

        vt = _tags(viewer.interests)
        ct = _tags(candidate.interests)
        if vt and ct:
            overlap = len(vt & ct)
            if overlap:
                preference_bonus += min(overlap * 4.0, 12.0)

    return round(min(completeness + photo_bonus + preference_bonus, 100.0), 2)


def get_behavioral_score(db: Session, profile_id: int) -> float:
    likes = db.query(models.Like).filter(models.Like.to_id == profile_id, models.Like.action == "like").count()
    skips = db.query(models.Like).filter(models.Like.to_id == profile_id, models.Like.action == "skip").count()
    total = likes + skips
    likes_ratio = (likes / total) * 100 if total > 0 else 50.0

    reciprocal_likes = db.query(models.Like).filter(
        models.Like.from_id == profile_id,
        models.Like.action == "like",
    ).count()
    match_rate = min(reciprocal_likes * 10, 25)

    profile = db.query(models.Profile).filter(models.Profile.id == profile_id).first()
    dialogs_bonus = min((profile.dialogs_started if profile else 0) * 5, 15)

    active_bonus = 0
    tod_bonus = 0.0
    if profile and profile.last_active_at:
        if profile.last_active_at >= datetime.utcnow() - timedelta(hours=6):
            active_bonus = 10
        elif profile.last_active_at >= datetime.utcnow() - timedelta(days=1):
            active_bonus = 5
        h = profile.last_active_at.hour
        if 18 <= h <= 23:
            tod_bonus = 8.0
        elif 12 <= h <= 17:
            tod_bonus = 4.0

    raw = likes_ratio * 0.6 + match_rate + dialogs_bonus + active_bonus + tod_bonus
    return round(min(raw, 100.0), 2)


def get_referral_boost(user: Optional[models.User]) -> float:
    if not user:
        return 0.0
    invited = min((user.referrals_count or 0) * 2.5, 10.0)
    joined_by_ref = 5.0 if user.referred_by_id else 0.0
    return round(min(invited + joined_by_ref, 12.0), 2)


def get_combined_score(primary: float, behavioral: float, referral_boost: float = 0.0) -> float:
    base = 0.6 * primary + 0.4 * behavioral
    return round(min(base + referral_boost, 100.0), 2)
