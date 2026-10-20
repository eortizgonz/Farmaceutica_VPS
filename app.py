import os
import time

import click
import psycopg
from psycopg import sql
from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from sqlalchemy.engine import URL, make_url

from extensions import csrf, db, login_manager, migrate
from forms import (
    EmptyForm,
    LoginForm,
    PasswordResetForm,
    PasswordResetRequestForm,
    RegistrationForm,
    SOPQuestionForm,
    SOPUploadForm,
)
from mail_service import send_password_reset_email
from models import Machine, MachineReading, User
from rag_service import answer_question, ingest_document
from machine_manual_service import ingest_machine_manuals, machine_diagnosis
from predictive_service import (
    append_simulated_snapshot,
    backfill_simulated_history,
    latest_machine_snapshot,
    recalculate_historical_risks,
    seed_demo_machines,
)
from predictive_chat import answer_predictive_question
from oee_service import append_oee_snapshot, oee_dashboard_data, seed_oee_demo
from oee_chat import answer_oee_question


load_dotenv()


def resolve_chat_mode(question, requested_mode):
    if requested_mode != "auto":
        return requested_mode
    normalized = question.casefold()
    oee_terms = ("oee", "eficiencia global", "disponibilidad", "rendimiento", "turno actual", "orden de producción", "orden de produccion", "lote activo", "microparada")
    if any(term in normalized for term in oee_terms):
        return "oee"
    predictive_terms = (
        "riesgo", "predictiv", "healthy", "warning", "critical", "crítica",
        "critica", "máquina debo revisar", "maquina debo revisar", "mayor riesgo",
        "estado de la máquina", "estado de la maquina", "vibración", "vibracion",
        "temperatura", "corriente", "rpm", "presión", "presion",
    )
    if any(term in normalized for term in predictive_terms):
        return "predictive"
    troubleshooting_terms = ("alarma", "error", "falla", "detenida", "se detuvo", "no arranca")
    if any(term in normalized for term in troubleshooting_terms):
        return "troubleshooting"
    return "sop"


