from datetime import datetime
from zoneinfo import ZoneInfo

from flask import current_app

from extensions import db
from models import ProductionBatch, ProductionOrder, WorkShift
from oee_service import oee_dashboard_data
from rag_service import _ollama


def _current_shift():
    now = datetime.now(ZoneInfo("America/Bogota"))
    shifts = db.session.scalars(db.select(WorkShift).where(WorkShift.active.is_(True))).all()
    current = now.time().replace(tzinfo=None)
    for shift in shifts:
        matches = (shift.start_time <= current < shift.end_time if shift.start_time < shift.end_time else current >= shift.start_time or current < shift.end_time)
        if matches:
            return shift, now
    return None, now


def answer_oee_question(question):
    data = oee_dashboard_data(days=7)
    if not data["summary"]["runs"]:
        raise ValueError("No existen ejecuciones OEE para consultar.")
    shift, now = _current_shift()
    orders = db.session.scalars(db.select(ProductionOrder).where(ProductionOrder.status == "In Progress").order_by(ProductionOrder.order_number).limit(8)).all()
    batches = db.session.scalars(db.select(ProductionBatch).where(ProductionBatch.status == "In Progress").order_by(ProductionBatch.batch_number).limit(8)).all()
    summary = data["summary"]
    context = [
        f"Fecha y hora: {now.isoformat()}.",
        f"Turno horario actual: {shift.code} - {shift.name}, {shift.start_time} a {shift.end_time}." if shift else "No existe un turno configurado para la hora actual.",
        f"Últimos 7 días ({summary['runs']} ejecuciones): OEE {summary['oee']}%, disponibilidad {summary['availability']}%, rendimiento {summary['performance']}%, calidad {summary['quality']}%.",
        "Menor OEE: " + "; ".join(f"{m['code']} {m['oee']}% ({m['status']})" for m in data["machines"][:8]),
        "Pérdidas: " + "; ".join(f"{x['category']} {x['minutes']} min" for x in data["losses"]),
        "Órdenes activas: " + ", ".join(x.order_number for x in orders),
        "Lotes activos: " + ", ".join(x.batch_number for x in batches),
    ]
    prompt = f"""Responde únicamente con los datos suministrados. No inventes producción en tiempo real: el turno actual proviene del horario configurado y los indicadores corresponden al historial simulado disponible. OEE = disponibilidad × rendimiento × calidad. Responde en español, máximo 180 palabras.

DATOS:
{chr(10).join(context)}

PREGUNTA: {question}"""
    response = _ollama("/api/chat", {"model": current_app.config["OLLAMA_CHAT_MODEL"], "messages": [{"role": "system", "content": "Eres un copiloto OEE farmacéutico. Explicas datos estructurados de PostgreSQL sin generar SQL."}, {"role": "user", "content": prompt}], "stream": False, "keep_alive": "10m", "options": {"temperature": 0.1, "num_ctx": 4096, "num_predict": current_app.config["OLLAMA_MAX_TOKENS"]}})
    return response["message"]["content"], ["PostgreSQL · OEE últimos 7 días", "PostgreSQL · turnos, órdenes y lotes"]
