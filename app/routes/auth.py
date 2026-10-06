"""Rutas de autenticación: registro, inicio y cierre de sesión."""

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app import db
from app.forms import LoginForm, RegisterForm
from app.models import User

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/register", methods=["GET", "POST"])
def register():
    """Crea una cuenta de cliente (sin privilegios de administrador)."""
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = RegisterForm()
    if form.validate_on_submit():
        user = User(
            name=form.name.data,
            email=form.email.data.lower(),
        )
        user.password = form.password.data

        # El correo es único: se avisa sin revelar nada más.
        if db.session.scalar(db.select(User).where(User.email == user.email)):
            flash("Ese correo ya está registrado.", "error")
        else:
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("¡Cuenta creada! Ya puedes empezar a simular ventas.", "success")
            return redirect(url_for("main.panel"))

    return render_template("auth/register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    """Autentica al usuario por correo y contraseña."""
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.scalar(
            db.select(User).where(User.email == form.email.data.lower())
        )
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            flash(f"Hola, {user.name}.", "success")
            return redirect(url_for("main.panel"))
        flash("Correo o contraseña incorrectos.", "error")

    return render_template("auth/login.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    """Cierra la sesión del usuario activo."""
    logout_user()
    flash("Sesión cerrada.", "info")
    return redirect(url_for("main.index"))
