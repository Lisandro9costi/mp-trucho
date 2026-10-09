"""Modelos de la base de datos (SQLAlchemy).

Define las tablas del simulador: usuarios, catálogo de productos,
pedidos con sus líneas de detalle y los pagos asociados.
"""

from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from app import db


def utcnow():
    """Devuelve la hora actual en UTC como ``datetime`` sin zona horaria."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(db.Model):
    """Usuario del sistema con rol ``cliente`` o ``admin``."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    orders = db.relationship(
        "Order",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select",
    )

    @property
    def is_active(self):
        """Flask-Login exige este atributo: toda cuenta registrada está activa."""
        return True

    @property
    def is_authenticated(self):
        """Flask-Login marca como autenticado a cualquier usuario cargado."""
        return True

    @property
    def is_anonymous(self):
        """Flask-Login: los usuarios reales nunca son anónimos."""
        return False

    def get_id(self):
        """Devuelve el id como cadena: es lo que Flask-Login guarda en sesión."""
        return str(self.id)

    @property
    def password(self):
        """Expone solo la escritura: la contraseña nunca se devuelve en claro."""
        raise AttributeError("La contraseña solo se puede asignar, no leer.")

    @password.setter
    def password(self, value):
        """Guarda la contraseña como hash (nunca en texto plano)."""
        self.password_hash = generate_password_hash(value)

    def check_password(self, value):
        """Verifica que ``value`` coincida con el hash almacenado.

        Args:
            value: contraseña en texto plano enviada por el usuario.

        Returns:
            ``True`` si coincide, ``False`` en caso contrario.
        """
        return check_password_hash(self.password_hash, value)

    def __repr__(self):
        """Representación legible para depuración."""
        return f"<User {self.email}>"


class Product(db.Model):
    """Producto del catálogo con precio y stock controlable."""

    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(40), unique=True, nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, default="", nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    stock = db.Column(db.Integer, nullable=False, default=0)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    items = db.relationship(
        "OrderItem",
        back_populates="product",
        lazy="select",
    )

    @property
    def is_available(self):
        """Indica si el producto puede venderse (activo y con stock)."""
        return self.active and self.stock > 0

    def __repr__(self):
        """Representación legible para depuración."""
        return f"<Product {self.sku}>"


class Order(db.Model):
    """Pedido de venta realizado por un cliente."""

    __tablename__ = "orders"

    # Estados posibles del ciclo de vida del pedido.
    STATUSES = ("pendiente", "pagado", "enviado", "cancelado")

    id = db.Column(db.Integer, primary_key=True)
    reference = db.Column(db.String(40), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="pendiente", index=True)
    total = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    notes = db.Column(db.Text, default="", nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    user = db.relationship("User", back_populates="orders")
    items = db.relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="select",
    )
    payments = db.relationship(
        "Payment",
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="select",
    )

    @property
    def paid_amount(self):
        """Suma de los importes de los pagos aprobados del pedido."""
        return sum(
            (p.amount for p in self.payments if p.status == "aprobado"),
            start=0,
        )

    @property
    def balance(self):
        """Diferencia entre el total del pedido y lo ya cobrado."""
        from decimal import Decimal

        return Decimal(self.total) - Decimal(self.paid_amount)

    @property
    def item_count(self):
        """Cantidad total de unidades del pedido."""
        return sum(item.quantity for item in self.items)

    def recalculate_total(self):
        """Recalcula ``total`` a partir del precio actual de las líneas."""
        from decimal import Decimal

        self.total = sum(
            (item.line_total for item in self.items),
            start=Decimal("0"),
        )

    def __repr__(self):
        """Representación legible para depuración."""
        return f"<Order {self.reference}>"


class OrderItem(db.Model):
    """Línea de detalle: producto + cantidad + precio congelado."""

    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True
    )
    product_id = db.Column(
        db.Integer, db.ForeignKey("products.id"), nullable=False, index=True
    )
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    order = db.relationship("Order", back_populates="items")
    product = db.relationship("Product", back_populates="items")

    @property
    def line_total(self):
        """Importe de la línea (``unit_price`` por ``quantity``)."""
        from decimal import Decimal

        return Decimal(self.unit_price) * Decimal(self.quantity)

    def __repr__(self):
        """Representación legible para depuración."""
        return f"<OrderItem order={self.order_id} qty={self.quantity}>"


class Payment(db.Model):
    """Cobro asociado a un pedido, con método y resultado."""

    __tablename__ = "payments"

    # Métodos de pago soportados por el simulador.
    METHODS = ("tarjeta", "efectivo", "transferencia")

    # Estados del cobro.
    STATUSES = ("pendiente", "aprobado", "rechazado")

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(
        db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True
    )
    amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    method = db.Column(db.String(20), nullable=False, default="tarjeta")
    status = db.Column(db.String(20), nullable=False, default="pendiente", index=True)
    reference = db.Column(db.String(40), unique=True, nullable=False, index=True)
    # Identificador del pago en Mercado Pago (vacío en el simulador local).
    mp_id = db.Column(db.String(30), nullable=True, index=True)
    # Medio de pago detectado por la API (visa, master, efectivo...).
    mp_method = db.Column(db.String(30), nullable=False, default="")
    # Motivo del resultado según la API (accredited, cc_rejected_...).
    status_detail = db.Column(
        db.String(40), nullable=False, default="", server_default=""
    )
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    order = db.relationship("Order", back_populates="payments")

    def __repr__(self):
        """Representación legible para depuración."""
        return f"<Payment {self.reference} {self.status}>"
