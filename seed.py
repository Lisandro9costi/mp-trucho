"""Carga de datos de prueba para el simulador.

Uso:  python seed.py

Es idempotente: se puede ejecutar varias veces sin duplicar registros.
"""

from datetime import datetime, timezone
from decimal import Decimal

from app import create_app, db
from app.models import Order, OrderItem, Payment, Product, User

# Catálogo inicial: (sku, nombre, descripción, precio, stock).
PRODUCTS = (
    ("CAF-001", "Café molido 250 g", "Tueste medio, molienda fina.", "9.90", 120),
    ("TE-002", "Té verde 100 g", "Sencha suelto.", "6.50", 80),
    ("VAS-003", "Vaso térmico 500 ml", "Acero inoxidable, cierre hermético.", "24.00", 40),
    ("MOL-004", "Molino manual", "Café en grano, ajuste de molienda.", "38.90", 15),
    ("SRV-005", "Servicio técnico a domicilio", "Montaje y revisión, 1 hora.", "45.00", 5),
)


def _utcnow():
    """Devuelve la hora actual en UTC sin zona horaria."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def seed_users():
    """Crea el administrador y dos clientes de prueba si no existen."""
    created = []

    accounts = (
        ("Admin Demo", "admin@simuladorapp.com", "admin123", True),
        ("Cliente Demo", "cliente@simuladorapp.com", "cliente123", False),
        ("Ana Ruiz", "ana@simuladorapp.com", "cliente123", False),
    )

    for name, email, password, is_admin in accounts:
        if db.session.scalar(db.select(User).where(User.email == email)):
            continue
        user = User(name=name, email=email, is_admin=is_admin)
        user.password = password
        db.session.add(user)
        created.append(email)

    db.session.commit()
    return created


def seed_products():
    """Inserta el catálogo inicial respetando los SKUs ya existentes."""
    created = []

    for sku, name, description, price, stock in PRODUCTS:
        if db.session.scalar(db.select(Product).where(Product.sku == sku)):
            continue
        db.session.add(
            Product(
                sku=sku,
                name=name,
                description=description,
                price=Decimal(price),
                stock=stock,
            )
        )
        created.append(sku)

    db.session.commit()
    return created


def seed_orders():
    """Crea un pedido pagado y uno pendiente, con sus cobros."""
    if db.session.scalar(db.select(Order).limit(1)):
        return []

    cliente = db.session.scalar(
        db.select(User).where(User.email == "cliente@simuladorapp.com")
    )
    ana = db.session.scalar(db.select(User).where(User.email == "ana@simuladorapp.com"))
    catalogo = db.session.scalars(db.select(Product).order_by(Product.sku)).all()

    if not (cliente and ana and len(catalogo) >= 2):
        return []

    ahora = _utcnow()
    creados = []

    # Pedido 1: pagado y enviado, con un cobro aprobado por tarjeta.
    pedido_pagado = Order(
        reference="PED-DEMO-0001",
        user=cliente,
        status="enviado",
        notes="Pedido de ejemplo ya cobrado.",
        created_at=ahora,
    )
    pedido_pagado.items.append(
        OrderItem(product=catalogo[0], quantity=2, unit_price=catalogo[0].price)
    )
    pedido_pagado.items.append(
        OrderItem(product=catalogo[2], quantity=1, unit_price=catalogo[2].price)
    )
    pedido_pagado.recalculate_total()
    pedido_pagado.payments.append(
        Payment(
            amount=pedido_pagado.total,
            method="tarjeta",
            status="aprobado",
            reference="PAY-DEMO-0001",
            created_at=ahora,
        )
    )
    db.session.add(pedido_pagado)
    creados.append(pedido_pagado.reference)

    # Pedido 2: pendiente de cobro, para probar el flujo de cobro.
    pedido_pendiente = Order(
        reference="PED-DEMO-0002",
        user=ana,
        status="pendiente",
        notes="Pendiente de pago.",
        created_at=ahora,
    )
    pedido_pendiente.items.append(
        OrderItem(product=catalogo[1], quantity=3, unit_price=catalogo[1].price)
    )
    pedido_pendiente.recalculate_total()
    db.session.add(pedido_pendiente)
    creados.append(pedido_pendiente.reference)

    db.session.commit()
    return creados


def main():
    """Ejecuta todos los pasos del seed e imprime el resumen."""
    app = create_app()
    with app.app_context():
        usuarios = seed_users()
        productos = seed_products()
        pedidos = seed_orders()

        print("Datos de prueba cargados.")
        print(f"  Usuarios nuevos: {usuarios or 'ninguno (ya existían)'}")
        print(f"  Productos nuevos: {productos or 'ninguno (ya existían)'}")
        print(f"  Pedidos nuevos: {pedidos or 'ninguno (ya existían)'}")
        print()
        print("Cuentas de prueba:")
        print("  admin@simuladorapp.com   / admin123    (administrador)")
        print("  cliente@simuladorapp.com / cliente123  (cliente)")
        print("  ana@simuladorapp.com     / cliente123  (cliente)")


if __name__ == "__main__":
    main()
