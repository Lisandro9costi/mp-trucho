"""Rutas principales: página de inicio y panel de resumen."""

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app import db
from app.models import Order, Payment, Product

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    """Muestra la portada con un resumen general del simulador."""
    return render_template("main/index.html")


@bp.route("/panel")
@login_required
def panel():
    """Muestra métricas de pedidos y cobros según el rol del usuario."""
    if current_user.is_admin:
        orders = db.session.scalars(db.select(Order)).all()
        payments = db.session.scalars(db.select(Payment)).all()
        products = db.session.scalars(db.select(Product)).all()
    else:
        orders = (
            db.session.scalars(
                db.select(Order).where(Order.user_id == current_user.id)
            )
            .unique()
            .all()
        )
        order_ids = [o.id for o in orders]
        payments = (
            db.session.scalars(
                db.select(Payment).where(Payment.order_id.in_(order_ids or [0]))
            )
            .unique()
            .all()
            if order_ids
            else []
        )
        products = []

    # El total cobrado solo cuenta pagos aprobados.
    cobrado = sum(float(p.amount) for p in payments if p.status == "aprobado")

    return render_template(
        "main/panel.html",
        orders=orders,
        payments=payments,
        products=products,
        cobrado=cobrado,
    )
