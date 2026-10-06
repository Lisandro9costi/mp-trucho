# AGENTS.md — Simulador Cobroventa

Punto de entrada: **`run.py`**. La app se construye con el patrón
*application factory* en `app/__init__.py` (`create_app()`).

## Comandos

```bat
nashe\Scripts\python.exe run.py          # servidor en 127.0.0.1:5000
nashe\Scripts\python.exe seed.py         # datos de prueba (idempotente)
nashe\Scripts\python.exe smoke_test.py   # pruebas con cliente de Flask
nashe\Scripts\python.exe smoke_http.py   # pruebas por HTTP real
```

No hay linter ni formateador configurado. Antes de dar por terminada una
tarea, ejecuta `smoke_test.py` y `smoke_http.py`.

## Rutas por blueprint

| Blueprint | Prefijo | Archivo |
|---|---|---|
| `main` | `/` | `app/routes/main.py` |
| `auth` | `/auth` | `app/routes/auth.py` |
| `products` | `/productos` | `app/routes/products.py` |
| `orders` | `/pedidos` | `app/routes/orders.py` |
| `payments` | `/pagos` | `app/routes/payments.py` |

Si añades un blueprint: créalo en `app/routes/`, regístralo dentro de
`create_app()` y crea `app/templates/<nombre>/` con sus plantillas.

## Convenciones

- Identificadores en inglés, docstrings y comentarios en español.
- Docstring en **cada** módulo, clase y función (Google-style para
  `create_app`, con `Args:`/`Returns:`).
- 4 espacios, comillas dobles, ~88 columnas, coma final en llamadas
  multilínea.
- Imports de la app siempre absolutos: `from app import db`,
  `from app.models import Order`.
- Imports de rutas **dentro** de la función (evitan ciclos con
  `app/__init__.py`).
- Decoradores en este orden: `@bp.route` → `@login_required` →
  `@admin_required`.
- Consultas con la API 2.0 de SQLAlchemy: `db.session.scalar(db.select(X)...)`,
  `db.get_or_404(X, id)`. Nada de `X.query`.
- Estados y métodos como cadenas en minúsculas y en español; tuplas de
  valores válidos como atributo de clase (`Order.STATUSES`).
- Flash: categorías `success`, `error`, `info`, `warning`. La plantilla
  base convierte `error` en `danger` de Bootstrap.
- Plantillas: una subcarpeta por blueprint, extienden `base.html`, usan
  los macros de `_macros.html` y `url_for('static', filename='css/style.css')`.
- Importaciones deliberadamente sin usar se marcan con `# noqa: F401`.
- `#` explica **por qué**, no qué hace el código.

## Detalles técnicos que conviene no romper

- `app/models.py`: `User` implementa `is_active`, `is_anonymous`,
  `is_authenticated` y `get_id()` porque Flask-Login los exige.
  La contraseña solo se escribe (`@password.setter`) y se compara con
  `check_password()`.
- Importes monetarios con `Numeric(10, 2)` y `Decimal`; `float` solo para
  sumar en las plantillas de resumen.
- `OrderItem.unit_price` congela el precio del producto en el momento del
  pedido, así que editar el catálogo no altera pedidos ya emitidos.
- `Order.recalculate_total()` debe llamarse tras tocar `order.items`.
- Cancelar un pedido recorre sus líneas y devuelve el stock.
- En `payments.pay` el importe se propone solo si el formulario no viene
  enviado (`if not form.is_submitted()`); si no, se sobrescribe lo que
  escribió el usuario.
- La regla de rechazo con tarjeta vive en `payments._simulate()`.

## Pruebas

`smoke_test.py` y `smoke_http.py` usan clases de configuración propias
(`SmokeConfig`, `HttpSmokeConfig`) que apuntan a un SQLite temporal, de
modo que no dependen de `seed.py` ni modifican `instance/app.db`. Si
añades una ruta o regla de negocio, añade también su comprobación.
