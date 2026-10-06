"""Paquete de rutas: agrupa los blueprints y utilidades compartidas."""

from functools import wraps

from flask import abort
from flask_login import current_user


def admin_required(func):
    """Decorador que restringe una vista a usuarios administradores.

    Si el usuario no está autenticado o no es admin, responde con 403.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not (current_user.is_authenticated and current_user.is_admin):
            abort(403)
        return func(*args, **kwargs)

    return wrapper


def owner_or_admin(obj, user_attr="user_id"):
    """Comprueba que ``obj`` pertenezca al usuario activo o a un admin.

    Args:
        obj: modelo con el atributo ``user_attr`` (id del propietario).
        user_attr: nombre del atributo que contiene el id del dueño.

    Returns:
        ``True`` si el usuario tiene acceso al objeto.
    """
    if current_user.is_admin:
        return True
    return getattr(obj, user_attr, None) == current_user.id
