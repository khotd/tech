import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
import models

from config import get_sync_database_url

SYNC_URL = get_sync_database_url()
if SYNC_URL.startswith("sqlite"):
    engine = create_engine(SYNC_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(SYNC_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def ensure_tables_exist():
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        print("🗄️ Таблицы не найдены. Создаём...")
        models.Base.metadata.create_all(bind=engine)
        print("✅ Таблицы созданы")

MOCK_PROFILES = [
    {"age": 22, "gender": "Ж", "city": "Москва", "bio": "Люблю путешествия, кофе и хорошие книги 📚✈️", "photos": 4, "likes": 15, "skips": 3},
    {"age": 28, "gender": "М", "city": "Санкт-Петербург", "bio": "IT-специалист, играю на гитаре, ищу единомышленников 🎸", "photos": 5, "likes": 22, "skips": 5},
    {"age": 25, "gender": "Ж", "city": "Москва", "bio": "Фотограф, люблю закаты и спонтанные поездки 📷", "photos": 6, "likes": 30, "skips": 2},
    {"age": 30, "gender": "М", "city": "Казань", "bio": "Предприниматель, ценю честность и чувство юмора", "photos": 3, "likes": 8, "skips": 10},
    {"age": 24, "gender": "Ж", "city": "Екатеринбург", "bio": "Студентка, изучаю дизайн, мечтаю о переезде в Европу 🎨", "photos": 2, "likes": 5, "skips": 8},
    {"age": 27, "gender": "М", "city": "Москва", "bio": "Врач, люблю спорт, здоровый образ жизни и вкусную еду 🏃‍♂️", "photos": 5, "likes": 18, "skips": 4},
    {"age": 23, "gender": "Ж", "city": "Новосибирск", "bio": "Музыкант, пишу песни, ищу вдохновение в людях 🎵", "photos": 4, "likes": 12, "skips": 6},
    {"age": 29, "gender": "М", "city": "Санкт-Петербург", "bio": "Архитектор, люблю историю, искусство и долгие прогулки", "photos": 3, "likes": 10, "skips": 7},
    {"age": 26, "gender": "Ж", "city": "Москва", "bio": "Маркетолог, обожаю креатив, мемы и настольные игры 🎲", "photos": 5, "likes": 25, "skips": 3},
    {"age": 31, "gender": "М", "city": "Сочи", "bio": "Фрилансер, работаю из любой точки мира, ищу приключения 🌍", "photos": 6, "likes": 20, "skips": 5},
    {"age": 21, "gender": "Ж", "city": "Москва", "bio": "Блогер, снимаю лайфстайл, люблю моду и бьюти", "photos": 1, "likes": 3, "skips": 12},
    {"age": 35, "gender": "М", "city": "Москва", "bio": "", "photos": 0, "likes": 1, "skips": 20},
]

def create_mock(db, idx, data):
    user = models.User(
        telegram_id=9000000000 + idx,
        username=f"mock_user_{idx}",
        referral_code=f"MOCK{idx:05d}",
    )
    db.add(user)
    db.flush()
    profile = models.Profile(
        user_id=user.id,
        age=data["age"],
        gender=data["gender"],
        city=data["city"],
        bio=data["bio"],
        interests=data.get("interests", "музыка, путешествия"),
        preferred_city=data.get("preferred_city", data["city"]),
        completeness_score=calculate_completeness(data),
        is_active=True,
    )
    db.add(profile)
    db.flush()
    for i in range(data["photos"]):
        db.add(
            models.Photo(
                profile_id=profile.id,
                s3_url=f"https://example.com/mock/{idx}_{i}.jpg",
                telegram_file_id=None,
                order_index=i,
            )
        )
    db.commit()
    print(f"✅ Создан профиль #{idx}: {data['age']} лет, {data['city']}")

def calculate_completeness(data: dict) -> float:
    score = sum([bool(data["bio"] and len(data["bio"]) > 10), bool(data["age"]), bool(data["gender"]), bool(data["city"])])
    return (score / 4.0) * 100

def main():
    print("🌱 Генерация моковых данных...")
    ensure_tables_exist()
    db = SessionLocal()
    try:
        existing = db.query(models.User).filter(models.User.telegram_id >= 9000000000).count()
        if existing > 0:
            print(f"⚠️ Уже есть {existing} моковых пользователей.")
            return
        for idx, data in enumerate(MOCK_PROFILES, start=1):
            create_mock(db, idx, data)
        print(f"\n🎉 Готово! Создано {len(MOCK_PROFILES)} тестовых анкет.")
    finally:
        db.close()

if __name__ == "__main__":
    main()