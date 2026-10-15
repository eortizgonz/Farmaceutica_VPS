import math
import random
from datetime import datetime, timedelta, timezone

from extensions import db
from models import Machine, MachineReading


MACHINE_CATALOG = [
    ("MX-750", "Mezcladora de alto cizallamiento", "Granulación", 9000, 7.1, 75, 42, 1200, 2.8),
    ("BX-200", "Empacadora blíster", "Empaque", 11000, 6.5, 70, 32, 900, 6.0),
    ("R-500", "Reactor de proceso", "Fabricación", 12000, 6.0, 135, 55, 320, 5.5),
    ("CT-900", "Tableteadora rotativa", "Compresión", 10000, 7.0, 78, 48, 1100, 3.5),
    ("RC-600", "Recubridora automática", "Recubrimiento", 8500, 6.2, 80, 38, 600, 3.0),
    ("LF-400", "Secador de lecho fluido", "Secado", 9500, 6.0, 95, 50, 1450, 2.6),
    ("TB-120", "Tamizadora vibratoria", "Dispensación", 7500, 8.0, 65, 24, 1500, 1.2),
    ("CB-02", "Cabina de dispensación", "Dispensación", 14000, 5.0, 55, 28, 1750, 0.9),
    ("GR-310", "Granulador oscilante", "Granulación", 8000, 7.5, 72, 30, 950, 1.8),
    ("CP-450", "Comprimidora de laboratorio", "Compresión", 6500, 6.8, 74, 22, 800, 2.2),
    ("ET-210", "Etiquetadora automática", "Empaque", 10500, 5.8, 62, 18, 1250, 5.0),
    ("EN-330", "Encartonadora horizontal", "Empaque", 10000, 6.2, 68, 26, 1000, 5.0),
    ("LV-700", "Lavadora de contenedores", "Lavado", 12000, 6.0, 92, 44, 700, 4.0),
    ("AU-150", "Autoclave de vapor", "Esterilización", 15000, 5.5, 145, 60, 500, 3.2),
    ("BO-850", "Bomba de transferencia", "Fabricación", 9000, 7.2, 88, 35, 1800, 6.5),
    ("CO-110", "Compresor de aire limpio", "Servicios", 16000, 7.0, 98, 75, 1750, 8.0),
    ("CH-420", "Chiller de proceso", "Servicios", 14500, 6.0, 82, 68, 1450, 5.0),
    ("EX-510", "Extractor de polvo", "Compresión", 11500, 6.8, 76, 40, 1650, 2.0),
    ("BL-280", "Balanza industrial", "Dispensación", 18000, 2.0, 50, 5, 1, 0.2),
    ("IN-640", "Inspector visual automático", "Calidad", 9500, 4.8, 60, 20, 750, 1.0),
]

CONDITION_PROFILES = [
    0.28, 0.82, 0.48, 0.94, 0.36, 0.69, 0.22, 0.57, 0.76, 0.31,
    0.44, 0.88, 0.25, 0.63, 0.72, 0.39, 0.91, 0.53, 0.18, 0.66,
]

# Pesos aprobados para el índice demostrativo. Deben sumar 1.0.
RISK_WEIGHTS = {
    "horas de uso": 0.12,
    "vibración": 0.25,
    "temperatura": 0.20,
    "corriente": 0.17,
    "desviación de RPM": 0.14,
    "presión": 0.12,
}

STATUS_THRESHOLDS = {"warning": 40.0, "critical": 70.0}


def _rule_score(ratio):
    """Convierte el porcentaje del límite en severidad de 0 a 100."""
    ratio = max(0.0, ratio)
    if ratio <= 0.60:
        return 0.0
    if ratio <= 0.80:
        return (ratio - 0.60) / 0.20 * 25.0
    if ratio <= 1.00:
        return 25.0 + (ratio - 0.80) / 0.20 * 45.0
    if ratio <= 1.15:
        return 70.0 + (ratio - 1.00) / 0.15 * 30.0
    return 100.0


