from datetime import datetime, timezone

from flask_login import UserMixin
from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_reset_token(self):
        serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
        return serializer.dumps(
            {"user_id": self.id, "password_version": self.password_hash[-20:]},
            salt="password-reset",
        )

    @staticmethod
    def verify_reset_token(token, max_age=3600):
        serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
        try:
            data = serializer.loads(token, salt="password-reset", max_age=max_age)
        except (BadSignature, SignatureExpired):
            return None
        user = db.session.get(User, data.get("user_id"))
        if not user or user.password_hash[-20:] != data.get("password_version"):
            return None
        return user


class SOPChunk(db.Model):
    __tablename__ = "sop_chunks"
    __table_args__ = (UniqueConstraint("document_hash", "page", "chunk_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    document_name: Mapped[str] = mapped_column(String(255), nullable=False)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list] = mapped_column(Vector(768), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class Machine(db.Model):
    __tablename__ = "machines"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    machine_type: Mapped[str] = mapped_column(String(100), nullable=False)
    area: Mapped[str] = mapped_column(String(100), nullable=False)
    max_usage_hours: Mapped[float] = mapped_column(Float, nullable=False)
    max_vibration: Mapped[float] = mapped_column(Float, nullable=False)
    max_temperature: Mapped[float] = mapped_column(Float, nullable=False)
    rated_current: Mapped[float] = mapped_column(Float, nullable=False)
    nominal_rpm: Mapped[float] = mapped_column(Float, nullable=False)
    max_pressure: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    readings: Mapped[list["MachineReading"]] = relationship(
        back_populates="machine", cascade="all, delete-orphan"
    )


class MachineReading(db.Model):
    __tablename__ = "machine_readings"
    __table_args__ = (UniqueConstraint("machine_id", "recorded_at", name="uq_machine_reading_time"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    machine_id: Mapped[int] = mapped_column(
        ForeignKey("machines.id", ondelete="CASCADE"), index=True, nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True, nullable=False
    )
    usage_hours: Mapped[float] = mapped_column(Float, nullable=False)
    vibration: Mapped[float] = mapped_column(Float, nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    current: Mapped[float] = mapped_column(Float, nullable=False)
    rpm: Mapped[float] = mapped_column(Float, nullable=False)
    pressure: Mapped[float] = mapped_column(Float, nullable=False)
    failure_probability: Mapped[float] = mapped_column(Float, nullable=False)
    health_status: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    explanation: Mapped[str] = mapped_column(String(500), nullable=False)
    machine: Mapped[Machine] = relationship(back_populates="readings")
