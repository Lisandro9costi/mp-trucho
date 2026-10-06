"""Rutas de pedidos: creación, listado, detalle, envío y cancelación."""

import secrets
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app import db
from app.forms import OrderForm
from app.models import Order, OrderItem, Product
from app.routes import admin_required, owner_or_admin

bp = Blueprint("orders", __name__, url_prefix="/pedidos")


def _generate_reference(prefix="PED"):
    """Genera una referencia única y legible para un pedido."""
    stamp = datetime.now().strftime("%Y%m%d")
    return f"{prefix}-{stamp}-{secrets.token_hex(3).upper()}"


@bp.route("/")
@login_required
def list_orders():
    """Lista los pedidos del usuario activo (o todos, si es admin)."""
    query = db.select(Order).order_by(Order.created_at.desc())
    if not current_user.is_admin:
        query = query.where(Order.user_id == current_user.id)

    orders = db.session.scalars(query).unique().all()
    return render_template("orders/list.html", orders=orders)


@bp.route("/nuevo", methods=["GET", "POST"])
@login_required
def create():
    """Crea un pedido con una línea de producto y descuenta el stock."""
    form = OrderForm()
    # El select se arma con los productos disponibles en cada visita.
    form.product_id.choices = [
        (p.id, f"{p.name} — {p.price} € (stock {p.stock})")
        for p in db.session.scalars(
            db.select(Product).where(
                Product.active.is_(True), Product.stock > 0
            ).order_by(Product.name)
        ).unique().all()
    ]

    if form.validate_on_submit():
        product = db.get_or_404(Product, form.product_id.data)
        quantity = int(form.quantity.data)

        # No se permite vender más stock del disponible.
        if not product.is_available:
            flash("El producto no está disponible.", "error")
        elif quantity > product.stock:
            flash(f"Solo quedan {product.stock} unidades de {product.name}.", "error")
        else:
            order = Order(
                reference=_generate_reference(),
                user_id=current_user.id,
                notes=form.notes.data or "",
            )
            # El precio se congela al momento del pedido.
            order.items.append(
                OrderItem(product=product, quantity=quantity, unit_price=product.price)
            )
            order.recalculate_total()

            product.stock -= quantity
            db.session.add(order)
            db.session.commit()
            flash(f"Pedido {order.reference} creado.", "success")
            return redirect(url_for("orders.detail", order_id=order.id))

    return render_template("orders/create.html", form=form)


@bp.route("/<int:order_id>")
@login_required
def detail(order_id):
    """Muestra el detalle de un pedido y sus pagos."""
    order = db.get_or_404(Order, order_id)
    if not owner_or_admin(order):
        abort(403)
    return render_template("orders/detail.html", order=order)


@bp.route("/<int:order_id>/enviar", methods=["POST"])
@login_required
@admin_required
def ship(order_id):
    """Marca un pedido pagado como enviado."""
    order = db.get_or_404(Order, order_id)
    if order.status != "pagado":
        flash("Solo se pueden enviar pedidos pagados.", "error")
    else:
        order.status = "enviado"
        db.session.commit()
        flash(f"Pedido {order.reference} enviado.", "success")
    return redirect(url_for("orders.detail", order_id=order.id))


@bp.route("/<int:order_id>/cancelar", methods=["POST"])
@login_required
def cancel(order_id):
    """Cancela un pedido y devuelve el stock al inventario."""
    order = db.get_or_404(Order, order_id)
    if not owner_or_admin(order):
        abort(403)

    if order.status == "enviado":
        flash("No se puede cancelar un pedido ya enviado.", "error")
    elif order.status == "cancelado":
        flash("El pedido ya estaba cancelado.", "info")
    else:
        # Se devuelve el stock de cada línea al catálogo.
        for item in order.items:
            item.product.stock += item.quantity
        order.status = "cancelado"
        db.session.commit()
        flash(f"Pedido {order.reference} cancelado.", "info")

    return redirect(url_for("orders.detail", order_id=order.id))
