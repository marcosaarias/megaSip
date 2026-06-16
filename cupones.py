from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import pandas as pd
from database.db import get_db_connection

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


@cupones_bp.route("/transmitir_sucursales", methods=["POST"])
def transmitir_sucursales():
    return "Cupones transmitidos a sucursales correctamente"


@cupones_bp.route("/sucursales_sorteo")
def sucursales_sorteo():
    return render_template("publicidad/sucursales_sorteo.html")


#@cupones_bp.route("/sucursal")
#def cupones_sucursal():
#    if session.get("usuario_rol") != "sucursal":
#        return redirect(url_for("sistemas.login"))

#    sucursal = session.get("usuario_nombre", "").strip().upper()

#    conn = get_db_connection()
#    cur = conn.cursor()

#    try:
#        cur.execute("""
#            SELECT nombre, dni, telefono, sucursal, estado
#            FROM cupones
#            WHERE UPPER(TRIM(sucursal)) = %s
#            ORDER BY id DESC
#        """, (sucursal,))

#        cupones = cur.fetchall()

#    finally:
#        cur.close()
#        conn.close()

#    return render_template(
#        "sucursales_cupones.html",
#        cupones=cupones,
#        sucursal=sucursal,
#        desde="-",
#        hasta="-"
#    )