from datetime import datetime, timezone

from flask_login import UserMixin
from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, Time, UniqueConstraint
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


class Product(db.Model):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    dosage_form: Mapped[str] = mapped_column(String(80), nullable=False)
    presentation: Mapped[str] = mapped_column(String(120), nullable=False)
    standard_batch_size: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class WorkShift(db.Model):
    __tablename__ = "work_shifts"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    start_time = mapped_column(Time, nullable=False)
    end_time = mapped_column(Time, nullable=False)
    planned_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ProductionOrder(db.Model):
    __tablename__ = "production_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True, nullable=False)
    planned_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    planned_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    planned_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    product: Mapped[Product] = relationship()


class ProductionBatch(db.Model):
    __tablename__ = "production_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_number: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    production_order_id: Mapped[int] = mapped_column(ForeignKey("production_orders.id", ondelete="CASCADE"), index=True, nullable=False)
    planned_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    order: Mapped[ProductionOrder] = relationship()


class ProductRouting(db.Model):
    __tablename__ = "product_routings"
    __table_args__ = (UniqueConstraint("product_id", "sequence", name="uq_product_routing_sequence"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    operation_code: Mapped[str] = mapped_column(String(40), nullable=False)
    operation_name: Mapped[str] = mapped_column(String(120), nullable=False)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id"), index=True, nullable=False)
    ideal_cycle_time_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    setup_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    product: Mapped[Product] = relationship()
    machine: Mapped[Machine] = relationship()


class ProductionRun(db.Model):
    __tablename__ = "production_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    production_order_id: Mapped[int] = mapped_column(ForeignKey("production_orders.id"), index=True, nullable=False)
    batch_id: Mapped[int] = mapped_column(ForeignKey("production_batches.id"), index=True, nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True, nullable=False)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id"), index=True, nullable=False)
    shift_id: Mapped[int] = mapped_column(ForeignKey("work_shifts.id"), index=True, nullable=False)
    operation_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    planned_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    ideal_cycle_time_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    machine: Mapped[Machine] = relationship()
    shift: Mapped[WorkShift] = relationship()
    product: Mapped[Product] = relationship()
    batch: Mapped[ProductionBatch] = relationship()


class ProductionCounter(db.Model):
    __tablename__ = "production_counters"
    id: Mapped[int] = mapped_column(primary_key=True)
    production_run_id: Mapped[int] = mapped_column(ForeignKey("production_runs.id", ondelete="CASCADE"), index=True, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    total_units: Mapped[int] = mapped_column(Integer, nullable=False)
    good_units: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected_units: Mapped[int] = mapped_column(Integer, nullable=False)
    rework_units: Mapped[int] = mapped_column(Integer, nullable=False)


class MachineDowntimeEvent(db.Model):
    __tablename__ = "machine_downtime_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    production_run_id: Mapped[int] = mapped_column(ForeignKey("production_runs.id", ondelete="CASCADE"), index=True, nullable=False)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id"), index=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[float] = mapped_column(Float, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    reason_description: Mapped[str] = mapped_column(String(180), nullable=False)
    category: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    is_planned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class OEEResult(db.Model):
    __tablename__ = "oee_results"
    __table_args__ = (UniqueConstraint("production_run_id", name="uq_oee_result_run"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    production_run_id: Mapped[int] = mapped_column(ForeignKey("production_runs.id", ondelete="CASCADE"), index=True, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    availability: Mapped[float] = mapped_column(Float, nullable=False)
    performance: Mapped[float] = mapped_column(Float, nullable=False)
    quality: Mapped[float] = mapped_column(Float, nullable=False)
    oee: Mapped[float] = mapped_column(Float, index=True, nullable=False)
    operating_minutes: Mapped[float] = mapped_column(Float, nullable=False)
    downtime_minutes: Mapped[float] = mapped_column(Float, nullable=False)
    total_units: Mapped[int] = mapped_column(Integer, nullable=False)
    good_units: Mapped[int] = mapped_column(Integer, nullable=False)
    run: Mapped[ProductionRun] = relationship()
