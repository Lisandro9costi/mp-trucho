# Simulador Cobroventa

Simulador de venta y cobro en Flask: catálogo de productos, pedidos con
control de stock y cobros que pueden resolverse localmente (simulador) o
mediante **Checkout Pro de Mercado Pago** (redirección), cuando hay
credenciales configuradas.

## Tecnologías

| Pieza | Versión | Uso |
|---|---|---|
| Flask | 3.1.3 | Framework web |
| Flask-SQLAlchemy | 3.1.1 | ORM y conexión a SQLite |
| Flask-Login | 0.6.3 | Sesiones y control de roles |
| Flask-WTF | 1.3.0 | Formularios y protección CSRF |
| WTForms | 3.2.2 | Validación de formularios |
| Bootstrap | 5.3.3 | Interfaz (CDN con SRI) |
| python-dotenv | 1.2.4 | Carga de variables desde `.env` |

## Variables de entorno

Las credenciales y el resto de la configuración local viven en un archivo
`.env` en la raíz (ignorado por git). Copiá la plantilla y completá los
valores:

```bat
copy .env.example .env
```

La app carga ese archivo con `python-dotenv` al arrancar. Las variables
de Mercado Pago se detallan más abajo; `SECRET_KEY` es opcional en
desarrollo.

## Estructura del proyecto

```
simulador cobroventa/
├── config.py             # Configuración (SECRET_KEY, BD, Mercado Pago)
├── run.py                # Punto de entrada: python run.py
├── seed.py               # Datos de prueba (idempotente)
├── .env.example          # Plantilla de variables de entorno (credenciales)
├── smoke_test.py         # Pruebas con el cliente de Flask
├── smoke_http.py         # Pruebas contra el servidor real por HTTP
├── requirements.txt
├── instance/
│   └── app.db            # SQLite (se crea sola, no se versiona)
└── app/
    ├── __init__.py       # create_app() + extensiones + ensure_columns()
    ├── models.py         # User, Product, Order, OrderItem, Payment
    ├── forms.py          # Formularios WTForms
    ├── services/
    │   └── mercado_pago.py  # Cliente de Checkout Pro (Preferences API)
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
copy .env.example .env
nashe\Scripts\python.exe seed.py
nashe\Scripts\python.exe run.py
```

Abre <http://127.0.0.1:5000>.

## Instalación (Linux / macOS)

```bash
python3 -m venv nashe
./nashe/bin/pip install -r requirements.txt
cp .env.example .env
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
| `/pagos/pedido/<id>` | GET, POST | dueño o admin | Registrar cobro o ir a Mercado Pago |
| `/pagos/retorno` | GET | dueño o admin | Vuelta del checkout de Mercado Pago |
| `/pagos/webhook` | GET, POST | público (exento de CSRF) | Notificaciones de Mercado Pago |
| `/pagos/<id>/actualizar` | POST | dueño o admin | Sincronizar un cobro con la API |
| `/pagos/` | GET | login | Listado de cobros |

## Mercado Pago (Checkout Pro)

Con `MP_ACCESS_TOKEN` configurado, el botón **"Pagar con Mercado Pago"**
de la pantalla de cobro crea una preferencia
(`POST /checkout/preferences`), guarda un cobro en estado `pendiente` y
redirige al comprador al checkout de Mercado Pago. Al volver (o cuando
llega el webhook) la app consulta `GET /v1/payments/{id}` y aplica el
estado real. Sin credenciales, todo sigue resolviéndose con el simulador
local.

| Variable de entorno | Uso | Por defecto |
|---|---|---|
| `MP_ACCESS_TOKEN` | Clave privada; sin ella manda el simulador local | vacío |
| `MP_API_URL` | Raíz de la API (se puede apuntar a un mock) | `https://api.mercadopago.com` |
| `MP_TIMEOUT` | Segundos de espera por llamada | `10` |
| `MP_BASE_URL` | Raíz pública del sitio para las `back_urls` | `http://127.0.0.1:5000` |
| `MP_NOTIFICATION_URL` | URL pública del webhook | vacío |
| `MP_CURRENCY` | Moneda de la preferencia (MP no acepta EUR) | `ARS` |