def calculate_risk(machine, values):
    rpm_deviation = abs(values["rpm"] - machine.nominal_rpm) / max(machine.nominal_rpm, 1)
    ratios = {
        "horas de uso": values["usage_hours"] / machine.max_usage_hours,
        "vibración": values["vibration"] / machine.max_vibration,
        "temperatura": values["temperature"] / machine.max_temperature,
        "corriente": values["current"] / machine.rated_current,
        # Una desviación de 20% equivale al 100% del límite de esta regla.
        "desviación de RPM": rpm_deviation / 0.20,
        "presión": values["pressure"] / machine.max_pressure,
    }
    scores = {key: _rule_score(value) for key, value in ratios.items()}
    contributions = {key: scores[key] * RISK_WEIGHTS[key] for key in scores}
    risk = sum(contributions.values())

    # Reglas de escalamiento para que un límite excedido no quede oculto por el promedio.
    exceeded = sum(ratio >= 1.0 for ratio in ratios.values())
    if any(ratio >= 1.15 for ratio in ratios.values()):
        risk = max(risk, 75.0)
    elif exceeded >= 2:
        risk = max(risk, 70.0)
    elif exceeded == 1:
        risk = max(risk, 45.0)

    risk = min(99.0, max(1.0, risk))
    status = ("Critical" if risk >= STATUS_THRESHOLDS["critical"] else
              "Warning" if risk >= STATUS_THRESHOLDS["warning"] else "Healthy")
    drivers = sorted(contributions, key=contributions.get, reverse=True)[:2]
    explanation = (
        f"Factores principales: {drivers[0]} ({contributions[drivers[0]]:.1f} puntos) "
        f"y {drivers[1]} ({contributions[drivers[1]]:.1f} puntos)."
    )
    return round(risk, 1), status, explanation


def _bounded(value, lower, upper, decimals=2):
    return round(max(lower, min(upper, value)), decimals)


