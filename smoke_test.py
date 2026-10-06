"""Prueba de humo del simulador: recorre el flujo completo.

Uso:  python smoke_test.py

Trabaja sobre una base de datos temporal, así que no toca
``instance/app.db`` ni necesita haber ejecutado ``seed.py``.
"""

import os
import re
import tempfile

from config import Config
from app import create_app, db
from app.models import Order, OrderItem, Payment, Product, User

# WTForms puede intercalar atributos (por ejemplo type="hidden") entre el
# name y el value, así que el patrón admite cualquier cosa en medio.
CSRF_RE = re.compile(r'name="csrf_token"[^>]*value="([^"]+)"')

# SKU único por ejecución para que el test sea repetible.
SKU = f"TEST-{os.getpid()}"


class SmokeConfig(Config):
    """Configuración que apunta a una base de datos descartable."""

    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(
        tempfile.gettempdir(), "simulador_smoke_test.db"
    )
    WTF_CSRF_ENABLED = True
    TESTING = True


def _csrf(client, url):
    """Extrae el token CSRF de un formulario renderizado."""
    html = client.get(url).get_data(as_text=True)
    match = CSRF_RE.search(html)
    return match.group(1) if match else ""


def _login(client, email, password):
    """Inicia sesión y devuelve la respuesta del POST."""
    return client.post(
        "/auth/login",
        data={
            "csrf_token": _csrf(client, "/auth/login"),
            "email": email,
            "password": password,
        },
    )


def _seed(app):
    """Crea el usuario administrador y un cliente para poder probar roles."""
    admin = User(name="Admin", email="admin@example.com", is_admin=True)
    admin.password = "admin123"
    cliente = User(name="Cliente", email="cliente@example.com")
    cliente.password = "cliente123"
    db.session.add_all([admin, cliente])
    db.session.commit()


