import random
from datetime import datetime, time as clock_time, timedelta, timezone

from extensions import db
from models import (Machine, MachineDowntimeEvent, OEEResult, Product,
                    ProductionBatch, ProductionCounter, ProductionOrder,
                    ProductionRun, ProductRouting, WorkShift)
from predictive_service import CONDITION_PROFILES, seed_demo_machines


PRODUCTS = [
    ("PRD-001", "Tabletas analgésicas 500 mg", "Tableta", "Blíster x 10", 120000),
    ("PRD-002", "Tabletas recubiertas 250 mg", "Tableta", "Frasco x 100", 90000),
    ("PRD-003", "Cápsulas 250 mg", "Cápsula", "Blíster x 10", 100000),
    ("PRD-004", "Suspensión oral 120 ml", "Suspensión", "Frasco x 120 ml", 30000),
    ("PRD-005", "Solución estéril 10 ml", "Solución", "Vial x 10 ml", 24000),
    ("PRD-006", "Granulado 5 g", "Granulado", "Sobre x 5 g", 75000),
    ("PRD-007", "Tabletas liberación prolongada", "Tableta", "Blíster x 14", 80000),
    ("PRD-008", "Cápsulas gastrorresistentes", "Cápsula", "Frasco x 30", 65000),
]

SHIFTS = [("T1", "Mañana", clock_time(6), clock_time(14)), ("T2", "Tarde", clock_time(14), clock_time(22)), ("T3", "Noche", clock_time(22), clock_time(6))]
REASONS = [("BRK", "Avería mecánica", "Avería"), ("SET", "Cambio de formato", "Configuración"), ("MAT", "Falta de material", "Materiales"), ("MIC", "Microparada", "Microparada"), ("QAI", "Espera de control de calidad", "Calidad")]


def calculate_oee(planned_minutes, downtime_minutes, ideal_cycle_seconds, total_units, good_units):
    operating = max(0.0, planned_minutes - downtime_minutes)
    availability = min(1.0, operating / planned_minutes) if planned_minutes else 0.0
    ideal_output = operating * 60 / ideal_cycle_seconds if ideal_cycle_seconds else 0.0
    performance = min(1.0, total_units / ideal_output) if ideal_output else 0.0
    quality = min(1.0, good_units / total_units) if total_units else 0.0
    return tuple(round(value * 100, 2) for value in (availability, performance, quality, availability * performance * quality)) + (round(operating, 2),)


