import unicodedata
from datetime import timedelta

from flask import current_app

from extensions import db
from models import Machine, MachineReading
from predictive_service import RISK_WEIGHTS, STATUS_THRESHOLDS, latest_machine_snapshot
from rag_service import _ollama


def _normalize(value):
    return "".join(
        character for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character)
    )


def _mentioned_machines(question, machines):
    normalized = _normalize(question)
    selected = []
    for machine in machines:
        code = machine.code.casefold()
        meaningful_words = [word for word in _normalize(machine.name).split() if len(word) >= 6]
        if code in normalized or any(word in normalized for word in meaningful_words):
            selected.append(machine)
    return selected[:4]


def _trend_context(machine, latest_reading):
    start = latest_reading.recorded_at - timedelta(hours=24)
    aggregate = db.session.execute(
        db.select(
            db.func.count(MachineReading.id),
            db.func.avg(MachineReading.failure_probability),
            db.func.min(MachineReading.failure_probability),
            db.func.max(MachineReading.failure_probability),
            db.func.avg(MachineReading.temperature),
            db.func.avg(MachineReading.vibration),
        ).where(
            MachineReading.machine_id == machine.id,
            MachineReading.recorded_at >= start,
            MachineReading.recorded_at <= latest_reading.recorded_at,
        )
    ).one()
    first = db.session.scalar(
        db.select(MachineReading)
        .where(
            MachineReading.machine_id == machine.id,
            MachineReading.recorded_at >= start,
            MachineReading.recorded_at <= latest_reading.recorded_at,
        )
        .order_by(MachineReading.recorded_at.asc()).limit(1)
    )
    change = latest_reading.failure_probability - first.failure_probability if first else 0
    direction = "aumentó" if change > 0.05 else "disminuyó" if change < -0.05 else "se mantuvo estable"
    return (
        f"Tendencia 24 h de {machine.code}: {aggregate[0]} lecturas; riesgo promedio "
        f"{float(aggregate[1] or 0):.1f}%, mínimo {float(aggregate[2] or 0):.1f}%, "
        f"máximo {float(aggregate[3] or 0):.1f}%. Desde la primera lectura hasta la actual "
        f"el riesgo {direction} {abs(change):.1f} puntos; "
        f"temperatura media {float(aggregate[4] or 0):.1f} °C y vibración media "
        f"{float(aggregate[5] or 0):.2f} mm/s."
    )


def answer_predictive_question(question):
    rows = latest_machine_snapshot()
    if not rows:
        raise ValueError("No existen lecturas predictivas para consultar.")

    machines = [machine for machine, _ in rows]
    latest_by_id = {machine.id: reading for machine, reading in rows}
    selected = _mentioned_machines(question, machines)
    counts = {"Healthy": 0, "Warning": 0, "Critical": 0}
    for _, reading in rows:
        counts[reading.health_status] += 1
    average = sum(reading.failure_probability for _, reading in rows) / len(rows)

    rules = ", ".join(f"{name} {weight * 100:.0f}%" for name, weight in RISK_WEIGHTS.items())
    context = [
        f"Modelo: índice demostrativo, no probabilidad estadística validada. Pesos: {rules}.",
        f"Estados: Healthy < {STATUS_THRESHOLDS['warning']:.0f}%; Warning desde "
        f"{STATUS_THRESHOLDS['warning']:.0f}% y Critical desde {STATUS_THRESHOLDS['critical']:.0f}%.",
        f"Resumen actual: {counts['Healthy']} Healthy, {counts['Warning']} Warning, "
        f"{counts['Critical']} Critical; riesgo promedio {average:.1f}%.",
        "Equipos con mayor riesgo:",
    ]
    for machine, reading in rows[:5]:
        context.append(
            f"- {machine.code} ({machine.name}, {machine.area}): {reading.failure_probability:.1f}% "
            f"{reading.health_status}; temperatura {reading.temperature:.1f} °C; vibración "
            f"{reading.vibration:.2f} mm/s; corriente {reading.current:.1f} A; RPM "
            f"{reading.rpm:.0f}; presión {reading.pressure:.2f} bar; {reading.explanation} "
            f"Lectura {reading.recorded_at.isoformat()}."
        )

    for machine in selected:
        reading = latest_by_id[machine.id]
        context.append(
            f"Detalle solicitado {machine.code}: uso {reading.usage_hours:.1f} h; límites: "
            f"vibración {machine.max_vibration:.2f} mm/s, temperatura {machine.max_temperature:.1f} °C, "
            f"corriente {machine.rated_current:.1f} A, RPM nominal {machine.nominal_rpm:.0f}, "
            f"presión {machine.max_pressure:.2f} bar."
        )
        context.append(_trend_context(machine, reading))

    prompt = f"""Responde usando únicamente los datos predictivos proporcionados.
No inventes valores ni afirmes que el índice es una probabilidad estadística validada.
Indica la fecha de la lectura cuando sea relevante. Si preguntan por una máquina no identificada,
solicita su código. Para decisiones de mantenimiento recomienda validación humana.
No interpretes el promedio como aumento o disminución; usa exclusivamente la dirección explícita
indicada entre la primera lectura y la actual.
Responde en español, máximo 180 palabras y termina la última oración.

DATOS:
{chr(10).join(context)}

PREGUNTA: {question}"""
    response = _ollama("/api/chat", {
        "model": current_app.config["OLLAMA_CHAT_MODEL"],
        "messages": [
            {"role": "system", "content": "Eres un copiloto de mantenimiento predictivo farmacéutico. Explicas datos estructurados sin ejecutar SQL ni sustituir decisiones técnicas."},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "keep_alive": "10m",
        "options": {
            "temperature": 0.1,
            "num_ctx": 4096,
            "num_predict": current_app.config["OLLAMA_MAX_TOKENS"],
        },
    })
    latest_timestamp = max(reading.recorded_at for _, reading in rows)
    sources = [f"PostgreSQL · machines + machine_readings · {latest_timestamp.isoformat()}"]
    if selected:
        sources.append("PostgreSQL · tendencias de las últimas 24 horas")
    return response["message"]["content"], sources
