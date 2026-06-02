from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import pandas as pd

cupones_bp = Blueprint("cupones", __name__, url_prefix="/cupones")


@cupones_bp.route("/", methods=["GET", "POST"])
def index():
    if session.get("usuario_rol") != "publicidad":
        return redirect(url_for("sistemas.login"))

    cupones = []
    total_filas = 0
    total_cupones = 0

    if request.method == "POST":
        archivo = request.files.get("archivo")

        if not archivo or archivo.filename == "":
            flash("Debe seleccionar un archivo Excel")
            return redirect(url_for("cupones.index"))

        df = pd.read_excel(archivo)
        total_filas = len(df)

        for _, fila in df.iterrows():
            estado = str(fila.get("Estado", "")).strip()

            if estado in ["Facturado", "Entregado"]:
                cupones.append({
                    "nombre": fila.get("Cliente", ""),
                    "dni": fila.get("Documento cliente", ""),
                    "telefono": fila.get("Teléfono", ""),
                    "sucursal": fila.get("Tienda", ""),
                    "estado": estado
                })

        total_cupones = len(cupones)

    return render_template(
        "publicidad/cupones.html",
        cupones=cupones,
        total_filas=total_filas,
        total_cupones=total_cupones
    )