def get_database_url():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        if database_url.startswith("postgres://"):
            return database_url.replace("postgres://", "postgresql+psycopg://", 1)
        return database_url

    return URL.create(
        "postgresql+psycopg",
        username=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "pharma_copilot"),
    )


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev-only-change-me"),
        SQLALCHEMY_DATABASE_URI=get_database_url(),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAIL_SERVER=os.getenv("MAIL_SERVER", "smtp.gmail.com"),
        MAIL_PORT=int(os.getenv("MAIL_PORT", "587")),
        MAIL_USERNAME=os.getenv("MAIL_USERNAME", ""),
        MAIL_PASSWORD=os.getenv("MAIL_PASSWORD", ""),
        MAIL_DEFAULT_SENDER=os.getenv("MAIL_DEFAULT_SENDER", ""),
        APP_BASE_URL=os.getenv("APP_BASE_URL", ""),
        OLLAMA_BASE_URL=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        OLLAMA_CHAT_MODEL=os.getenv("OLLAMA_CHAT_MODEL", "llama3.1:8b"),
        OLLAMA_EMBED_MODEL=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
        OLLAMA_TIMEOUT=int(os.getenv("OLLAMA_TIMEOUT", "300")),
        OLLAMA_MAX_TOKENS=int(os.getenv("OLLAMA_MAX_TOKENS", "220")),
        SESSION_IDLE_TIMEOUT_SECONDS=int(os.getenv("SESSION_IDLE_TIMEOUT_SECONDS", "1800")),
        MAX_CONTENT_LENGTH=25 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)
    login_manager.login_view = "login"
    login_manager.login_message = "Inicia sesión para acceder al dashboard."
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.before_request
    def enforce_idle_session_timeout():
        if not current_user.is_authenticated:
            return None
        now = int(time.time())
        last_activity = session.get("last_user_activity")
        timeout = app.config["SESSION_IDLE_TIMEOUT_SECONDS"]
        if last_activity is not None and now - int(last_activity) >= timeout:
            logout_user()
            session.clear()
            if request.path.startswith("/api/"):
                return jsonify(error="La sesión terminó por inactividad."), 401
            flash("La sesión terminó por inactividad.", "info")
            return redirect(url_for("login"))
        if last_activity is None or request.endpoint == "session_activity":
            session["last_user_activity"] = now
        return None

    @app.post("/api/session/activity")
    @login_required
    @csrf.exempt
    def session_activity():
        session["last_user_activity"] = int(time.time())
        return jsonify(status="active")

    @app.route("/")
    @login_required
    def index():
        return render_template("index.html", logout_form=EmptyForm(), chat_form=EmptyForm())

    @app.get("/predictive")
    @login_required
    def predictive_dashboard():
        rows = latest_machine_snapshot()
        counts = {"Healthy": 0, "Warning": 0, "Critical": 0}
        for _, reading in rows:
            counts[reading.health_status] += 1
        average_risk = round(sum(reading.failure_probability for _, reading in rows) / len(rows), 1) if rows else 0
        return render_template(
            "predictive.html", rows=rows, counts=counts, average_risk=average_risk,
            highest=rows[0] if rows else None, logout_form=EmptyForm(),
            embedded=request.args.get("embedded") == "1",
        )

    @app.get("/api/predictive/snapshot")
    @login_required
    def predictive_snapshot_api():
        rows = latest_machine_snapshot()
        counts = {"Healthy": 0, "Warning": 0, "Critical": 0}
        machines = []
        for machine, reading in rows:
            counts[reading.health_status] += 1
            machines.append({
                "code": machine.code,
                "name": machine.name,
                "area": machine.area,
                "usage_hours": reading.usage_hours,
                "vibration": reading.vibration,
                "temperature": reading.temperature,
                "current": reading.current,
                "rpm": reading.rpm,
                "pressure": reading.pressure,
                "failure_probability": reading.failure_probability,
                "health_status": reading.health_status,
                "explanation": reading.explanation,
                "recorded_at": reading.recorded_at.isoformat(),
                "limits": {
                    "vibration": machine.max_vibration,
                    "temperature": machine.max_temperature,
                    "current": machine.rated_current,
                    "pressure": machine.max_pressure,
                },
            })
        average = round(sum(item["failure_probability"] for item in machines) / len(machines), 1) if machines else 0
        return jsonify(
            machines=machines,
            summary={**counts, "average_risk": average, "total": len(machines)},
            updated_at=max((item["recorded_at"] for item in machines), default=None),
        )

    @app.get("/api/predictive/machines/<string:code>/diagnosis")
    @login_required
    def predictive_machine_diagnosis_api(code):
        machine = db.session.scalar(db.select(Machine).where(Machine.code == code))
        if not machine:
            return jsonify(error="Máquina no encontrada."), 404
        reading = db.session.scalar(
            db.select(MachineReading)
            .where(MachineReading.machine_id == machine.id)
            .order_by(MachineReading.recorded_at.desc()).limit(1)
        )
        if not reading:
            return jsonify(error="La máquina no tiene lecturas disponibles."), 404
        try:
            manual = machine_diagnosis(machine, reading)
        except ValueError as error:
            return jsonify(error=str(error)), 404
        return jsonify(
            machine={"code": machine.code, "name": machine.name, "area": machine.area},
            reading={
                "failure_probability": reading.failure_probability,
                "health_status": reading.health_status,
                "explanation": reading.explanation,
                "usage_hours": reading.usage_hours,
                "vibration": reading.vibration,
                "temperature": reading.temperature,
                "current": reading.current,
                "rpm": reading.rpm,
                "pressure": reading.pressure,
                "recorded_at": reading.recorded_at.isoformat(),
            },
            manual=manual,
        )

    @app.get("/oee")
    @login_required
    def oee_dashboard():
        data = oee_dashboard_data(days=request.args.get("days", 7, type=int))
        return render_template("oee.html", data=data, embedded=request.args.get("embedded") == "1")

    @app.get("/api/oee/summary")
    @login_required
    def oee_summary_api():
        days = max(1, min(request.args.get("days", 7, type=int), 90))
        return jsonify(oee_dashboard_data(days=days))

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.route("/sop", methods=["GET", "POST"])
    @login_required
    def sop_assistant():
        upload_form = SOPUploadForm(prefix="upload")
        question_form = SOPQuestionForm(prefix="question")
        answer = None
        sources = []
        if upload_form.submit.data and upload_form.validate_on_submit():
            try:
                count = ingest_document(upload_form.document.data)
                flash(f"Documento indexado en {count} fragmentos.", "success")
                return redirect(url_for("sop_assistant"))
            except Exception as error:
                app.logger.exception("Error indexando documento")
                flash(str(error), "error")
        elif question_form.submit.data and question_form.validate_on_submit():
            try:
                mode = resolve_chat_mode(question_form.question.data, question_form.mode.data)
                if mode == "predictive":
                    answer, sources = answer_predictive_question(question_form.question.data)
                elif mode == "oee":
                    answer, sources = answer_oee_question(question_form.question.data)
                else:
                    answer, sources = answer_question(question_form.question.data, mode)
            except Exception as error:
                app.logger.exception("Error consultando SOP")
                flash(str(error), "error")
        return render_template("sop.html", upload_form=upload_form, question_form=question_form, answer=answer, sources=sources)

    @app.post("/api/sop/chat")
    @login_required
    def sop_chat_api():
        payload = request.get_json(silent=True) or {}
        question = str(payload.get("question", "")).strip()
        mode = payload.get("mode", "auto")
        if len(question) < 5 or len(question) > 2000:
            return jsonify(error="La pregunta debe tener entre 5 y 2000 caracteres."), 400
        if mode not in {"auto", "sop", "troubleshooting", "predictive", "oee"}:
            return jsonify(error="Modo de consulta inválido."), 400
        try:
            mode = resolve_chat_mode(question, mode)
            if mode == "predictive":
                answer, sources = answer_predictive_question(question)
            elif mode == "oee":
                answer, sources = answer_oee_question(question)
            else:
                answer, sources = answer_question(question, mode)
            return jsonify(answer=answer, sources=sources)
        except ValueError as error:
            return jsonify(error=str(error)), 400
        except RuntimeError as error:
            app.logger.exception("Ollama no disponible")
            return jsonify(error=str(error)), 503
        except Exception:
            app.logger.exception("Error en el chat SOP")
            return jsonify(error="No fue posible procesar la consulta."), 500

    @app.route("/registro", methods=["GET", "POST"])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for("index"))

        form = RegistrationForm()
        if form.validate_on_submit():
            user = User(
                name=form.name.data.strip(),
                email=form.email.data.strip().lower(),
                username=form.username.data.strip().lower(),
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash("Usuario creado. Ya puedes iniciar sesión.", "success")
            return redirect(url_for("login"))
        return render_template("auth/register.html", form=form)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("index"))

        form = LoginForm()
        if form.validate_on_submit():
            identity = form.identity.data.strip().lower()
            user = db.session.scalar(
                db.select(User).where(
                    (User.username == identity) | (User.email == identity)
                )
            )
            if user and user.check_password(form.password.data):
                login_user(user, remember=form.remember.data)
                session["last_user_activity"] = int(time.time())
                return redirect(url_for("index"))
            flash("Usuario/correo o contraseña incorrectos.", "error")
        return render_template("auth/login.html", form=form)

    @app.route("/recuperar-password", methods=["GET", "POST"])
    def request_password_reset():
        if current_user.is_authenticated:
            return redirect(url_for("index"))
        form = PasswordResetRequestForm()
        if form.validate_on_submit():
            email = form.email.data.strip().lower()
            user = db.session.scalar(db.select(User).where(User.email == email))
            if user:
                try:
                    send_password_reset_email(user)
                except Exception:
                    app.logger.exception("No se pudo enviar el correo de recuperación")
            flash(
                "Si el correo está registrado, recibirás un enlace de recuperación.",
                "success",
            )
            return redirect(url_for("login"))
        return render_template("auth/request_reset.html", form=form)

    @app.route("/restablecer-password/<token>", methods=["GET", "POST"])
    def reset_password(token):
        if current_user.is_authenticated:
            return redirect(url_for("index"))
        user = User.verify_reset_token(token)
        if not user:
            flash("El enlace es inválido o ya venció.", "error")
            return redirect(url_for("request_password_reset"))
        form = PasswordResetForm()
        if form.validate_on_submit():
            user.set_password(form.password.data)
            db.session.commit()
            flash("Contraseña actualizada. Ya puedes iniciar sesión.", "success")
            return redirect(url_for("login"))
        return render_template("auth/reset_password.html", form=form)

    @app.post("/logout")
    @login_required
    def logout():
        form = EmptyForm()
        if form.validate_on_submit():
            logout_user()
            flash("Sesión cerrada correctamente.", "success")
        return redirect(url_for("login"))

    @app.cli.command("create-db")
    def create_database_command():
        """Crea la base PostgreSQL configurada si todavía no existe."""
        url = make_url(app.config["SQLALCHEMY_DATABASE_URI"])
        if not url.drivername.startswith("postgresql"):
            raise click.ClickException("create-db solo está disponible para PostgreSQL.")

        database_name = url.database
        if not database_name:
            raise click.ClickException("POSTGRES_DB no puede estar vacío.")

        try:
            with psycopg.connect(
                host=url.host,
                port=url.port or 5432,
                user=url.username,
                password=url.password,
                dbname="postgres",
                autocommit=True,
            ) as connection:
                exists = connection.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s", (database_name,)
                ).fetchone()
                if exists:
                    click.echo(f"La base '{database_name}' ya existe.")
                    return
                connection.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name))
                )
                click.echo(f"Base '{database_name}' creada correctamente.")
        except psycopg.Error as error:
            raise click.ClickException(f"No fue posible crear la base: {error}") from error

    @app.cli.command("ingest-documents")
    @click.argument("folder", type=click.Path(exists=True, file_okay=False, path_type=str))
    def ingest_documents_command(folder):
        """Indexa en pgvector todos los PDF, TXT y MD de una carpeta."""
        from pathlib import Path
        from werkzeug.datastructures import FileStorage

        paths = sorted(path for path in Path(folder).iterdir() if path.suffix.lower() in {".pdf", ".txt", ".md"} and path.name.lower() != "readme.md")
        if not paths:
            raise click.ClickException("No se encontraron documentos compatibles.")
        for path in paths:
            with path.open("rb") as stream:
                count = ingest_document(FileStorage(stream=stream, filename=path.name))
            click.echo(f"{path.name}: {count} fragmentos indexados")
        click.echo(f"Carga completada: {len(paths)} documentos.")

    @app.cli.command("seed-predictive-data")
    def seed_predictive_data_command():
        """Crea o actualiza las 20 máquinas sin borrar su historial."""
        count = seed_demo_machines()
        click.echo(f"Datos predictivos cargados: {count} máquinas.")

    @app.cli.command("ingest-machine-manuals")
    def ingest_machine_manuals_command():
        """Genera e indexa en pgvector un manual predictivo por máquina."""
        try:
            machines, chunks = ingest_machine_manuals()
        except ValueError as error:
            raise click.ClickException(str(error)) from error
        click.echo(f"Manuales indexados: {machines} máquinas, {chunks} fragmentos.")

    @app.cli.command("capture-machine-readings")
    @click.option("--seed", type=int, default=None, help="Semilla opcional para reproducibilidad.")
    def capture_machine_readings_command(seed):
        """Inserta una nueva lectura simulada para cada máquina."""
        try:
            count = append_simulated_snapshot(seed=seed)
        except ValueError as error:
            raise click.ClickException(str(error)) from error
        click.echo(f"Nueva captura completada: {count} lecturas.")

    @app.cli.command("seed-oee-data")
    @click.option("--days", type=click.IntRange(min=1, max=365), default=30, show_default=True)
    @click.option("--seed", type=int, default=2026, show_default=True)
    def seed_oee_data_command(days, seed):
        """Crea productos, turnos, órdenes, lotes y resultados OEE simulados."""
        result = seed_oee_demo(days=days, seed=seed)
        click.echo(f"OEE cargado: {result['products']} productos, {result['shifts']} turnos, {result['orders']} órdenes y {result['runs']} ejecuciones nuevas.")

    @app.cli.command("run-oee-collector")
    @click.option("--interval-seconds", type=click.IntRange(min=60, max=86400), default=900, show_default=True)
    @click.option("--iterations", type=click.IntRange(min=0), default=0, hidden=True)
    def run_oee_collector_command(interval_seconds, iterations):
        """Simula continuamente producción, pérdidas y resultados OEE."""
        seed_oee_demo(days=30)
        interval_minutes = max(1, round(interval_seconds / 60))
        click.echo(f"Recolector OEE activo: una ventana cada {interval_seconds} segundos.")
        completed = 0
        try:
            while not iterations or completed < iterations:
                count = append_oee_snapshot(interval_minutes=interval_minutes)
                completed += 1
                click.echo(f"Ventana OEE {completed}: {count} ejecuciones insertadas.")
                if not iterations or completed < iterations:
                    time.sleep(interval_seconds)
        except KeyboardInterrupt:
            click.echo("Recolector OEE detenido.")

    @app.cli.command("run-reading-collector")
    @click.option("--interval-seconds", type=click.IntRange(min=5, max=86400), default=15, show_default=True)
    @click.option("--iterations", type=click.IntRange(min=0), default=0, hidden=True)
    def run_reading_collector_command(interval_seconds, iterations):
        """Captura lecturas continuamente; cero iteraciones significa ejecución indefinida."""
        seed_demo_machines()
        click.echo(f"Recolector activo: una captura cada {interval_seconds} segundos. Ctrl+C para detener.")
        completed = 0
        try:
            while not iterations or completed < iterations:
                count = append_simulated_snapshot()
                completed += 1
                click.echo(f"Captura {completed}: {count} lecturas insertadas.")
                if not iterations or completed < iterations:
                    time.sleep(interval_seconds)
        except KeyboardInterrupt:
            click.echo("Recolector detenido.")

    @app.cli.command("backfill-predictive-history")
    @click.option("--days", type=click.IntRange(min=1, max=730), default=90, show_default=True)
    @click.option("--interval-minutes", type=click.IntRange(min=5, max=1440), default=60, show_default=True)
    @click.option("--seed", type=int, default=2026, show_default=True)
    def backfill_predictive_history_command(days, interval_minutes, seed):
        """Genera lecturas históricas anteriores sin duplicar el periodo existente."""
        try:
            count = backfill_simulated_history(days, interval_minutes, seed)
        except ValueError as error:
            raise click.ClickException(str(error)) from error
        click.echo(f"Historial completado: {count} lecturas nuevas.")

    @app.cli.command("recalculate-machine-risks")
    @click.option("--batch-size", type=click.IntRange(min=100, max=10000), default=1000, show_default=True)
    def recalculate_machine_risks_command(batch_size):
        """Recalcula riesgo y estado de todo el historial con las reglas vigentes."""
        count = recalculate_historical_risks(batch_size)
        click.echo(f"Riesgos recalculados: {count} lecturas.")

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=os.getenv("FLASK_DEBUG") == "1")
