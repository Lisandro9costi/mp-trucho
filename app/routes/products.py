"""Rutas de catálogo: listado, alta, edición y baja de productos."""

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import login_required
from sqlalchemy import or_

from app import db
from app.forms import ProductForm
from app.models import Product
from app.routes import admin_required

bp = Blueprint("products", __name__, url_prefix="/productos")


@bp.route("/")
def list_products():
    """Muestra el catálogo con un filtro opcional por nombre o SKU."""
    from flask import request

    q = request.args.get("q", "").strip()

    # Sin filtro se listan solo los productos activos.
    query = db.select(Product)
    if q:
        pattern = f"%{q}%"
        query = query.where(or_(Product.name.ilike(pattern), Product.sku.ilike(pattern)))
    else:
        query = query.where(Product.active.is_(True))

    products = db.session.scalars(query.order_by(Product.name)).unique().all()
    return render_template("products/list.html", products=products, q=q)


@bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@admin_required
def create():
    """Da de alta un producto nuevo."""
    form = ProductForm()
    if form.validate_on_submit():
        sku = form.sku.data.strip().upper()
        if db.session.scalar(db.select(Product).where(Product.sku == sku)):
            flash(f"El SKU {sku} ya existe.", "error")
        else:
            product = Product(
                sku=sku,
                name=form.name.data,
                description=form.description.data or "",
                price=form.price.data,
                stock=int(form.stock.data),
                active=form.active.data,
            )
            db.session.add(product)
            db.session.commit()
            flash("Producto creado.", "success")
            return redirect(url_for("products.list_products"))
    return render_template("products/form.html", form=form, product=None)


@bp.route("/<int:product_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def edit(product_id):
    """Edita los datos de un producto existente."""
    product = db.get_or_404(Product, product_id)
    form = ProductForm(obj=product)

    if form.validate_on_submit():
        sku = form.sku.data.strip().upper()
        duplicate = db.session.scalar(
            db.select(Product).where(Product.sku == sku, Product.id != product.id)
        )
        if duplicate:
            flash(f"El SKU {sku} ya está en uso por otro producto.", "error")
        else:
            product.sku = sku
            product.name = form.name.data
            product.description = form.description.data or ""
            product.price = form.price.data
            product.stock = int(form.stock.data)
            product.active = form.active.data
            db.session.commit()
            flash("Producto actualizado.", "success")
            return redirect(url_for("products.list_products"))

    return render_template("products/form.html", form=form, product=product)


@bp.route("/<int:product_id>/baja", methods=["POST"])
@login_required
@admin_required
def deactivate(product_id):
    """Da de baja un producto (baja lógica: se conserva el historial)."""
    product = db.get_or_404(Product, product_id)
    product.active = False
    db.session.commit()
    flash(f"{product.name} quedó dado de baja.", "info")
    return redirect(url_for("products.list_products"))
