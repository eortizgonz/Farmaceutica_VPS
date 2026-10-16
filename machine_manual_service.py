from io import BytesIO
from pathlib import Path

from werkzeug.datastructures import FileStorage

from extensions import db
from models import Machine, SOPChunk
from predictive_service import _rule_score
from rag_service import ingest_document


MANUAL_PROFILES = {
    "Mezcladora": (["Desalineación o desgaste del impulsor", "Sobrecarga o viscosidad fuera de rango", "Lubricación insuficiente en rodamientos"], "El patrón de vibración, corriente y temperatura puede indicar esfuerzo anormal del tren de mezcla.", ["Verificar carga, viscosidad y velocidad contra la orden", "Inspeccionar impulsor, sello y alineación", "Revisar lubricación y rodamientos"]),
    "Empacadora": (["Desalineación del sistema de arrastre", "Atasco de material o esfuerzo del motor", "Desgaste de rodamientos o transmisión"], "La desviación de velocidad junto con vibración o corriente elevada sugiere resistencia en transporte o sellado.", ["Ejecutar el despeje de producto autorizado", "Inspeccionar guías, rodillos, cadenas y sellado", "Confirmar sincronismo y temperatura de sellado"]),
    "Reactor": (["Carga térmica o presión fuera de régimen", "Incrustación en camisa o agitador", "Deterioro de sello, motor o reductor"], "Temperatura, presión y corriente crecientes pueden reflejar pérdida de transferencia térmica o sobrecarga de agitación.", ["Comparar temperatura y presión con la receta", "Verificar camisa, válvulas y sistema de alivio", "Inspeccionar sello, reductor y agitador aislado"]),
    "Tableteadora": (["Sobrecarga en compresión o alimentación irregular", "Desgaste de punzones, torreta o rodamientos", "Lubricación deficiente o desalineación"], "Vibración y corriente elevadas con variación de RPM son compatibles con esfuerzo anormal del conjunto de compresión.", ["Verificar fuerza de compresión y alimentación", "Inspeccionar punzones, matrices, torreta y lubricación", "Confirmar alineación y ausencia de producto compactado"]),
    "Recubridora": (["Carga desequilibrada del bombo", "Restricción del sistema de aire", "Desgaste del accionamiento o rodamientos"], "La combinación de vibración, temperatura y RPM puede corresponder a desequilibrio o restricción de proceso.", ["Confirmar carga y parámetros de receta", "Revisar filtros, ductos y extracción", "Inspeccionar accionamiento, rodillos y rodamientos"]),
    "Secador": (["Filtros saturados o flujo de aire restringido", "Sobretemperatura del sistema", "Desbalance del ventilador"], "Presión, temperatura y corriente fuera de tendencia pueden indicar restricción de aire o deterioro del ventilador.", ["Verificar diferencial de presión y filtros", "Comprobar compuertas, calentamiento y sensores", "Inspeccionar ventilador y rodamientos"]),
    "default": (["Desgaste mecánico progresivo", "Carga operativa fuera del rango normal", "Sensor descalibrado o condición eléctrica anormal"], "Las variables con mayor aporte deben verificarse contra el estado real y el historial de mantenimiento.", ["Confirmar la lectura con un instrumento verificado", "Revisar carga, conexiones, lubricación y elementos móviles", "Comparar con mantenimiento preventivo y eventos recientes"]),
}

MANUALS_FOLDER = Path(__file__).resolve().parent / "datos_simulados" / "manuales_maquinas"


def _profile(machine):
    searchable = f"{machine.machine_type} {machine.name}".casefold()
    for key, profile in MANUAL_PROFILES.items():
        if key != "default" and key.casefold() in searchable:
            return profile
    return MANUAL_PROFILES["default"]


def manual_filename(machine):
    return f"MAN-EQP-{machine.code}_mantenimiento_predictivo.md"


def manual_text(machine):
    path = MANUALS_FOLDER / manual_filename(machine)
    if not path.is_file():
        raise ValueError(f"No existe el archivo físico del manual: {path.name}")
    return path.read_text(encoding="utf-8")


def ingest_machine_manuals():
    machines = db.session.scalars(db.select(Machine).order_by(Machine.code)).all()
    if not machines:
        raise ValueError("Primero debe ejecutar seed-predictive-data.")
    chunks = 0
    for machine in machines:
        raw = manual_text(machine).encode("utf-8")
        chunks += ingest_document(FileStorage(stream=BytesIO(raw), filename=manual_filename(machine)))
    return len(machines), chunks


def machine_diagnosis(machine, reading):
    filename = manual_filename(machine)
    if not db.session.scalar(db.select(SOPChunk.id).where(SOPChunk.document_name == filename).limit(1)):
        raise ValueError("El manual de esta máquina aún no está indexado en pgvector.")

    ratios = [
        ("Horas de uso", reading.usage_hours / machine.max_usage_hours, 0.12),
        ("Vibración", reading.vibration / machine.max_vibration, 0.25),
        ("Temperatura", reading.temperature / machine.max_temperature, 0.20),
        ("Corriente", reading.current / machine.rated_current, 0.17),
        ("Desviación de RPM", abs(reading.rpm - machine.nominal_rpm) / max(machine.nominal_rpm, 1) / 0.20, 0.14),
        ("Presión", reading.pressure / machine.max_pressure, 0.12),
    ]
    factors = []
    for label, ratio, weight in ratios:
        contribution = _rule_score(ratio) * weight
        factors.append({"name": label, "contribution": round(contribution, 1), "ratio": round(ratio * 100, 1)})
    factors.sort(key=lambda item: item["contribution"], reverse=True)

    causes, diagnosis, actions = _profile(machine)
    if reading.health_status == "Healthy":
        diagnosis = "Condición estable dentro de las reglas configuradas. Mantener observación de tendencias."
        causes = ["No se identifica una condición dominante de falla", "Variación operacional dentro de límites configurados"]
        actions = ["Continuar el monitoreo periódico", "Cumplir el mantenimiento preventivo", "Verificar cualquier cambio sostenido de tendencia"]
    else:
        actions = list(actions) + ["Programar inspección prioritaria y documentar hallazgos" if reading.health_status == "Warning" else "Escalar de inmediato y aplicar parada segura/LOTO si el procedimiento lo exige"]
    return {"diagnosis": diagnosis, "causes": causes, "actions": actions, "factors": factors, "source": f"{filename} · pgvector"}
