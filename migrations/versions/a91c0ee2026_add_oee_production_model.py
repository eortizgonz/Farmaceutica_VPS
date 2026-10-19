"""add OEE production model

Revision ID: a91c0ee2026
Revises: f273b8ac501d
"""

from alembic import op
import sqlalchemy as sa

revision = "a91c0ee2026"
down_revision = "f273b8ac501d"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("products", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("code", sa.String(40), nullable=False), sa.Column("name", sa.String(140), nullable=False), sa.Column("dosage_form", sa.String(80), nullable=False), sa.Column("presentation", sa.String(120), nullable=False), sa.Column("standard_batch_size", sa.Integer(), nullable=False), sa.Column("active", sa.Boolean(), nullable=False))
    op.create_index("ix_products_code", "products", ["code"], unique=True)
    op.create_table("work_shifts", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("code", sa.String(20), nullable=False, unique=True), sa.Column("name", sa.String(60), nullable=False), sa.Column("start_time", sa.Time(), nullable=False), sa.Column("end_time", sa.Time(), nullable=False), sa.Column("planned_minutes", sa.Integer(), nullable=False), sa.Column("active", sa.Boolean(), nullable=False))
    op.create_table("production_orders", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("order_number", sa.String(40), nullable=False), sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False), sa.Column("planned_quantity", sa.Integer(), nullable=False), sa.Column("planned_start", sa.DateTime(timezone=True), nullable=False), sa.Column("planned_end", sa.DateTime(timezone=True), nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("priority", sa.String(20), nullable=False))
    op.create_index("ix_production_orders_order_number", "production_orders", ["order_number"], unique=True); op.create_index("ix_production_orders_product_id", "production_orders", ["product_id"]); op.create_index("ix_production_orders_status", "production_orders", ["status"])
    op.create_table("production_batches", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("batch_number", sa.String(50), nullable=False), sa.Column("production_order_id", sa.Integer(), sa.ForeignKey("production_orders.id", ondelete="CASCADE"), nullable=False), sa.Column("planned_quantity", sa.Integer(), nullable=False), sa.Column("actual_quantity", sa.Integer(), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("status", sa.String(30), nullable=False))
    op.create_index("ix_production_batches_batch_number", "production_batches", ["batch_number"], unique=True); op.create_index("ix_production_batches_production_order_id", "production_batches", ["production_order_id"]); op.create_index("ix_production_batches_status", "production_batches", ["status"])
    op.create_table("product_routings", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False), sa.Column("sequence", sa.Integer(), nullable=False), sa.Column("operation_code", sa.String(40), nullable=False), sa.Column("operation_name", sa.String(120), nullable=False), sa.Column("machine_id", sa.Integer(), sa.ForeignKey("machines.id"), nullable=False), sa.Column("ideal_cycle_time_seconds", sa.Float(), nullable=False), sa.Column("setup_minutes", sa.Integer(), nullable=False), sa.UniqueConstraint("product_id", "sequence", name="uq_product_routing_sequence"))
    op.create_index("ix_product_routings_product_id", "product_routings", ["product_id"]); op.create_index("ix_product_routings_machine_id", "product_routings", ["machine_id"])
    op.create_table("production_runs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("production_order_id", sa.Integer(), sa.ForeignKey("production_orders.id"), nullable=False), sa.Column("batch_id", sa.Integer(), sa.ForeignKey("production_batches.id"), nullable=False), sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False), sa.Column("machine_id", sa.Integer(), sa.ForeignKey("machines.id"), nullable=False), sa.Column("shift_id", sa.Integer(), sa.ForeignKey("work_shifts.id"), nullable=False), sa.Column("operation_sequence", sa.Integer(), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True), nullable=False), sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False), sa.Column("planned_minutes", sa.Integer(), nullable=False), sa.Column("ideal_cycle_time_seconds", sa.Float(), nullable=False), sa.Column("status", sa.String(30), nullable=False))
    for col in ("production_order_id", "batch_id", "product_id", "machine_id", "shift_id", "started_at"): op.create_index(f"ix_production_runs_{col}", "production_runs", [col])
    op.create_table("production_counters", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("production_run_id", sa.Integer(), sa.ForeignKey("production_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False), sa.Column("total_units", sa.Integer(), nullable=False), sa.Column("good_units", sa.Integer(), nullable=False), sa.Column("rejected_units", sa.Integer(), nullable=False), sa.Column("rework_units", sa.Integer(), nullable=False))
    op.create_index("ix_production_counters_production_run_id", "production_counters", ["production_run_id"]); op.create_index("ix_production_counters_recorded_at", "production_counters", ["recorded_at"])
    op.create_table("machine_downtime_events", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("production_run_id", sa.Integer(), sa.ForeignKey("production_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("machine_id", sa.Integer(), sa.ForeignKey("machines.id"), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True), nullable=False), sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False), sa.Column("duration_minutes", sa.Float(), nullable=False), sa.Column("reason_code", sa.String(40), nullable=False), sa.Column("reason_description", sa.String(180), nullable=False), sa.Column("category", sa.String(60), nullable=False), sa.Column("is_planned", sa.Boolean(), nullable=False))
    for col in ("production_run_id", "machine_id", "reason_code", "category"): op.create_index(f"ix_machine_downtime_events_{col}", "machine_downtime_events", [col])
    op.create_table("oee_results", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("production_run_id", sa.Integer(), sa.ForeignKey("production_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("availability", sa.Float(), nullable=False), sa.Column("performance", sa.Float(), nullable=False), sa.Column("quality", sa.Float(), nullable=False), sa.Column("oee", sa.Float(), nullable=False), sa.Column("operating_minutes", sa.Float(), nullable=False), sa.Column("downtime_minutes", sa.Float(), nullable=False), sa.Column("total_units", sa.Integer(), nullable=False), sa.Column("good_units", sa.Integer(), nullable=False), sa.UniqueConstraint("production_run_id", name="uq_oee_result_run"))
    op.create_index("ix_oee_results_production_run_id", "oee_results", ["production_run_id"]); op.create_index("ix_oee_results_oee", "oee_results", ["oee"])


def downgrade():
    for table in ("oee_results", "machine_downtime_events", "production_counters", "production_runs", "product_routings", "production_batches", "production_orders", "work_shifts", "products"):
        op.drop_table(table)
