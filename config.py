"""Configuración central de la aplicación.

Centraliza los valores de configuración que la fábrica ``create_app()``
lee al inicializar la aplicación.
"""

import os

# Directorio base del proyecto (donde vive este archivo).
BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Clase de configuración aplicada por defecto a la aplicación."""

    # Clave secreta usada para firmar cookies de sesión y tokens CSRF.
    # En producción debe reemplazarse con un valor propio y seguro.
    SECRET_KEY = os.environ.get("SECRET_KEY") or "clave-de-desarrollo-cambiar-en-produccion"

    # Base de datos SQLite alojada en el directorio instance/.
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or (
        "sqlite:///" + os.path.join(BASE_DIR, "instance", "app.db")
    )

    # Desactiva el sistema de eventos de SQLAlchemy (innecesario y costoso).
    SQLALCHEMY_TRACK_MODIFICATIONS = False
