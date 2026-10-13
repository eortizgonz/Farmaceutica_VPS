import os

import click
import psycopg
from psycopg import sql
from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, url_for
from flask_login import current_user, login_required, login_user, logout_user

from sqlalchemy.engine import URL, make_url

from extensions import csrf, db, login_manager, migrate
from forms import EmptyForm, LoginForm, RegistrationForm
from models import User


load_dotenv()


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

    @app.route("/")
    @login_required
    def index():
        return render_template("index.html", logout_form=EmptyForm())

    @app.get("/health")
    def health():
        return jsonify(status="ok")

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
                return redirect(url_for("index"))
            flash("Usuario/correo o contraseña incorrectos.", "error")
        return render_template("auth/login.html", form=form)

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

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=os.getenv("FLASK_DEBUG") == "1")
