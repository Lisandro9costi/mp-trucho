"""Formularios de la aplicación (Flask-WTF).

Todos los formularios declaran explícitamente ``submit`` para que los
botones de las plantillas funcionen con CSRF habilitado.
"""

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DecimalField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, EqualTo, Length, NumberRange


class LoginForm(FlaskForm):
    """Formulario de inicio de sesión."""

    email = StringField(
        "Correo", validators=[DataRequired(), Email(), Length(max=180)]
    )
    password = PasswordField(
        "Contraseña", validators=[DataRequired(), Length(min=4, max=128)]
    )
    remember = BooleanField("Recordarme")
    submit = SubmitField("Entrar")


class RegisterForm(FlaskForm):
    """Formulario de registro de un nuevo cliente."""

    name = StringField("Nombre", validators=[DataRequired(), Length(max=120)])
    email = StringField(
        "Correo", validators=[DataRequired(), Email(), Length(max=180)]
    )
    password = PasswordField(
        "Contraseña",
        validators=[DataRequired(), Length(min=6, max=128)],
    )
    password2 = PasswordField(
        "Repetir contraseña",
        validators=[DataRequired(), EqualTo("password", message="No coinciden.")],
    )
    submit = SubmitField("Crear cuenta")


class ProductForm(FlaskForm):
    """Formulario de alta y edición de productos."""

    sku = StringField("SKU", validators=[DataRequired(), Length(max=40)])
    name = StringField("Nombre", validators=[DataRequired(), Length(max=160)])
    description = TextAreaField("Descripción", validators=[Length(max=2000)])
    price = DecimalField(
        "Precio",
        validators=[DataRequired(), NumberRange(min=0)],
        places=2,
    )
    stock = DecimalField(
        "Stock", validators=[DataRequired(), NumberRange(min=0)], places=0
    )
    active = BooleanField("Activo", default=True)
    submit = SubmitField("Guardar")


class OrderForm(FlaskForm):
    """Formulario para crear un pedido con sus líneas de producto."""

    product_id = SelectField("Producto", validators=[DataRequired()], coerce=int)
    quantity = DecimalField(
        "Cantidad",
        validators=[DataRequired(), NumberRange(min=1)],
        places=0,
    )
    notes = TextAreaField("Notas", validators=[Length(max=2000)])
    submit = SubmitField("Crear pedido")


class PaymentForm(FlaskForm):
    """Formulario de cobro de un pedido."""

    amount = DecimalField(
        "Importe",
        validators=[DataRequired(), NumberRange(min=0.01)],
        places=2,
    )
    method = SelectField("Método", choices=[], validators=[DataRequired()])
    submit = SubmitField("Cobrar")
