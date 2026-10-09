"""Cliente de la API de Mercado Pago (Checkout Pro vía Preferences API).

Está implementado con ``urllib`` de la biblioteca estándar, así que no
añade dependencias. Solo el servidor usa el Access Token; el navegador
recibe únicamente la URL de inicio del checkout.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from flask import current_app


class MercadoPagoError(Exception):
    """Error al comunicarse con la API de Mercado Pago.

    Args:
        message: descripción del problema.
        status_code: código HTTP devuelto por la API, si lo hubo.
    """

    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


# Traducción de los estados remotos a los estados internos del simulador.
# Todo lo que no sea un cobro aprobado o rechazado queda como pendiente.
_STATUS_MAP = {
    "approved": "aprobado",
    "rejected": "rechazado",
    "cancelled": "rechazado",
    "refunded": "rechazado",
    "charged_back": "rechazado",
}

# Tipos de pago excluidos en el checkout para dejar un único medio: la
# transferencia bancaria (``bank_transfer``). El saldo en cuenta
# (``account_money``) no se puede excluir: Mercado Pago lo muestra siempre.
EXCLUDED_PAYMENT_TYPES = (
    "credit_card",
    "debit_card",
    "prepaid_card",
    "ticket",
    "atm",
    "digital_currency",
    "voucher_card",
    "crypto_transfer",
)


def is_configured():
    """Indica si hay un Access Token configurado.

    Returns:
        ``True`` cuando ``MP_ACCESS_TOKEN`` tiene un valor no vacío.
    """
    return bool(str(current_app.config.get("MP_ACCESS_TOKEN", "")).strip())


def map_status(status):
    """Traduce un estado de Mercado Pago al estado interno del simulador.

    Args:
        status: cadena devuelta por la API (``approved``, ``pending``...).

    Returns:
        ``"aprobado"``, ``"rechazado"`` o ``"pendiente"``.
    """
    return _STATUS_MAP.get(str(status or "").lower(), "pendiente")


def _request(method, path, payload=None):
    """Ejecuta una llamada HTTP autenticada contra la API.

    Args:
        method: ``"GET"`` o ``"POST"``.
        path: ruta relativa, por ejemplo ``/checkout/preferences``.
        payload: diccionario a serializar como JSON (solo para POST).

    Returns:
        Tupla ``(status_code, dict)`` con la respuesta ya decodificada.

    Raises:
        MercadoPagoError: si la API responde con error o no hay conexión.
    """
    base = str(
        current_app.config.get("MP_API_URL", "https://api.mercadopago.com")
    ).rstrip("/")
    token = str(current_app.config.get("MP_ACCESS_TOKEN", "")).strip()
    timeout = int(current_app.config.get("MP_TIMEOUT", 10))

    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(f"{base}{path}", data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise MercadoPagoError(
            f"Mercado Pago respondió {exc.code}: {detail[:200]}",
            status_code=exc.code,
        ) from exc
    except urllib.error.URLError as exc:
        raise MercadoPagoError(
            f"No se pudo conectar con Mercado Pago: {exc.reason}"
        ) from exc


def _normalize(result):
    """Reduce una respuesta de pago a los campos que usa la aplicación.

    Args:
        result: diccionario devuelto por la API para un pago.

    Returns:
        Diccionario con ``id``, ``status``, ``status_detail``,
        ``payment_method_id`` y ``external_reference`` como cadenas.
    """
    return {
        "id": str(result.get("id", "")),
        "status": result.get("status", ""),
        "status_detail": result.get("status_detail", ""),
        "payment_method_id": result.get("payment_method_id", ""),
        "external_reference": result.get("external_reference", ""),
    }


def create_preference(reference, amount, description, payer_email, base_url):
    """Crea una preferencia de pago y devuelve su URL de inicio.

    Args:
        reference: ``external_reference`` (la referencia del cobro local).
        amount: importe total a cobrar.
        description: texto que verá el comprador en el checkout.
        payer_email: correo del comprador.
        base_url: raíz pública del sitio para construir las ``back_urls``.

    Returns:
        La URL ``init_point`` a la que hay que redirigir al comprador.

    Raises:
        MercadoPagoError: si la API rechaza la creación de la preferencia
            o no devuelve una URL de inicio.
    """
    currency = current_app.config.get("MP_CURRENCY", "ARS")
    notification_url = str(current_app.config.get("MP_NOTIFICATION_URL", "")).strip()
    back_urls = {
        "success": f"{base_url}/pagos/retorno",
        "pending": f"{base_url}/pagos/retorno",
        "failure": f"{base_url}/pagos/retorno",
    }

    preference = {
        "items": [
            {
                "title": description,
                "quantity": 1,
                "currency_id": currency,
                "unit_price": float(amount),
            }
        ],
        "payer": {"email": payer_email},
        "external_reference": reference,
        "back_urls": back_urls,
        "payment_methods": {
            "excluded_payment_types": [
                {"id": payment_type} for payment_type in EXCLUDED_PAYMENT_TYPES
            ],
        },
    }
    if notification_url:
        preference["notification_url"] = notification_url

    _, result = _request("POST", "/checkout/preferences", preference)
    init_point = result.get("init_point") or result.get("sandbox_init_point")
    if not init_point:
        raise MercadoPagoError("Mercado Pago no devolvió una URL de inicio.")
    return init_point


def get_payment(payment_id):
    """Consulta el estado de un pago concreto.

    Args:
        payment_id: identificador del pago en Mercado Pago.

    Returns:
        Diccionario normalizado (ver :func:`_normalize`).

    Raises:
        MercadoPagoError: si la API responde con error.
    """
    _, result = _request("GET", f"/v1/payments/{payment_id}")
    return _normalize(result)


def find_payment(reference):
    """Busca el último pago asociado a una referencia externa.

    Se usa cuando todavía no se conoce el ``payment_id`` (por ejemplo,
    tras volver del checkout): la búsqueda va por ``external_reference``.

    Args:
        reference: ``external_reference`` con la que se creó la preferencia.

    Returns:
        Diccionario normalizado del pago más reciente, o ``None`` si no
        hay ninguno con esa referencia.

    Raises:
        MercadoPagoError: si la API responde con error.
    """
    query = urllib.parse.quote(reference)
    _, result = _request("GET", f"/v1/payments/search?external_reference={query}")
    results = result.get("results") or []
    if not results:
        return None
    return _normalize(results[0])
