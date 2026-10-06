# Simulador Cobroventa

Simulador de venta y cobro en Flask: catálogo de productos, pedidos con
control de stock y cobros simulados (tarjeta, efectivo y transferencia)
sin pasar por una pasarela real.

## Tecnologías

| Pieza | Versión | Uso |
|---|---|---|
| Flask | 3.1.3 | Framework web |
| Flask-SQLAlchemy | 3.1.1 | ORM y conexión a SQLite |
| Flask-Login | 0.6.3 | Sesiones y control de roles |
| Flask-WTF | 1.3.0 | Formularios y protección CSRF |
| WTForms | 3.2.2 | Validación de formularios |
| Bootstrap | 5.3.3 | Interfaz (CDN con SRI) |

## Estructura del proyecto

```
simulador cobroventa/
├── config.py             # Configuración (SECRET_KEY, ruta de la BD)
├── run.py                # Punto de entrada: python run.py
├── seed.py               # Datos de prueba (idempotente)
├── smoke_test.py         # Pruebas con el cliente de Flask
├── smoke_http.py         # Pruebas contra el servidor real por HTTP
├── requirements.txt
├── instance/
│   └── app.db            # SQLite (se crea sola, no se versiona)
└── app/
    ├── __init__.py       # create_app() + extensiones
    ├── models.py         # User, Product, Order, OrderItem, Payment
    ├── forms.py          # Formularios WTForms
    ├── routes/
    │   ├── __init__.py   # admin_required, owner_or_admin
    │   ├── auth.py       # /auth/register, /auth/login, /auth/logout
    │   ├── main.py       # /, /panel
    │   ├── products.py   # /productos/...
    │   ├── orders.py     # /pedidos/...
    │   └── payments.py   # /pagos/...
    ├── templates/
    │   ├── base.html, _macros.html
    │   ├── auth/, errors/, main/, products/, orders/, payments/
    └── static/css/style.css
```

## Instalación (Windows)

```bat
nashe\Scripts\python.exe -m pip install -r requirements.txt
nashe\Scripts\python.exe seed.py
nashe\Scripts\python.exe run.py
```

Abre <http://127.0.0.1:5000>.

## Instalación (Linux / macOS)

```bash
python3 -m venv nashe
./nashe/bin/pip install -r requirements.txt
./nashe/bin/python seed.py
./nashe/bin/python run.py
```

## Usuarios de prueba

| Correo | Contraseña | Rol |
|---|---|---|
| admin@simuladorapp.com | admin123 | Administrador |
| cliente@simuladorapp.com | cliente123 | Cliente |
| ana@simuladorapp.com | cliente123 | Cliente |

`seed.py` es idempotente: se puede volver a ejecutar sin duplicar nada.

## Rutas

| Ruta | Método | Acceso | Vista |
|---|---|---|---|
| `/` | GET | público | Portada |
| `/panel` | GET | login | Métricas y últimos pedidos |
| `/auth/register` | GET, POST | público | Crear cuenta |
| `/auth/login` | GET, POST | público | Entrar |
| `/auth/logout` | GET | login | Salir |
| `/productos/` | GET | público | Catálogo con búsqueda |
| `/productos/nuevo` | GET, POST | admin | Alta de producto |
| `/productos/<id>/editar` | GET, POST | admin | Editar producto |
| `/productos/<id>/baja` | POST | admin | Baja lógica |
| `/pedidos/` | GET | login | Listado (propio o todo) |
| `/pedidos/nuevo` | GET, POST | login | Crear pedido |
| `/pedidos/<id>` | GET | dueño o admin | Detalle |
| `/pedidos/<id>/enviar` | POST | admin | Marcar enviado |
| `/pedidos/<id>/cancelar` | POST | dueño o admin | Cancelar y devolver stock |
| `/pagos/pedido/<id>` | GET, POST | dueño o admin | Registrar cobro |
| `/pagos/` | GET | login | Listado de cobros |

## Reglas de negocio del simulador

- El pedido descuenta stock y **congela el precio** en la línea de detalle.
- Cancelar un pedido devuelve el stock al catálogo.
- Solo se cobra hasta el saldo pendiente; un cobro que lo salda deja el
  pedido en `pagado`.
- Un pedido `pagado` puede pasar a `enviado` (acción de admin).
- Resultado del cobro simulado:
  - efectivo y transferencia: siempre aprobados;
  - tarjeta: se rechaza cuando el importe termina en `0` (para poder probar
    el camino de error sin depender de una pasarela real).
- Estados de pedido: `pendiente`, `pagado`, `enviado`, `cancelado`.

## Pruebas

```bat
nashe\Scripts\python.exe smoke_test.py
nashe\Scripts\python.exe smoke_http.py
```

- `smoke_test.py` recorre 40 comprobaciones con el cliente de pruebas de
  Flask: validaciones, stock, totales, roles y CSRF.
- `smoke_http.py` arranca el servidor real y repite el flujo por HTTP
  manteniendo cookies, como haría un navegador.

Ambos usan una base de datos temporal, así que no tocan `instance/app.db`
ni necesitan `seed.py`.

## Notas de seguridad

- `SECRET_KEY` tiene un valor por defecto pensado para desarrollo. En
  producción define la variable de entorno `SECRET_KEY`.
- Los formularios llevan token CSRF; los POST que lo envyían se rechazan
  con 400.
- El acceso a un pedido se comprueba con `owner_or_admin`: un cliente que
  pide el id de otro recibe 403.
- Para desplegar, `run.py` usa el servidor de desarrollo de Flask, que no
  es apto para producción: usa waitress, gunicorn o similar.