def _as_utc(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def _values_from_condition(machine, level, rng, usage_hours=None, phase=0.0):
    """Genera variables correlacionadas sin sobrepasar 115% de los límites."""
    cycle = math.sin(phase) * 0.035
    load = max(0.12, min(1.08, level + cycle + rng.gauss(0, 0.025)))
    anomaly = rng.uniform(0.06, 0.14) if rng.random() < 0.025 else 0.0
    load = min(1.12, load + anomaly)
    direction = -1 if rng.random() < 0.5 else 1
    hours = usage_hours if usage_hours is not None else machine.max_usage_hours * (0.30 + load * 0.70)
    return {
        "usage_hours": _bounded(hours, 0, machine.max_usage_hours * 1.15, 1),
        "vibration": _bounded(machine.max_vibration * (0.30 + load * 0.72) + rng.gauss(0, machine.max_vibration * 0.015), 0, machine.max_vibration * 1.15),
        "temperature": _bounded(machine.max_temperature * (0.42 + load * 0.61) + rng.gauss(0, machine.max_temperature * 0.01), 0, machine.max_temperature * 1.15, 1),
        "current": _bounded(machine.rated_current * (0.36 + load * 0.68) + rng.gauss(0, machine.rated_current * 0.012), 0, machine.rated_current * 1.15, 1),
        "rpm": _bounded(machine.nominal_rpm * (1 + direction * load * 0.20) + rng.gauss(0, max(machine.nominal_rpm * 0.008, 0.1)), machine.nominal_rpm * 0.72, machine.nominal_rpm * 1.28, 0),
        "pressure": _bounded(machine.max_pressure * (0.34 + load * 0.70) + rng.gauss(0, machine.max_pressure * 0.012), 0, machine.max_pressure * 1.15),
    }


def _add_reading(machine, recorded_at, values):
    risk, status, explanation = calculate_risk(machine, values)
    db.session.add(MachineReading(
        machine_id=machine.id, recorded_at=recorded_at,
        failure_probability=risk, health_status=status,
        explanation=explanation, **values,
    ))


def seed_demo_machines():
    for index, spec in enumerate(MACHINE_CATALOG):
        code, name, area, hours, vibration, temperature, current, rpm, pressure = spec
        machine = db.session.scalar(db.select(Machine).where(Machine.code == code))
        if not machine:
            machine = Machine(
                code=code, name=name, machine_type=name.split()[0], area=area,
                max_usage_hours=hours, max_vibration=vibration,
                max_temperature=temperature, rated_current=current,
                nominal_rpm=rpm, max_pressure=pressure,
            )
            db.session.add(machine)
            db.session.flush()
        exists = db.session.scalar(
            db.select(db.func.count(MachineReading.id)).where(MachineReading.machine_id == machine.id)
        )
        if not exists:
            rng = random.Random(2026 + index)
            values = _values_from_condition(machine, CONDITION_PROFILES[index], rng)
            _add_reading(machine, datetime.now(timezone.utc), values)
    db.session.commit()
    return len(MACHINE_CATALOG)


def append_simulated_snapshot(recorded_at=None, seed=None):
    """Agrega una lectura posterior por máquina sin eliminar el historial."""
    recorded_at = recorded_at or datetime.now(timezone.utc)
    rng = random.Random(seed)
    machines = db.session.scalars(db.select(Machine).order_by(Machine.id)).all()
    if not machines:
        raise ValueError("Primero debe ejecutar seed-predictive-data.")
    inserted = 0
    for index, machine in enumerate(machines):
        latest = db.session.scalar(
            db.select(MachineReading)
            .where(MachineReading.machine_id == machine.id)
            .order_by(MachineReading.recorded_at.desc()).limit(1)
        )
        elapsed = max(0.0, (recorded_at - _as_utc(latest.recorded_at)).total_seconds() / 3600) if latest else 0
        level = CONDITION_PROFILES[index % len(CONDITION_PROFILES)]
        usage = (latest.usage_hours + elapsed) if latest else None
        if latest:
            observed_load = max(latest.vibration / machine.max_vibration, latest.temperature / machine.max_temperature)
            level = max(0.1, min(1.08, (observed_load - 0.30) / 0.72 + rng.gauss(0, 0.018)))
        values = _values_from_condition(machine, level, rng, usage, recorded_at.timestamp() / 86400 * math.tau)
        _add_reading(machine, recorded_at, values)
        inserted += 1
    db.session.commit()
    return inserted


def backfill_simulated_history(days=90, interval_minutes=60, seed=2026):
    """Completa el historial anterior a la primera lectura; repetirlo no duplica datos."""
    if days < 1 or interval_minutes < 5:
        raise ValueError("days debe ser >= 1 e interval_minutes >= 5.")
    machines = db.session.scalars(db.select(Machine).order_by(Machine.id)).all()
    if not machines:
        raise ValueError("Primero debe ejecutar seed-predictive-data.")
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    requested_start = now - timedelta(days=days)
    step = timedelta(minutes=interval_minutes)
    inserted = 0
    for index, machine in enumerate(machines):
        first_at = _as_utc(db.session.scalar(
            db.select(db.func.min(MachineReading.recorded_at))
            .where(MachineReading.machine_id == machine.id)
        )) or now
        cursor = requested_start
        rng = random.Random(seed + machine.id)
        total_hours = max(1.0, (first_at - requested_start).total_seconds() / 3600)
        end_usage = machine.max_usage_hours * (0.30 + CONDITION_PROFILES[index] * 0.70)
        while cursor < first_at:
            progress = max(0.0, min(1.0, (cursor - requested_start).total_seconds() / max((first_at - requested_start).total_seconds(), 1)))
            level = max(0.10, CONDITION_PROFILES[index] * (0.72 + 0.28 * progress))
            usage = max(0.0, end_usage - total_hours + progress * total_hours)
            values = _values_from_condition(machine, level, rng, usage, cursor.timestamp() / 86400 * math.tau)
            _add_reading(machine, cursor, values)
            inserted += 1
            cursor += step
        db.session.flush()
    db.session.commit()
    return inserted


def recalculate_historical_risks(batch_size=1000):
    """Aplica las reglas vigentes a todas las lecturas ya almacenadas."""
    last_id = 0
    updated = 0
    while True:
        readings = db.session.scalars(
            db.select(MachineReading)
            .where(MachineReading.id > last_id)
            .order_by(MachineReading.id)
            .limit(batch_size)
        ).all()
        if not readings:
            break
        for reading in readings:
            values = {
                "usage_hours": reading.usage_hours,
                "vibration": reading.vibration,
                "temperature": reading.temperature,
                "current": reading.current,
                "rpm": reading.rpm,
                "pressure": reading.pressure,
            }
            risk, status, explanation = calculate_risk(reading.machine, values)
            reading.failure_probability = risk
            reading.health_status = status
            reading.explanation = explanation
            last_id = reading.id
            updated += 1
        db.session.commit()
    return updated


def latest_machine_snapshot():
    latest = (
        db.select(MachineReading.machine_id, db.func.max(MachineReading.recorded_at).label("latest"))
        .group_by(MachineReading.machine_id).subquery()
    )
    return db.session.execute(
        db.select(Machine, MachineReading)
        .join(MachineReading, MachineReading.machine_id == Machine.id)
        .join(latest, (latest.c.machine_id == MachineReading.machine_id) &
              (latest.c.latest == MachineReading.recorded_at))
        .order_by(MachineReading.failure_probability.desc())
    ).all()
