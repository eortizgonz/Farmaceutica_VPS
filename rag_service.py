import hashlib
import json
import urllib.error
import urllib.request
from io import BytesIO

from flask import current_app
from pypdf import PdfReader

from extensions import db
from models import SOPChunk


def _ollama(path, payload, timeout=None):
    timeout = timeout or current_app.config["OLLAMA_TIMEOUT"]
    request = urllib.request.Request(
        f"{current_app.config['OLLAMA_BASE_URL'].rstrip('/')}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError(f"No fue posible conectar con Ollama: {error}") from error


def _embed(texts):
    result = _ollama("/api/embed", {"model": current_app.config["OLLAMA_EMBED_MODEL"], "input": texts})
    return result["embeddings"]


def _chunks(text, size=1200, overlap=200):
    clean = " ".join(text.split())
    return [clean[start:start + size] for start in range(0, len(clean), size - overlap) if clean[start:start + size].strip()]


def ingest_document(file):
    raw = file.read()
    name = file.filename
    pages = ([(i + 1, p.extract_text() or "") for i, p in enumerate(PdfReader(BytesIO(raw)).pages)]
             if name.lower().endswith(".pdf") else [(1, raw.decode("utf-8", errors="replace"))])
    digest = hashlib.sha256(raw).hexdigest()
    records = [(page, index, chunk) for page, text in pages for index, chunk in enumerate(_chunks(text))]
    if not records:
        raise ValueError("El documento no contiene texto extraíble.")
    embeddings = _embed([record[2] for record in records])
    # El nombre identifica la versión lógica del documento. Si el archivo cambia,
    # sustituimos sus vectores anteriores para no mezclar versiones en las respuestas.
    db.session.execute(db.delete(SOPChunk).where(SOPChunk.document_name == name))
    for (page, index, content), embedding in zip(records, embeddings):
        db.session.add(SOPChunk(document_hash=digest, document_name=name, page=page,
                                chunk_index=index, content=content, embedding=embedding))
    db.session.commit()
    return len(records)


def answer_question(question, mode):
    if not db.session.scalar(db.select(db.func.count(SOPChunk.id))):
        raise ValueError("Primero debe cargar al menos un SOP o manual.")
    query_embedding = _embed([question])[0]
    chunks = db.session.scalars(
        db.select(SOPChunk).order_by(SOPChunk.embedding.cosine_distance(query_embedding)).limit(3)
    ).all()
    contexts, sources = [], []
    for chunk in chunks:
        label = f"{chunk.document_name} · página {chunk.page}"
        contexts.append(f"[{label}]\n{chunk.content}")
        if label not in sources:
            sources.append(label)
    instruction = ("Guía paso a paso el diagnóstico. Prioriza seguridad, bloqueo/etiquetado y escalamiento; no indiques reiniciar equipos ni anular protecciones sin respaldo explícito del SOP."
                   if mode == "troubleshooting" else "Responde de forma precisa y concisa usando únicamente la evidencia recuperada.")
    prompt = f"""{instruction}
No inventes. Si la evidencia es insuficiente, dilo y solicita consultar al responsable autorizado.
Cita las fuentes entre corchetes.
Responde en un máximo de 160 palabras y termina siempre la última oración.

EVIDENCIA:
{chr(10).join(contexts)}

PREGUNTA: {question}"""
    response = _ollama("/api/chat", {
        "model": current_app.config["OLLAMA_CHAT_MODEL"],
        "messages": [
            {"role": "system", "content": "Eres un copiloto documental para personal autorizado de una planta farmacéutica. Resume procedimientos aprobados sin sustituir controles de seguridad ni decisiones humanas."},
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
    return response["message"]["content"], sources
