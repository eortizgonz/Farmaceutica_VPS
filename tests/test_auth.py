import unittest

from app import create_app
from extensions import db
from models import User


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


if __name__ == "__main__":
    unittest.main()