def seed_oee_demo(days=30, seed=2026):
    seed_demo_machines()
    rng = random.Random(seed)
    products = []
    for spec in PRODUCTS:
        product = db.session.scalar(db.select(Product).where(Product.code == spec[0]))
        if not product:
            product = Product(code=spec[0], name=spec[1], dosage_form=spec[2], presentation=spec[3], standard_batch_size=spec[4], active=True)
            db.session.add(product)
        products.append(product)
    shifts = []
    for code, name, start, end in SHIFTS:
        shift = db.session.scalar(db.select(WorkShift).where(WorkShift.code == code))
        if not shift:
            shift = WorkShift(code=code, name=name, start_time=start, end_time=end, planned_minutes=480, active=True)
            db.session.add(shift)
        shifts.append(shift)
    db.session.flush()

    machines = db.session.scalars(db.select(Machine).order_by(Machine.id)).all()
    for index, machine in enumerate(machines):
        product = products[index % len(products)]
        if not db.session.scalar(db.select(ProductRouting.id).where(ProductRouting.product_id == product.id, ProductRouting.machine_id == machine.id)):
            sequence = (index // len(products) + 1) * 10
            db.session.add(ProductRouting(product_id=product.id, sequence=sequence, operation_code=f"OP-{sequence:03d}", operation_name=machine.area, machine_id=machine.id, ideal_cycle_time_seconds=round(1.1 + index * 0.11, 2), setup_minutes=30 + index % 4 * 10))
    db.session.flush()

    orders, batches = {}, {}
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    for index, product in enumerate(products):
        number = f"OP-{now.year}-{index + 1:04d}"
        order = db.session.scalar(db.select(ProductionOrder).where(ProductionOrder.order_number == number))
        if not order:
            order = ProductionOrder(order_number=number, product_id=product.id, planned_quantity=product.standard_batch_size * 4, planned_start=now - timedelta(days=days), planned_end=now + timedelta(days=5), status="In Progress", priority="High" if index < 2 else "Normal")
            db.session.add(order); db.session.flush()
        batch_number = f"LOT-{now.year}-{index + 1:04d}"
        batch = db.session.scalar(db.select(ProductionBatch).where(ProductionBatch.batch_number == batch_number))
        if not batch:
            batch = ProductionBatch(batch_number=batch_number, production_order_id=order.id, planned_quantity=product.standard_batch_size, actual_quantity=0, started_at=now - timedelta(days=days), status="In Progress")
            db.session.add(batch); db.session.flush()
        orders[product.id], batches[product.id] = order, batch

    if db.session.scalar(db.select(db.func.count(OEEResult.id))):
        db.session.commit()
        return {"products": len(products), "shifts": len(shifts), "orders": len(orders), "runs": 0}

    inserted = 0
    start_day = (now - timedelta(days=days)).replace(hour=6)
    for day in range(days):
        for index, machine in enumerate(machines):
            product = products[index % len(products)]
            shift = shifts[(day + index) % len(shifts)]
            started = start_day + timedelta(days=day, hours=(0, 8, 16)[shifts.index(shift)])
            planned = 450
            risk_level = CONDITION_PROFILES[index % len(CONDITION_PROFILES)]
            downtime = round(rng.uniform(8, 30) + risk_level * rng.uniform(15, 75), 1)
            ideal_cycle = round(1.1 + index * 0.11, 2)
            availability_target = max(0.55, 1 - downtime / planned)
            performance_target = max(0.60, min(0.98, 0.96 - risk_level * 0.18 + rng.uniform(-0.04, 0.04)))
            quality_target = max(0.88, min(0.999, 0.995 - risk_level * 0.055 + rng.uniform(-0.008, 0.006)))
            operating = planned * availability_target
            total = max(1, int(operating * 60 / ideal_cycle * performance_target))
            good = max(0, int(total * quality_target))
            run = ProductionRun(production_order_id=orders[product.id].id, batch_id=batches[product.id].id, product_id=product.id, machine_id=machine.id, shift_id=shift.id, operation_sequence=(index // len(products) + 1) * 10, started_at=started, ended_at=started + timedelta(minutes=planned), planned_minutes=planned, ideal_cycle_time_seconds=ideal_cycle, status="Completed")
            db.session.add(run); db.session.flush()
            db.session.add(ProductionCounter(production_run_id=run.id, recorded_at=run.ended_at, total_units=total, good_units=good, rejected_units=total-good, rework_units=int((total-good)*0.15)))
            reason = REASONS[(day + index) % len(REASONS)]
            db.session.add(MachineDowntimeEvent(production_run_id=run.id, machine_id=machine.id, started_at=started + timedelta(minutes=120), ended_at=started + timedelta(minutes=120+downtime), duration_minutes=downtime, reason_code=reason[0], reason_description=reason[1], category=reason[2], is_planned=reason[0] == "SET"))
            availability, performance, quality, oee, operating_minutes = calculate_oee(planned, downtime, ideal_cycle, total, good)
            db.session.add(OEEResult(production_run_id=run.id, calculated_at=run.ended_at, availability=availability, performance=performance, quality=quality, oee=oee, operating_minutes=operating_minutes, downtime_minutes=downtime, total_units=total, good_units=good))
            inserted += 1
    db.session.commit()
    return {"products": len(products), "shifts": len(shifts), "orders": len(orders), "runs": inserted}


def oee_dashboard_data(days=7):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.session.execute(db.select(Machine, OEEResult, ProductionRun).join(ProductionRun, ProductionRun.machine_id == Machine.id).join(OEEResult, OEEResult.production_run_id == ProductionRun.id).where(ProductionRun.started_at >= since).order_by(ProductionRun.started_at.desc())).all()
    if not rows:
        return {"summary": {"oee": 0, "availability": 0, "performance": 0, "quality": 0, "runs": 0}, "machines": [], "losses": []}
    grouped = {}
    for machine, result, run in rows:
        grouped.setdefault(machine.code, {"machine": machine, "results": []})["results"].append(result)
    machines = []
    for item in grouped.values():
        results = item["results"]
        avg = lambda field: round(sum(getattr(r, field) for r in results) / len(results), 1)
        oee = avg("oee")
        machines.append({"code": item["machine"].code, "name": item["machine"].name, "area": item["machine"].area, "oee": oee, "availability": avg("availability"), "performance": avg("performance"), "quality": avg("quality"), "status": "Excellent" if oee >= 85 else "Healthy" if oee >= 70 else "Warning" if oee >= 50 else "Critical"})
    machines.sort(key=lambda row: row["oee"])
    all_results = [row[1] for row in rows]
    avg_all = lambda field: round(sum(getattr(r, field) for r in all_results) / len(all_results), 1)
    losses = db.session.execute(db.select(MachineDowntimeEvent.category, db.func.sum(MachineDowntimeEvent.duration_minutes)).join(ProductionRun, ProductionRun.id == MachineDowntimeEvent.production_run_id).where(ProductionRun.started_at >= since).group_by(MachineDowntimeEvent.category).order_by(db.func.sum(MachineDowntimeEvent.duration_minutes).desc())).all()
    return {"summary": {"oee": avg_all("oee"), "availability": avg_all("availability"), "performance": avg_all("performance"), "quality": avg_all("quality"), "runs": len(rows)}, "machines": machines, "losses": [{"category": category, "minutes": round(minutes, 1)} for category, minutes in losses]}
