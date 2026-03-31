import os
from flask import Flask, url_for, redirect

from sistemas import sistemas_bp
from usuarios import usuarios_bp
from farmacia import farmacia_bp
from compras import compras_bp
from vencimientos import vencimientos_bp
from logs import logs_bp

app = Flask(__name__)
app.secret_key = "clave_secreta_demo"

# Registrar blueprints
app.register_blueprint(sistemas_bp, url_prefix='/sistemas')
app.register_blueprint(usuarios_bp, url_prefix='/usuarios')
app.register_blueprint(farmacia_bp, url_prefix='/farmacia')
app.register_blueprint(compras_bp, url_prefix='/compras')
app.register_blueprint(vencimientos_bp)
app.register_blueprint(logs_bp)


@app.route("/")
def home():
    return redirect(url_for("sistemas.login"))

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5008
    )