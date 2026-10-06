"""Rutas de cobro: registra pagos simulados sobre un pedido."""

import secrets
from decimal import Decimal

from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app import db
from app.forms import PaymentForm
from app.models import Order, Payment
from app.routes import admin_required, owner_or_admin

bp = Blueprint("payments", __name__, url_prefix="/pagos")


def _generate_reference(prefix="PAY"):
    """Genera una referencia única y legible para un pago."""
    from datetime import datetime

    stamp = datetime.now().strftime("%Y%m%d")
    return f"{prefix}-{stamp}-{secrets.token_hex(3).upper()}"


def _simulate(method, amount):
    """Decide el resultado del cobro según el método (lógica del simulador).

    Args:
        method: método de pago elegido.
        amount: importe del cobro.

    Returns:
        ``"aprobado"`` o ``"rechazado"``.
    """
    if method == "efectivo":
        return "aprobado"
    if method == "tarjeta":
        # Regla del simulador: los importes terminados en 0 se rechazan,
        # para poder probar el camino de error sin depender de una pasarela.
        return "rechazado" if amount % 10 == 0 else "aprobado"
    # Transferencia: se aprueba siempre, queda pendiente de conciliar.
    return "aprobado"


@bp.route("/pedido/<int:order_id>", methods=["GET", "POST"])
@login_required
def pay(order_id):
    """Registra un cobro contra el pedido indicado."""
    order = db.get_or_404(Order, order_id)
    if not owner_or_admin(order):
        abort(403)

    form = PaymentForm()
    form.method.choices = [(m, m.capitalize()) for m in Payment.METHODS]
    # Solo se propone el saldo pendiente en el GET: en un POST el importe
    # enviado por el usuario debe respetarse tal cual.
    if not form.is_submitted():
        form.amount.data = order.balance

    if form.validate_on_submit():
        amount = Decimal(form.amount.data)
        balance = order.balance

        if order.status in ("enviado", "cancelado"):
            flash("Este pedido ya no admite cobros.", "error")
        elif amount > balance:
            flash(f"El importe supera el saldo pendiente ({balance} €).", "error")
        else:
            payment = Payment(
                order=order,
                amount=amount,
                method=form.method.data,
                reference=_generate_reference(),
                status=_simulate(form.method.data, amount),
            )
            db.session.add(payment)

            # Un cobro aprobado que salda el pedido lo marca como pagado.
            if payment.status == "aprobado" and amount >= balance:
                order.status = "pagado"

            db.session.commit()
            if payment.status == "aprobado":
                flash(f"Cobro {payment.reference} aprobado.", "success")
            else:
                flash(
                    f"Cobro {payment.reference} rechazado por el simulador.", "error"
                )
            return redirect(url_for("orders.detail", order_id=order.id))

    return render_template("payments/pay.html", form=form, order=order)


@bp.route("/")
@login_required
def panel():
    """Lista los cobros: todos para el admin, los propios para el cliente."""
    query = db.select(Payment).order_by(Payment.created_at.desc())
    if not current_user.is_admin:
        order_ids = db.session.scalars(
            db.select(Order.id).where(Order.user_id == current_user.id)
        ).all()
        query = query.where(Payment.order_id.in_(list(order_ids) or [0]))

    payments = db.session.scalars(query).unique().all()
    return render_template("payments/panel.html", payments=payments)
