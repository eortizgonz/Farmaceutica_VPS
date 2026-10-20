import unittest
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app import create_app, resolve_chat_mode
from extensions import db
from models import Machine, MachineReading, OEEResult, Product, ProductionRun, User, WorkShift
from oee_service import append_oee_snapshot, seed_oee_demo
from predictive_service import append_simulated_snapshot, seed_demo_machines


class AuthFlowTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(
            {
                "TESTING": True,
                "WTF_CSRF_ENABLED": False,
                "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                "SECRET_KEY": "test-secret",
            }
        )
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_dashboard_requires_login(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_session_expires_after_idle_timeout(self):
        self.app.config["SESSION_IDLE_TIMEOUT_SECONDS"] = 1
        user = User(name="Inactivo", email="idle@example.com", username="idle")
        user.set_password("ClaveSegura123")
        db.session.add(user)
        db.session.commit()
        self.client.post("/login", data={"identity": "idle", "password": "ClaveSegura123"})
        with self.client.session_transaction() as browser_session:
            browser_session["last_user_activity"] = int(time.time()) - 2

        response = self.client.get("/api/predictive/snapshot")

        self.assertEqual(response.status_code, 401)
        self.assertIn("inactividad", response.json["error"])

    def test_register_login_and_logout(self):
        response = self.client.post(
            "/registro",
            data={
                "name": "Ana Gómez",
                "email": "ANA@EXAMPLE.COM",
                "username": "Ana.G",
                "password": "ClaveSegura123",
                "confirm_password": "ClaveSegura123",
            },
            follow_redirects=True,
        )
        self.assertIn("Usuario creado", response.get_data(as_text=True))

        user = db.session.scalar(db.select(User).where(User.username == "ana.g"))
        self.assertIsNotNone(user)
        self.assertEqual(user.email, "ana@example.com")
        self.assertNotEqual(user.password_hash, "ClaveSegura123")

        response = self.client.post(
            "/login",
            data={"identity": "ANA@EXAMPLE.COM", "password": "ClaveSegura123"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Ana Gómez", response.get_data(as_text=True))
        self.assertIn("Analítica predictiva", response.get_data(as_text=True))
        self.assertIn('id="predictiveEmbedded"', response.get_data(as_text=True))

        response = self.client.post("/logout", follow_redirects=True)
        self.assertIn("Sesión cerrada", response.get_data(as_text=True))

    def test_rejects_duplicate_email_and_username(self):
        user = User(name="Primera", email="user@example.com", username="usuario")
        user.set_password("ClaveSegura123")
        db.session.add(user)
        db.session.commit()

        response = self.client.post(
            "/registro",
            data={
                "name": "Segunda",
                "email": "USER@example.com",
                "username": "Usuario",
                "password": "OtraClave123",
                "confirm_password": "OtraClave123",
            },
        )
        body = response.get_data(as_text=True)
        self.assertIn("Ya existe una cuenta con este correo", body)
        self.assertIn("Este username ya está en uso", body)

    @patch("app.send_password_reset_email")
    def test_password_reset_flow(self, send_email):
        user = User(name="Ana", email="ana@example.com", username="ana")
        user.set_password("ClaveAnterior123")
        db.session.add(user)
        db.session.commit()

        response = self.client.post(
            "/recuperar-password",
            data={"email": "ANA@example.com"},
            follow_redirects=True,
        )
        self.assertIn("Si el correo está registrado", response.get_data(as_text=True))
        send_email.assert_called_once_with(user)

        token = user.get_reset_token()
        response = self.client.post(
            f"/restablecer-password/{token}",
            data={
                "password": "ClaveNueva456",
                "confirm_password": "ClaveNueva456",
            },
            follow_redirects=True,
        )
        self.assertIn("Contraseña actualizada", response.get_data(as_text=True))
        self.assertTrue(user.check_password("ClaveNueva456"))
        self.assertIsNone(User.verify_reset_token(token))

    @patch("app.send_password_reset_email")
    def test_password_reset_does_not_reveal_unknown_email(self, send_email):
        response = self.client.post(
            "/recuperar-password",
            data={"email": "missing@example.com"},
            follow_redirects=True,
        )
        self.assertIn("Si el correo está registrado", response.get_data(as_text=True))
        send_email.assert_not_called()

    @patch("app.answer_question", return_value=("Detenga el equipo según el SOP.", ["manual.pdf · página 4"]))
    def test_authenticated_sop_chat(self, answer_question):
        user = User(name="Operador", email="op@example.com", username="operador")
        user.set_password("ClaveSegura123")
        db.session.add(user)
        db.session.commit()
        self.client.post("/login", data={"identity": "operador", "password": "ClaveSegura123"})

        response = self.client.post(
            "/api/sop/chat",
            json={"question": "¿Qué indica el procedimiento?", "mode": "sop"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["sources"], ["manual.pdf · página 4"])
        answer_question.assert_called_once()

    @patch(
        "app.answer_predictive_question",
        return_value=("La CT-900 está en Warning con 43.3%.", ["PostgreSQL · machine_readings"]),
    )
    def test_authenticated_predictive_chat(self, predictive_answer):
        user = User(name="Operador", email="predict@example.com", username="predictivo")
        user.set_password("ClaveSegura123")
        db.session.add(user)
        db.session.commit()
        self.client.post("/login", data={"identity": "predictivo", "password": "ClaveSegura123"})

        response = self.client.post(
            "/api/sop/chat",
            json={"question": "¿Cuál es el riesgo actual de la CT-900?", "mode": "predictive"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("43.3%", response.json["answer"])
        predictive_answer.assert_called_once_with("¿Cuál es el riesgo actual de la CT-900?")

    def test_sop_chat_requires_login(self):
        response = self.client.post("/api/sop/chat", json={"question": "Pregunta válida", "mode": "sop"})
        self.assertEqual(response.status_code, 302)

    def test_automatic_chat_mode_routing(self):
        self.assertEqual(resolve_chat_mode("¿Qué máquina debo revisar primero?", "auto"), "predictive")
        self.assertEqual(resolve_chat_mode("¿Qué hago ante la alarma E-104?", "auto"), "troubleshooting")
        self.assertEqual(resolve_chat_mode("¿Cómo se libera un lote?", "auto"), "sop")
        self.assertEqual(resolve_chat_mode("¿Cuál es el OEE del turno actual?", "auto"), "oee")

    @patch("app.answer_oee_question", return_value=("El turno actual es T1.", ["PostgreSQL · turnos"]))
    def test_authenticated_oee_chat(self, answer_oee):
        user = User(name="Operador", email="oeechat@example.com", username="oeechat")
        user.set_password("ClaveSegura123")
        db.session.add(user)
        db.session.commit()
        self.client.post("/login", data={"identity": "oeechat", "password": "ClaveSegura123"})
        response = self.client.post("/api/sop/chat", json={"question": "¿Cuál es el OEE del turno actual?", "mode": "auto"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("T1", response.json["answer"])
        answer_oee.assert_called_once()

    def test_predictive_dashboard_requires_login(self):
        response = self.client.get("/predictive")
        self.assertEqual(response.status_code, 302)

    def test_predictive_dashboard_with_seed_data(self):
        user = User(name="Técnico", email="tech@example.com", username="tecnico")
        user.set_password("ClaveSegura123")
        db.session.add(user)
        db.session.commit()
        seed_demo_machines()
        self.client.post("/login", data={"identity": "tecnico", "password": "ClaveSegura123"})

        response = self.client.get("/predictive")
        body = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Salud de equipos de producción", body)
        self.assertEqual(db.session.scalar(db.select(db.func.count(Machine.id))), 20)
        self.assertEqual(db.session.scalar(db.select(db.func.count(MachineReading.id))), 20)

        embedded = self.client.get("/predictive?embedded=1")
        self.assertEqual(embedded.status_code, 200)
        self.assertIn('<body class="embedded">', embedded.get_data(as_text=True))

        snapshot = self.client.get("/api/predictive/snapshot")
        self.assertEqual(snapshot.status_code, 200)
        self.assertEqual(snapshot.json["summary"]["total"], 20)
        self.assertEqual(len(snapshot.json["machines"]), 20)
        self.assertIn("failure_probability", snapshot.json["machines"][0])
        self.assertIn('id="diagnosisModal"', body)

        append_simulated_snapshot(
            recorded_at=datetime.now(timezone.utc) + timedelta(minutes=15), seed=99
        )
        self.assertEqual(db.session.scalar(db.select(db.func.count(MachineReading.id))), 40)

    @patch("app.machine_diagnosis")
    def test_machine_diagnosis_endpoint(self, diagnosis):
        user = User(name="Técnico", email="manual@example.com", username="manual")
        user.set_password("ClaveSegura123")
        db.session.add(user)
        db.session.commit()
        seed_demo_machines()
        diagnosis.return_value = {
            "diagnosis": "Revisar tren mecánico.",
            "causes": ["Desalineación"],
            "actions": ["Inspeccionar rodamientos"],
            "factors": [{"name": "Vibración", "contribution": 12.5, "ratio": 95.0}],
            "source": "MAN-EQP-MX-750_mantenimiento_predictivo.md · pgvector",
        }
        self.client.post("/login", data={"identity": "manual", "password": "ClaveSegura123"})

        response = self.client.get("/api/predictive/machines/MX-750/diagnosis")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["machine"]["code"], "MX-750")
        self.assertIn("pgvector", response.json["manual"]["source"])

    def test_oee_dashboard_and_relational_seed(self):
        user = User(name="OEE", email="oee@example.com", username="oee")
        user.set_password("ClaveSegura123")
        db.session.add(user)
        db.session.commit()
        result = seed_oee_demo(days=1, seed=99)
        self.client.post("/login", data={"identity": "oee", "password": "ClaveSegura123"})

        page = self.client.get("/oee?embedded=1")
        api = self.client.get("/api/oee/summary?days=7")

        self.assertEqual(page.status_code, 200)
        self.assertIn("Eficiencia Global de Equipos", page.get_data(as_text=True))
        self.assertEqual(api.status_code, 200)
        self.assertEqual(result["runs"], 20)
        self.assertEqual(db.session.scalar(db.select(db.func.count(Product.id))), 8)
        self.assertEqual(db.session.scalar(db.select(db.func.count(WorkShift.id))), 3)
        self.assertEqual(db.session.scalar(db.select(db.func.count(ProductionRun.id))), 20)
        self.assertEqual(db.session.scalar(db.select(db.func.count(OEEResult.id))), 20)
        self.assertGreater(api.json["summary"]["oee"], 0)

        captured_at = datetime.now(timezone.utc).replace(second=0, microsecond=0) + timedelta(minutes=15)
        self.assertEqual(append_oee_snapshot(recorded_at=captured_at, interval_minutes=15, seed=7), 20)
        self.assertEqual(append_oee_snapshot(recorded_at=captured_at, interval_minutes=15, seed=7), 0)
        self.assertEqual(db.session.scalar(db.select(db.func.count(OEEResult.id))), 40)


if __name__ == "__main__":
    unittest.main()
