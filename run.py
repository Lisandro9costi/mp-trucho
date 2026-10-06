"""Punto de entrada de la aplicación.

Permite ejecutar la app con ``python run.py`` o con ``flask run``
(definiendo FLASK_APP=run.py o usando ``flask --app run run``).
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
