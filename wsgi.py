"""Titik masuk WSGI (gunicorn / PythonAnywhere): `from wsgi import application`."""
from app import create_app

application = create_app()
app = application
