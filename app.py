import os
from flask import Flask, url_for, redirect

from archivo_maestro import archivo_maestro_bp
from sistemas import sistemas_bp
from usuarios import usuarios_bp
from farmacia import farmacia_bp
from farmacia_folder import farmacia_folder_bp
from laboratorios import laboratorios_bp
from rubros import rubros_bp
from subrubros import subrubros_bp
from compras import compras_bp
from vencimientos import vencimientos_bp
from promociones import promociones_bp
from logs import logs_bp
from pedidoya import pedidoya_bp
from diarios import diarios_bp
from saltarefrescos import saltarefrescos_bp
from ecommerce_cenefas import ecommerce_cenefas_bp
from cenefas_sistemas import cenefas_sistemas_bp
from operadores import operadores_bp
from cupones import cupones_bp
from informes_ecommerce import informes_ecommerce_bp
from modulos_farmacia.farmacia_diarios import farmacia_diarios_bp
from modulos_farmacia.farmacia_nutricia import farmacia_nutricia_bp
from farmacia_logs import farmacia_logs_bp

app = Flask(__name__)
app.secret_key = "clave_secreta_demo"

app.register_blueprint(farmacia_logs_bp)
app.register_blueprint(farmacia_diarios_bp)
app.register_blueprint(farmacia_nutricia_bp)
app.register_blueprint(informes_ecommerce_bp)
app.register_blueprint(cupones_bp)
app.register_blueprint(archivo_maestro_bp, url_prefix="/archivo_maestro")
app.register_blueprint(cenefas_sistemas_bp)
app.register_blueprint(ecommerce_cenefas_bp)
app.register_blueprint(diarios_bp)
app.register_blueprint(saltarefrescos_bp)
app.register_blueprint(sistemas_bp, url_prefix='/sistemas')
app.register_blueprint(usuarios_bp, url_prefix='/usuarios')
app.register_blueprint(farmacia_bp, url_prefix='/farmacia')
app.register_blueprint(farmacia_folder_bp, url_prefix='/farmacia_folder')
app.register_blueprint(laboratorios_bp, url_prefix='/laboratorios')
app.register_blueprint(rubros_bp, url_prefix='/rubros')
app.register_blueprint(subrubros_bp, url_prefix='/subrubros')
app.register_blueprint(pedidoya_bp, url_prefix="/pedidoya")
app.register_blueprint(compras_bp, url_prefix='/compras')
app.register_blueprint(vencimientos_bp)
app.register_blueprint(logs_bp)
app.register_blueprint(promociones_bp)
app.register_blueprint(operadores_bp)

@app.route("/")
def home():
    return redirect(url_for("sistemas.login"))

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5008
    )