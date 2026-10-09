"""Paquete principal de la aplicación Flask.

Expone la fábrica ``create_app()`` que centraliza la creación, la
configuración, el registro de extensiones y blueprints, y el manejo
de errores de la aplicación.
"""

import os

from flask import Flask, render_template
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

from config import Config

# Instancias de extensiones compartidas por toda la aplicación.
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()


def create_app(config_class=Config):
    """Crea y configura la aplicación Flask (patrón application factory).

    Args:
        config_class: clase de configuración a usar (por defecto ``Config``).

    Returns:
        Una instancia de Flask lista para ejecutarse.
    """
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    # Garantiza que exista el directorio de la instancia (instance/).
    os.makedirs(app.instance_path, exist_ok=True)

    # Inicializa las extensiones.
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Página a la que redirige @login_required cuando no hay sesión activa.
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Debes iniciar sesión para continuar."
    login_manager.login_message_category = "warning"

    # Registro de blueprints (rutas de cada módulo).
    from app.routes import auth, main, orders, payments, products

    app.register_blueprint(auth.bp)
    app.register_blueprint(main.bp)
    app.register_blueprint(products.bp)
    app.register_blueprint(orders.bp)
    app.register_blueprint(payments.bp)

    # Importa los modelos para que SQLAlchemy conozca las tablas.
    from app import models  # noqa: F401

    # Crea las tablas que falten y añade las columnas nuevas a las ya
    # existentes (db.create_all() no altera tablas creadas).
    with app.app_context():
        db.create_all()
        ensure_columns()

    @app.context_processor
    def inject_year():
        """Inyecta el año actual en las plantillas (pie de página)."""
        from datetime import datetime

        return {"year": datetime.now().year}

    @app.context_processor
    def inject_mercado_pago():
        """Inyecta si Mercado Pago está configurado (para mostrar su botón)."""
        token = str(app.config.get("MP_ACCESS_TOKEN", "")).strip()
        return {"mp_configured": bool(token)}

    @app.errorhandler(404)
    def page_not_found(error):
        """Muestra una página amigable cuando el recurso no existe."""
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def forbidden(error):
        """Muestra una página amigable cuando el acceso está prohibido."""
        return render_template("errors/403.html"), 403

    @app.errorhandler(500)
    def internal_server_error(error):
        """Limpia la sesión de la BD y muestra una página de error interno."""
        db.session.rollback()
        return render_template("errors/500.html"), 500

    return app


def ensure_columns():
    """Añade a las tablas ya existentes las columnas nuevas que falten.

    ``db.create_all()`` no altera tablas creadas y SQLite no ofrece
    ``ADD COLUMN IF NOT EXISTS``, así que se comprueba columna a columna
    la tabla de cobros antes de emitir el ``ALTER TABLE``. Solo se añaden
    columnas: nunca se modifican ni se eliminan datos existentes.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    if "payments" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("payments")}
    additions = (
        ("mp_id", "VARCHAR(30)"),
        ("mp_method", "VARCHAR(30) NOT NULL DEFAULT ''"),
        ("status_detail", "VARCHAR(40) NOT NULL DEFAULT ''"),
    )
    with db.engine.begin() as connection:
        for name, ddl in additions:
            if name not in existing:
                connection.execute(
                    text(f"ALTER TABLE payments ADD COLUMN {name} {ddl}")
                )


@login_manager.user_loader
def load_user(user_id):
    """Carga el usuario activo a partir de su id (lo necesita Flask-Login)."""
    from app.models import User

    return db.session.get(User, int(user_id))