El checkout está limitado a un único medio de pago: **transferencia
bancaria**. La preferencia excluye tarjetas y efectivo
(`payment_methods.excluded_payment_types`); el saldo en cuenta
(`account_money`) no se puede excluir porque Mercado Pago lo muestra
siempre.

El Access Token **nunca** se envía al navegador: solo vive en el servidor.
Las credenciales de prueba están en *Tus integraciones > Datos de
integración > Pruebas > Credenciales*. Cargalas en el archivo `.env` de
la raíz (no en el repositorio):

```env
MP_ACCESS_TOKEN=APP_USR-0000000000000000-000000-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx-000000000
```

Comportamiento:

- Con el botón de Mercado Pago, el cobro nace `pendiente` con
  `reference` como `external_reference`. Al aprobarse se guardan `mp_id`,
  `mp_method` y `status_detail` y el pedido pasa a `pagado`.
- `/pagos/webhook` acepta el formato v2 y el IPN, está exento de CSRF y
  de login, y siempre responde 2xx salvo fallo de la API (500 para que
  Mercado Pago reintente).
- `/pagos/<id>/actualizar` (botón **Sincronizar**) consulta la API a
  mano; es la vía práctica en desarrollo, donde Mercado Pago no puede
  alcanzar `back_urls` ni `notification_url` locales porque exige https.
- Si un cobro aprobado pasa a rechazado y queda saldo, el pedido vuelve
  a `pendiente`.

## Reglas de negocio del simulador

- El pedido descuenta stock y **congela el precio** en la línea de detalle.
- Cancelar un pedido devuelve el stock al catálogo.
- Solo se cobra hasta el saldo pendiente; un cobro que lo salda deja el
  pedido en `pagado`.
- Un pedido `pagado` puede pasar a `enviado` (acción de admin).
- Resultado del cobro local (sin credenciales de Mercado Pago):
  - efectivo y transferencia: siempre aprobados;
  - tarjeta: se rechaza cuando el importe termina en `0` (para poder probar
    el camino de error sin depender de una pasarela real).
- Estados de pedido: `pendiente`, `pagado`, `enviado`, `cancelado`.
- Estados de cobro: `pendiente`, `aprobado`, `rechazado` (traducidos de
  `approved`, `rejected` y `pending` cuando responde la API).

## Pruebas

```bat
nashe\Scripts\python.exe smoke_test.py
nashe\Scripts\python.exe smoke_http.py
```

- `smoke_test.py` recorre las comprobaciones del flujo con el cliente de
  pruebas de Flask: validaciones, stock, totales, roles, CSRF y la
  integración con Checkout Pro (con la capa HTTP parcheada, sin red).
- `smoke_http.py` arranca el servidor real y repite el flujo por HTTP
  manteniendo cookies, como haría un navegador, más el webhook.

Ambos usan una base de datos temporal, así que no tocan `instance/app.db`
ni necesitan `seed.py`.

## Notas de seguridad

- `SECRET_KEY` tiene un valor por defecto pensado para desarrollo. En
  producción define `SECRET_KEY` en el `.env`.
- `MP_ACCESS_TOKEN` solo se lee en el servidor y viaja en la cabecera
  `Authorization`; nunca se imprime ni se expone en las plantillas.
- Los formularios llevan token CSRF; los POST que lo envían se rechazan
  con 400 (la única excepción es `/pagos/webhook`, que Mercado Pago debe
  poder llamar sin token).
- El acceso a un pedido se comprueba con `owner_or_admin`: un cliente que
  pide el id de otro recibe 403.
- Para desplegar, `run.py` usa el servidor de desarrollo de Flask, que no
  es apto para producción: usa waitress, gunicorn o similar.
