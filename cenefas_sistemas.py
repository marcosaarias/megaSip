import uuid
from datetime import datetime
from io import BytesIO
from utils.sucursales import SUCURSAL_MAP

import pandas as pd
from flask import Blueprint, render_template, request, session, send_file

from sistemas import login_requerido
from compras import procesar_archivo_cenefas, guardar_temporal, recuperar_temporal


cenefas_sistemas_bp = Blueprint(
    "cenefas_sistemas",
    __name__,
    url_prefix="/sistemas/cenefas"
)


@cenefas_sistemas_bp.route("/", methods=["GET", "POST"])
@login_requerido("sistemas")
def index():
    preview = None
    mensaje_error = None
    total_registros = 0

    fecha_desde = request.form.get("fecha_desde") or ""
    fecha_hasta = request.form.get("fecha_hasta") or ""
    tipo = request.form.get("tipo", "mayorista")
    grupo_sucursales = request.form.get("grupo_sucursales") or ""

    if request.method == "POST":
        archivo = request.files.get("archivo")

        try:
            df, preview, mensaje_error, total_registros = procesar_archivo_cenefas(
                archivo=archivo,
                tipo=tipo,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta
            )

            if df is not None:
                lote_id = str(uuid.uuid4())
                guardar_temporal(lote_id, df)

                session["cenefas_sistemas_lote_id"] = lote_id
                session["cenefas_sistemas_tipo"] = tipo
                session["cenefas_sistemas_fecha_desde"] = fecha_desde
                session["cenefas_sistemas_fecha_hasta"] = fecha_hasta

        except Exception as e:
            mensaje_error = f"Error de backend: {e}"

    return render_template(
        "cenefas_sistemas.html",
        preview=preview,
        tipo=tipo,
        mensaje_error=mensaje_error,
        total_registros=total_registros,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        grupo_sucursales=grupo_sucursales,   # 👈 importante
        sucursal_map=SUCURSAL_MAP
    )


@cenefas_sistemas_bp.route("/descargar", methods=["POST"])
@login_requerido("sistemas")
def descargar():
    lote_id = session.get("cenefas_sistemas_lote_id")
    df = recuperar_temporal(lote_id)

    if not lote_id or df is None:
        return "No hay archivo generado para descargar.", 400

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Cenefas")

    output.seek(0)

    nombre_archivo = f"cenefas_sistemas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    return send_file(
        output,
        as_attachment=True,
        download_name=nombre_archivo,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )