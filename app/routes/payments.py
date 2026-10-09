"""Rutas de cobro: Checkout Pro de Mercado Pago o simulador local.

El botón "Pagar con Mercado Pago" crea una preferencia y redirige al
comprador al checkout de Mercado Pago. Sin credenciales (variable
``MP_ACCESS_TOKEN``) se mantiene el comportamiento original: el cobro se
resuelve localmente con :func:`_simulate`.
"""

import secrets
from decimal import Decimal

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from app import csrf, db
from app.forms import PaymentForm
from app.models import Order, Payment
from app.routes import admin_required, owner_or_admin
from app.services import mercado_pago as mp

bp = Blueprint("payments", __name__, url_prefix="/pagos")


def _generate_reference(prefix="PAY"):
    """Genera una referencia única y legible para un pago."""
    from datetime import datetime

    stamp = datetime.now().strftime("%Y%m%d")
    return f"{prefix}-{stamp}-{secrets.token_hex(3).upper()}"


def _base_url():
    """Raíz pública del sitio para construir las ``back_urls``."""
    return str(
        current_app.config.get("MP_BASE_URL", "http://127.0.0.1:5000")
    ).rstrip("/")


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


def _apply_remote(payment, remote):
    """Aplica a un cobro el estado devuelto por Mercado Pago.

    Marca como ``pagado`` el pedido cuando el cobro aprobado lo salda, o
    lo devuelve a ``pendiente`` si un cobro aprobado pasa a rechazado y
    queda saldo por cobrar.

    Args:
        payment: fila de :class:`Payment` ya cargada en la sesión.
        remote: dict normalizado con ``status`` y ``status_detail``.
    """
    payment.status = mp.map_status(remote.get("status"))
    if remote.get("status_detail"):
        payment.status_detail = remote["status_detail"]
    if remote.get("payment_method_id"):
        payment.mp_method = remote["payment_method_id"]

    order = payment.order
    total = Decimal(str(order.total))
    balance = Decimal(str(order.balance))
    if payment.status == "aprobado" and Decimal(str(order.paid_amount)) >= total:
        order.status = "pagado"
    elif payment.status != "aprobado" and order.status == "pagado" and balance > 0:
        order.status = "pendiente"


def _announce(payment):
    """Muestra el resultado del cobro recién registrado.

    Args:
        payment: pago que acaba de guardarse en la base de datos.
    """
    origen = "Mercado Pago" if payment.method == "mercadopago" else "el simulador"
    if payment.status == "aprobado":
        flash(f"Cobro {payment.reference} aprobado por {origen}.", "success")
    elif payment.status == "pendiente":
        flash(
            f"Cobro {payment.reference} pendiente en {origen}"
            f" ({payment.status_detail or 'esperando confirmación'}).",
            "warning",
        )
    else:
        flash(
            f"Cobro {payment.reference} rechazado por {origen}"
            f" ({payment.status_detail or 'sin detalle'}).",
            "error",
        )


def _create_mp_payment(order, amount):
    """Crea el cobro local pendiente y la preferencia en Mercado Pago.

    Args:
        order: pedido que se está cobrando.
        amount: importe del cobro.

    Returns:
        La URL ``init_point`` del checkout de Mercado Pago.

    Raises:
        mercado_pago.MercadoPagoError: si la API rechaza la preferencia.
    """
    payment = Payment(
        order=order,
        amount=amount,
        method="mercadopago",
        reference=_generate_reference(),
        status="pendiente",
    )
    db.session.add(payment)
    # Se asigna la referencia antes de construir la preferencia: Mercado
    # Pago la recibe como external_reference para poder cruzar el cobro.
    db.session.flush()

    return mp.create_preference(
        reference=payment.reference,
        amount=amount,
        description=f"Cobro pedido {order.reference}",
        payer_email=current_user.email,
        base_url=_base_url(),
    )


def _sync_payment(payment):
    """Consulta en Mercado Pago el estado real de un cobro y lo aplica.

    Primero intenta por ``mp_id``; si aún no se conoce (por ejemplo tras
    volver del checkout), busca por ``external_reference``.

    Args:
        payment: fila de :class:`Payment` a sincronizar.

    Returns:
        El dict remoto aplicado, o ``None`` si Mercado Pago todavía no
        registró ningún pago con esa referencia.

    Raises:
        mercado_pago.MercadoPagoError: si la API responde con error.
    """
    remote = (
        mp.get_payment(payment.mp_id)
        if payment.mp_id
        else mp.find_payment(payment.reference)
    )
    if remote is None:
        return None

    payment.mp_id = remote.get("id") or payment.mp_id
    _apply_remote(payment, remote)
    return remote


@bp.route("/pedido/<int:order_id>", methods=["GET", "POST"])
@login_required
def pay(order_id):
    """Registra un cobro contra el pedido indicado.

    Con el botón ``go_mp`` y credenciales de Mercado Pago, redirige al
    checkout; en cualquier otro caso resuelve el cobro con el simulador.
    """
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
        elif "go_mp" in request.form and mp.is_configured():
            try:
                init_point = _create_mp_payment(order, amount)
            except mp.MercadoPagoError as exc:
                db.session.rollback()
                flash(f"No se pudo iniciar el pago: {exc}", "error")
                return render_template("payments/pay.html", form=form, order=order)

            db.session.commit()
            flash("Se redirige a Mercado Pago para completar el pago.", "info")
            return redirect(init_point)
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
            _announce(payment)
            return redirect(url_for("orders.detail", order_id=order.id))

    return render_template("payments/pay.html", form=form, order=order)


@bp.route("/retorno")
@login_required
def retorno():
    """Procesa el retorno del comprador desde el checkout de Mercado Pago.

    Mercado Pago agrega ``external_reference`` y ``payment_id`` a las
    ``back_urls``. Se consulta la API para confirmar el estado real,
    porque los parámetros de la URL no son confiables.
    """
    reference = request.args.get("external_reference", "").strip()
    payment = (
        db.session.scalar(db.select(Payment).where(Payment.reference == reference))
        if reference
        else None
    )
    if payment is None:
        flash("No se encontró el cobro del pago recibido.", "warning")
        return redirect(url_for("payments.panel"))

    if not owner_or_admin(payment.order):
        abort(403)

    if not mp.is_configured():
        flash(
            "El cobro sigue pendiente: faltan las credenciales de Mercado Pago.",
            "warning",
        )
        return redirect(url_for("orders.detail", order_id=payment.order_id))

    try:
        remote = _sync_payment(payment)
    except mp.MercadoPagoError as exc:
        flash(f"No se pudo confirmar el pago: {exc}", "error")
        return redirect(url_for("orders.detail", order_id=payment.order_id))

    db.session.commit()
    if remote is None:
        flash(
            "Mercado Pago todavía no registró el pago; probá sincronizar en unos segundos.",
            "info",
        )
    else:
        _announce(payment)
    return redirect(url_for("orders.detail", order_id=payment.order_id))


@bp.route("/webhook", methods=["GET", "POST"])
@csrf.exempt
def webhook():
    """Recibe las notificaciones de Mercado Pago y sincroniza el cobro.

    Acepta el formato v2 (cuerpo ``{"type": "payment", "data": {"id"}}``)
    y el IPN antiguo (``?topic=payment&id=...``). Mercado Pago exige una
    respuesta 2xx para no reintentar el envío.
    """
    payload = request.get_json(silent=True) or {}
    data = payload.get("data") or {}
    topic = payload.get("type") or request.args.get("topic") or request.args.get("type")
    mp_id = str(
        data.get("id") or request.args.get("id") or request.args.get("data.id") or ""
    ).strip()

    # Solo interesan los pagos: otros temas (merchant_order...) se ignoran.
    if not mp_id or (topic is not None and topic != "payment"):
        return ("Notificación ignorada.", 200)
    if not mp.is_configured():
        # Sin credenciales no hay nada que consultar: se responde 200 para
        # que Mercado Pago no reenvíe el aviso indefinidamente.
        return ("Sin credenciales de Mercado Pago configuradas.", 200)

    try:
        remote = mp.get_payment(mp_id)
    except mp.MercadoPagoError as exc:
        current_app.logger.warning("Webhook de Mercado Pago: %s", exc)
        # 5xx: Mercado Pago reintentará la notificación más tarde.
        return (str(exc), 500)

    reference = remote.get("external_reference", "")
    payment = db.session.scalar(db.select(Payment).where(Payment.mp_id == mp_id))
    if payment is None and reference:
        payment = db.session.scalar(
            db.select(Payment).where(Payment.reference == reference)
        )
    if payment is None:
        return (f"Cobro con id {mp_id} no encontrado.", 200)

    payment.mp_id = mp_id
    _apply_remote(payment, remote)
    db.session.commit()
    return ("Sincronizado.", 200)


@bp.route("/<int:payment_id>/actualizar", methods=["POST"])
@login_required
def refresh(payment_id):
    """Sincroniza un cobro con la API (sincronización manual).

    Es necesaria en desarrollo, donde Mercado Pago no puede alcanzar
    ``back_urls`` ni ``notification_url`` locales (exige https).
    """
    payment = db.get_or_404(Payment, payment_id)
    if not owner_or_admin(payment.order):
        abort(403)

    if payment.method != "mercadopago":
        flash("Este cobro no viene de Mercado Pago: no hay nada que consultar.", "info")
    elif not mp.is_configured():
        flash("Faltan las credenciales de Mercado Pago (MP_ACCESS_TOKEN).", "warning")
    else:
        try:
            remote = _sync_payment(payment)
        except mp.MercadoPagoError as exc:
            flash(f"No se pudo consultar el cobro: {exc}", "error")
        else:
            db.session.commit()
            if remote is None:
                flash("Mercado Pago todavía no registró este pago.", "info")
            else:
                _announce(payment)
            return redirect(url_for("orders.detail", order_id=payment.order_id))

    return redirect(url_for("orders.detail", order_id=payment.order_id))


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
