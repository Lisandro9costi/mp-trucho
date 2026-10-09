"""Arranque real del servidor + peticiones HTTP sobre los endpoints.

Uso:  python smoke_http.py

Levanta el servidor en un hilo, hace peticiones reales con urllib
(manteniendo las cookies como lo haría un navegador) y comprueba que el
flujo completo (registro -> pedido -> cobro) funciona por HTTP.

Usa una base de datos temporal, así que no toca ``instance/app.db``.
"""

import os
import re
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from urllib.parse import urlencode

from werkzeug.serving import make_server

from config import Config
from app import create_app, db
from app.models import Product, User

BASE = "http://127.0.0.1:5099"
CSRF_RE = re.compile(r'name="csrf_token"[^>]*value="([^"]+)"')


class HttpSmokeConfig(Config):
    """Configuración con una base de datos descartable."""

    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(
        tempfile.gettempdir(), "simulador_smoke_http.db"
    )
    # Sin credenciales reales: el .env del entorno no debe filtrarse.
    MP_ACCESS_TOKEN = ""
    MP_NOTIFICATION_URL = ""


def _opener():
    """Devuelve ``(opener, cookiejar)``: cookies persistentes como un navegador."""
    jar = CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        NoRedirect(),
    )
    return opener, jar


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Impide seguir redirecciones: cada POST se evalúa por separado."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Devuelve ``None`` para que urllib no siga la redirección."""
        return None


def request(opener, path, fields=None):
    """Ejecuta una petición y devuelve ``(status, html)``.

    Args:
        opener: opener con manejo de cookies.
        path: ruta relativa, por ejemplo ``/auth/login``.
        fields: ``None`` para GET, o un dict para el cuerpo del POST.

    Returns:
        Tupla con el código de estado y el HTML de la respuesta.
    """
    data = None
    if fields is not None:
        data = urlencode(fields).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, method="POST" if data else "GET")
    if data:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with opener.open(req) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def token_of(opener, path):
    """Descarga una página y extrae su token CSRF."""
    _, html = request(opener, path)
    match = CSRF_RE.search(html)
    return match.group(1) if match else ""


def main():
    """Arranca el servidor y comprueba el flujo por HTTP real."""
    db_path = HttpSmokeConfig.SQLALCHEMY_DATABASE_URI.replace("sqlite:///", "")
    if os.path.exists(db_path):
        os.remove(db_path)

    app = create_app(HttpSmokeConfig)
    with app.app_context():
        admin = User(name="Admin", email="admin@example.com", is_admin=True)
        admin.password = "admin123"
        db.session.add(admin)
        db.session.add(Product(sku="HTTP-1", name="Producto HTTP", price="12.34", stock=10))
        db.session.commit()

    server = make_server("127.0.0.1", 5099, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.5)

    failures = []

    def check(name, condition):
        """Registra el resultado de una comprobación."""
        print(f"{'OK   ' if condition else 'FALLO'} {name}")
        if not condition:
            failures.append(name)

    try:
        opener, jar = _opener()

        # --- Páginas públicas ---
        status, html = request(opener, "/")
        check("GET / responde 200", status == 200)
        check("portada trae el título", "Simulador" in html)

        status, _ = request(opener, "/productos/")
        check("GET /productos/ responde 200", status == 200)

        # --- Registro: crea sesión real ---
        token = token_of(opener, "/auth/register")
        status, html = request(
            opener,
            "/auth/register",
            {
                "csrf_token": token,
                "name": "Cliente HTTP",
                "email": "clientehttp@example.com",
                "password": "secreto123",
                "password2": "secreto123",
            },
        )
        check("registro redirige (302)", status == 302)
        cookies = {c.name for c in jar}
        check("registro crea sesión", "session" in cookies)

        # El usuario quedó autenticado: el panel ya no redirige al login.
        status, html = request(opener, "/panel")
        check("panel accesible tras registrar", status == 200 and "Panel de" in html)

        # --- CSRF activo ---
        status, _ = request(opener, "/pedidos/nuevo", {"product_id": "1", "quantity": "1"})
        check("POST sin token CSRF rechazado (400)", status == 400)

        # --- Alta de pedido ---
        with app.app_context():
            product_id = db.session.scalar(
                db.select(Product.id).where(Product.sku == "HTTP-1")
            )

        token = token_of(opener, "/pedidos/nuevo")
        status, html = request(
            opener,
            "/pedidos/nuevo",
            {
                "csrf_token": token,
                "product_id": str(product_id),
                "quantity": "1",
                "notes": "Pedido HTTP",
            },
        )
        check("alta de pedido redirige al detalle (302)", status == 302)

        with app.app_context():
            from app.models import Order

            pedido = db.session.scalar(
                db.select(Order).where(Order.notes == "Pedido HTTP")
            )
            order_id = pedido.id if pedido else None
            total = pedido.total if pedido else None
        check("el pedido se guardó", order_id is not None)

        # --- Cobro ---
        if order_id:
            token = token_of(opener, f"/pagos/pedido/{order_id}")
            status, html = request(
                opener,
                f"/pagos/pedido/{order_id}",
                {
                    "csrf_token": token,
                    "amount": str(total),
                    "method": "efectivo",
                },
            )
            check("cobro redirige (302)", status == 302)

            _, detalle = request(opener, f"/pedidos/{order_id}")
            check("detalle muestra el cobro aprobado", "aprobado" in detalle)

            with app.app_context():
                order = db.session.get(Order, order_id)
                check("el pedido queda pagado", order.status == "pagado")

        # --- Logout y acceso restringido ---
        status, _ = request(opener, "/auth/logout")
        check("logout redirige (302)", status == 302)
        status, _ = request(opener, "/panel")
        check("tras salir, el panel redirige", status == 302)

        # --- Webhook de Mercado Pago (público y exento de CSRF) ---
        status, _ = request(opener, "/pagos/webhook?topic=payment&id=1")
        check("webhook MP responde 200 sin sesión", status == 200)
        status, _ = request(
            opener, "/pagos/webhook?type=payment&id=1", {"dummy": "1"}
        )
        check("webhook MP acepta POST sin CSRF (exento)", status == 200)

        # --- 404 ---
        status, html = request(opener, "/no-existe")
        check("ruta inexistente responde 404", status == 404)
        check("la página 404 es la del proyecto", "Volver al inicio" in html)
    finally:
        server.shutdown()
        thread.join(timeout=5)

    print()
    if failures:
        print(f"{len(failures)} comprobación(es) fallida(s):")
        for name in failures:
            print(f"  - {name}")
        return 1

    print("Servidor real OK: todas las comprobaciones pasaron.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
