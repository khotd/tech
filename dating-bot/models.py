"""
Модели базы данных
"""
from sqlalchemy import Column, BigInteger, String, Text, Integer, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    profile = relationship("Profile", back_populates="user", uselist=False)

class Profile(Base):
    __tablename__ = "profiles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), default="") 
    bio = Column(Text, default="")
    age = Column(Integer)
    gender = Column(String(50))
    city = Column(String(255))
    preferred_gender = Column(String(50), default="any")
    preferred_age_min = Column(Integer, default=18)
    preferred_age_max = Column(Integer, default=100)
    completeness_score = Column(Float, default=0.0)
    rating_score = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    dialogs_started = Column(Integer, default=0)
    last_active_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="profile")
    photos = relationship("Photo", back_populates="profile", cascade="all, delete-orphan")
    likes_given = relationship("Like", foreign_keys="Like.from_id", back_populates="from_profile")
    likes_received = relationship("Like", foreign_keys="Like.to_id", back_populates="to_profile")

class Photo(Base):
    __tablename__ = "photos"
    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=False)
    s3_url = Column(String(500))
    order_index = Column(Integer, default=0)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    profile = relationship("Profile", back_populates="photos")

class Like(Base):
    __tablename__ = "likes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    from_id = Column(Integer, ForeignKey("profiles.id"), nullable=False)
    to_id = Column(Integer, ForeignKey("profiles.id"), nullable=False)
    action = Column(String(50))  # 'like', 'skip'
    created_at = Column(DateTime, default=datetime.utcnow)
    from_profile = relationship("Profile", foreign_keys=[from_id], back_populates="likes_given")
    to_profile = relationship("Profile", foreign_keys=[to_id], back_populates="likes_received")


class ProfileRating(Base):
    __tablename__ = "profile_ratings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=False, index=True)
    primary_score = Column(Float, default=0.0)
    behavioral_score = Column(Float, default=0.0)
    combined_score = Column(Float, default=0.0, index=True)
    calculated_at = Column(DateTime, default=datetime.utcnow)