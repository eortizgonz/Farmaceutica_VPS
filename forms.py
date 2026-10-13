from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Regexp, ValidationError

from extensions import db
from models import User


class RegistrationForm(FlaskForm):
    name = StringField("Nombre completo", validators=[DataRequired(), Length(min=2, max=120)])
    email = StringField("Correo", validators=[DataRequired(), Email(), Length(max=255)])
    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(min=3, max=80),
            Regexp(r"^[A-Za-z0-9_.-]+$", message="Usa solamente letras, números, punto, guion o guion bajo."),
        ],
    )
    password = PasswordField("Contraseña", validators=[DataRequired(), Length(min=8, max=128)])
    confirm_password = PasswordField(
        "Confirmar contraseña",
        validators=[DataRequired(), EqualTo("password", message="Las contraseñas no coinciden.")],
    )
    submit = SubmitField("Crear cuenta")

    def validate_email(self, field):
        email = field.data.strip().lower()
        if db.session.scalar(db.select(User).where(User.email == email)):
            raise ValidationError("Ya existe una cuenta con este correo.")

    def validate_username(self, field):
        username = field.data.strip().lower()
        if db.session.scalar(db.select(User).where(User.username == username)):
            raise ValidationError("Este username ya está en uso.")


class LoginForm(FlaskForm):
    identity = StringField("Username o correo", validators=[DataRequired(), Length(max=255)])
    password = PasswordField("Contraseña", validators=[DataRequired(), Length(max=128)])
    remember = BooleanField("Mantener sesión")
    submit = SubmitField("Iniciar sesión")


class EmptyForm(FlaskForm):
    submit = SubmitField("Cerrar sesión")