def main():
    """Ejecuta las comprobaciones y devuelve 0 si todo pasa."""
    # Se parte siempre de una base limpia.
    db_path = SmokeConfig.SQLALCHEMY_DATABASE_URI.replace("sqlite:///", "")
    if os.path.exists(db_path):
        os.remove(db_path)

    app = create_app(SmokeConfig)
    failures = []

    with app.app_context():
        _seed(app)

    client = app.test_client()

    def check(name, condition):
        """Registra el resultado de una comprobación."""
        print(f"{'OK   ' if condition else 'FALLO'} {name}")
        if not condition:
            failures.append(name)

    # --- Rutas públicas y protecciones ---
    check("GET /", client.get("/").status_code == 200)
    check("GET /productos/", client.get("/productos/").status_code == 200)
    check("GET /auth/login", client.get("/auth/login").status_code == 200)
    check("GET /auth/register", client.get("/auth/register").status_code == 200)
    check("GET /panel redirige a login", client.get("/panel").status_code == 302)
    check("GET /ruta-inexistente -> 404", client.get("/nope").status_code == 404)

    # --- Registro de una cuenta nueva ---
    resp = client.post(
        "/auth/register",
        data={
            "csrf_token": _csrf(client, "/auth/register"),
            "name": "Nueva Cuenta",
            "email": "nueva@example.com",
            "password": "secreto123",
            "password2": "secreto123",
        },
    )
    check(
        "registro redirige al panel",
        resp.status_code == 302 and resp.headers["Location"].endswith("/panel"),
    )
    client.get("/auth/logout")

    # --- Login del administrador ---
    resp = _login(client, "admin@example.com", "admin123")
    check(
        "login admin redirige al panel",
        resp.status_code == 302 and resp.headers["Location"].endswith("/panel"),
    )
    check("panel accesible para el admin", client.get("/panel").status_code == 200)

    # La contraseña incorrecta se rechaza: hay que salir antes porque /auth/login
    # redirige al inicio si ya hay sesión.
    client.get("/auth/logout")
    resp = _login(client, "admin@example.com", "malaclave")
    check(
        "contraseña incorrecta no entra",
        resp.status_code == 200
        and "incorrectos" in resp.get_data(as_text=True),
    )
    _login(client, "admin@example.com", "admin123")

    # --- Alta de producto (con CSRF) ---
    resp = client.post(
        "/productos/nuevo",
        data={
            "csrf_token": _csrf(client, "/productos/nuevo"),
            "sku": SKU,
            "name": "Producto de prueba",
            "description": "Creado por smoke_test.",
            "price": "12.34",
            "stock": "5",
            "active": "y",
        },
    )
    with app.app_context():
        producto = db.session.scalar(db.select(Product).where(Product.sku == SKU))
        product_id = producto.id if producto else None
    check("alta de producto", product_id is not None)

    # --- SKU duplicado rechazado ---
    resp = client.post(
        "/productos/nuevo",
        data={
            "csrf_token": _csrf(client, "/productos/nuevo"),
            "sku": SKU,
            "name": "Duplicado",
            "description": "",
            "price": "1.00",
            "stock": "1",
            "active": "y",
        },
        follow_redirects=True,
    )
    check(
        "SKU duplicado rechazado",
        "ya existe" in resp.get_data(as_text=True),
    )

    # --- Validación del formulario (precio obligatorio) ---
    resp = client.post(
        "/productos/nuevo",
        data={
            "csrf_token": _csrf(client, "/productos/nuevo"),
            "sku": f"{SKU}-B",
            "name": "Sin precio",
            "description": "",
            "price": "",
            "stock": "1",
            "active": "y",
        },
    )
    check("formulario de producto valida", resp.status_code == 200)

    # --- Alta de pedido: descuenta stock y calcula el total ---
    resp = client.post(
        "/pedidos/nuevo",
        data={
            "csrf_token": _csrf(client, "/pedidos/nuevo"),
            "product_id": str(product_id),
            "quantity": "2",
            "notes": "Pedido de prueba",
        },
    )
    with app.app_context():
        pedido = db.session.scalar(
            db.select(Order).where(Order.notes == "Pedido de prueba")
        )
        order_id = pedido.id if pedido else None
        stock_restante = db.session.get(Product, product_id).stock
    check("alta de pedido", order_id is not None)
    check(
        "total calculado (2 x 12.34)",
        pedido is not None and float(pedido.total) == 24.68,
    )
    check("stock descontado (5 -> 3)", stock_restante == 3)

    # --- No se puede pedir más stock del disponible ---
    client.post(
        "/pedidos/nuevo",
        data={
            "csrf_token": _csrf(client, "/pedidos/nuevo"),
            "product_id": str(product_id),
            "quantity": "99",
            "notes": "Pedido imposible",
        },
        follow_redirects=True,
    )
    with app.app_context():
        imposible = db.session.scalar(
            db.select(Order).where(Order.notes == "Pedido imposible")
        )
    check("pedido sin stock suficiente rechazado", imposible is None)

    # --- Cobro por encima del saldo rechazado ---
    client.post(
        f"/pagos/pedido/{order_id}",
        data={
            "csrf_token": _csrf(client, f"/pagos/pedido/{order_id}"),
            "amount": "999.00",
            "method": "efectivo",
        },
        follow_redirects=True,
    )
    with app.app_context():
        pagos = db.session.scalars(
            db.select(Payment).where(Payment.order_id == order_id)
        ).all()
    check("cobro superior al saldo rechazado", len(pagos) == 0)

    # --- Cobro aprobado: efectivo salda el pedido ---
    resp = client.post(
        f"/pagos/pedido/{order_id}",
        data={
            "csrf_token": _csrf(client, f"/pagos/pedido/{order_id}"),
            "amount": "24.68",
            "method": "efectivo",
        },
        follow_redirects=True,
    )
    with app.app_context():
        pago = db.session.scalar(
            db.select(Payment).where(Payment.order_id == order_id).limit(1)
        )
        estado = db.session.get(Order, order_id).status
    check("cobro aprobado", pago is not None and pago.status == "aprobado")
    check("pedido pasa a pagado", estado == "pagado")
    check("flash de cobro", "aprobado" in resp.get_data(as_text=True))

    # --- Tarjeta con importe terminado en 0 se rechaza (regla del simulador) ---
    # El cliente paga su propio pedido con tarjeta: es el caso real de uso.
    client.get("/auth/logout")
    _login(client, "cliente@example.com", "cliente123")
    resp = client.post(
        "/pedidos/nuevo",
        data={
            "csrf_token": _csrf(client, "/pedidos/nuevo"),
            "product_id": str(product_id),
            "quantity": "1",
            "notes": "Pedido para rechazo",
        },
    )
    with app.app_context():
        pedido2 = db.session.scalar(
            db.select(Order).where(Order.notes == "Pedido para rechazo")
        )
        order2_id = pedido2.id
    resp = client.post(
        f"/pagos/pedido/{order2_id}",
        data={
            "csrf_token": _csrf(client, f"/pagos/pedido/{order2_id}"),
            "amount": "12.34",
            "method": "tarjeta",
        },
        follow_redirects=True,
    )
    with app.app_context():
        pago2 = db.session.scalar(
            db.select(Payment).where(Payment.order_id == order2_id).limit(1)
        )
        estado2 = db.session.get(Order, order2_id).status
    check("tarjeta se aprueba (importe no terminado en 0)", pago2 is not None and pago2.status == "aprobado")
    check("pedido del cliente pasa a pagado", estado2 == "pagado")

    # Un importe redondo con tarjeta debe rechazarse según la regla del simulador.
    with app.app_context():
        pedido3 = Order(
            reference="PED-TEST-RECH", user_id=_cliente_id(app), status="pendiente"
        )
        pedido3.items.append(
            OrderItem(product=db.session.get(Product, product_id), quantity=1, unit_price="20.00")
        )
        pedido3.recalculate_total()
        db.session.add(pedido3)
        db.session.commit()
        order3_id = pedido3.id
    resp = client.post(
        f"/pagos/pedido/{order3_id}",
        data={
            "csrf_token": _csrf(client, f"/pagos/pedido/{order3_id}"),
            "amount": "20.00",
            "method": "tarjeta",
        },
        follow_redirects=True,
    )
    with app.app_context():
        pago3 = db.session.scalar(
            db.select(Payment).where(Payment.order_id == order3_id).limit(1)
        )
        estado3 = db.session.get(Order, order3_id).status
    check("tarjeta con importe redondo se rechaza", pago3 is not None and pago3.status == "rechazado")
    check("pedido sigue pendiente tras rechazo", estado3 == "pendiente")

    # --- Envío solo por admin y solo desde pagado ---
    client.post(
        f"/pedidos/{order3_id}/enviar",
        data={"csrf_token": _csrf(client, f"/pedidos/{order3_id}")},
        follow_redirects=True,
    )
    with app.app_context():
        estado3 = db.session.get(Order, order3_id).status
    check("no se envía un pedido no pagado", estado3 == "pendiente")

    # --- Cancelar devuelve el stock ---
    with app.app_context():
        stock_antes = db.session.get(Product, product_id).stock
    client.post(
        f"/pedidos/{order3_id}/cancelar",
        data={"csrf_token": _csrf(client, f"/pedidos/{order3_id}")},
        follow_redirects=True,
    )
    with app.app_context():
        stock_despues = db.session.get(Product, product_id).stock
        estado3 = db.session.get(Order, order3_id).status
    check("cancelación devuelve el stock", stock_despues == stock_antes + 1)
    check("pedido cancelado", estado3 == "cancelado")

    client.get("/auth/logout")
    _login(client, "admin@example.com", "admin123")

    # --- Envío de un pedido pagado (admin) ---
    client.post(
        f"/pedidos/{order2_id}/enviar",
        data={"csrf_token": _csrf(client, f"/pedidos/{order2_id}")},
        follow_redirects=True,
    )
    with app.app_context():
        estado_enviado = db.session.get(Order, order2_id).status
    check("pedido pagado enviado", estado_enviado == "enviado")

    # --- Búsqueda de productos ---
    check(
        "búsqueda por nombre",
        "Producto de prueba" in client.get("/productos/?q=prueba").get_data(as_text=True),
    )

    # --- Un cliente no accede a rutas de admin ni a pedidos ajenos ---
    client.get("/auth/logout")
    resp = _login(client, "cliente@example.com", "cliente123")
    check(
        "login cliente redirige al panel",
        resp.status_code == 302 and resp.headers["Location"].endswith("/panel"),
    )
    check("panel accesible para el cliente", client.get("/panel").status_code == 200)
    check(
        "cliente recibe 403 en alta de producto",
        client.get("/productos/nuevo").status_code == 403,
    )
    check(
        "cliente puede crear sus propios pedidos",
        client.get("/pedidos/nuevo").status_code == 200,
    )
    check(
        "cliente no puede ver pedido ajeno (403)",
        client.get(f"/pedidos/{order_id}").status_code == 403,
    )
    # El token se pide en una página propia: /pedidos/<ajeno> ya responde 403
    # y no contiene formulario, así que daría 400 en vez de 403.
    cliente_token = _csrf(client, "/pedidos/nuevo")
    check(
        "cliente no puede enviar pedidos (403)",
        client.post(
            f"/pedidos/{order_id}/enviar",
            data={"csrf_token": cliente_token},
        ).status_code
        == 403,
    )
    check(
        "cliente solo ve sus cobros",
        client.get("/pagos/").status_code == 200,
    )
    check(
        "cliente ve 403 en edición de producto",
        client.get(f"/productos/{product_id}/editar").status_code == 403,
    )

    # --- Logout ---
    client.get("/auth/logout")
    check("logout cierra sesión", client.get("/panel").status_code == 302)

    print()
    if failures:
        print(f"{len(failures)} comprobación(es) fallida(s):")
        for name in failures:
            print(f"  - {name}")
        return 1

    print("Todas las comprobaciones pasaron.")
    # La conexión sigue abierta: el archivo temporal se limpia en el próximo
    # arranque (Windows no permite borrarlo con la BD en uso).
    return 0


def _cliente_id(app):
    """Devuelve el id del usuario cliente de prueba."""
    with app.app_context():
        return db.session.scalar(
            db.select(User.id).where(User.email == "cliente@example.com")
        )


if __name__ == "__main__":
    raise SystemExit(main())
