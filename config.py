"""Configuración central de la aplicación.

Centraliza los valores de configuración que la fábrica ``create_app()``
lee al inicializar la aplicación.
"""

import os

from dotenv import load_dotenv

# Directorio base del proyecto (donde vive este archivo).
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Carga las variables del archivo .env (ignorado por git) si existe. Así
# las credenciales no viven en el repositorio ni en este archivo.
load_dotenv(os.path.join(BASE_DIR, ".env"))


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

    # --- Mercado Pago (Checkout Pro) ---
    # Access Token privado de la aplicación: sin él la app cobra con el
    # simulador local. En pruebas empieza por APP_USR (Tus integraciones >
    # Datos de integración > Pruebas > Credenciales).
    MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN", "")

    # Raíz de la API; se puede apuntar a un proxy o mock en pruebas.
    MP_API_URL = os.environ.get("MP_API_URL", "https://api.mercadopago.com")

    # Segundos de espera antes de cortar una llamada a la API.
    MP_TIMEOUT = int(os.environ.get("MP_TIMEOUT", "10"))

    # Raíz pública del sitio, usada para construir las back_urls. En
    # local se usa el servidor de desarrollo; en producción, el dominio
    # real (Mercado Pago exige https en back_urls y notification_url).
    MP_BASE_URL = os.environ.get("MP_BASE_URL", "http://127.0.0.1:5000")

    # URL pública que recibe las notificaciones (webhook). Vacía por
    # defecto para no enviar a Mercado Pago una URL local inalcanzable.
    MP_NOTIFICATION_URL = os.environ.get("MP_NOTIFICATION_URL", "")

    # Moneda de la preferencia (Mercado Pago no acepta EUR).
    MP_CURRENCY = os.environ.get("MP_CURRENCY", "ARS")
