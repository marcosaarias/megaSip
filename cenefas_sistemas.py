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
    grupo_sucursales = request.form.get("grupo_sucursales") or ""

    if request.method == "POST":
        archivo = request.files.get("archivo")
        lote_id = session.get("cenefas_sistemas_lote_id")

        try:
            df = None

            print("==== DEBUG CENEFAS SISTEMAS ====")
            print("Grupo seleccionado:", grupo_sucursales)
            print("Codigos del grupo:", SUCURSAL_MAP.get(grupo_sucursales, "NO ENCONTRADO"))
            print("Lote actual:", lote_id)

            if archivo and archivo.filename:
                print("Archivo recibido:", archivo.filename)

                df, preview, mensaje_error, total_registros = procesar_archivo_cenefas(
                    archivo=archivo,
                    tipo="mayorista",
                    fecha_desde=fecha_desde,
                    fecha_hasta=fecha_hasta
                )

                print("DF despues de procesar_archivo_cenefas:")
                print("Columnas:", df.columns.tolist() if df is not None else None)

                if df is not None:
                    print("Primeras filas ANTES de aplicar grupo:")
                    print(df.head().to_string())

                    lote_id = str(uuid.uuid4())
                    session["cenefas_sistemas_lote_id"] = lote_id

            else:
                print("No vino archivo. Recuperando temporal...")
                df = recuperar_temporal(lote_id)

                print("DF recuperado:")
                print("Columnas:", df.columns.tolist() if df is not None else None)

                if df is not None:
                    print("Primeras filas recuperadas:")
                    print(df.head().to_string())

            if df is not None and grupo_sucursales:
                codigos = SUCURSAL_MAP.get(grupo_sucursales, "")

                print("Aplicando grupo:", grupo_sucursales)
                print("Codigos a aplicar:", codigos)

                if codigos:
                    df["sucursales"] = codigos

                    print("Primeras filas DESPUES de aplicar grupo:")
                    print(df.head().to_string())

            if df is not None:
                preview = df.to_html(
                    classes="table table-striped table-bordered",
                    index=False
                )
                total_registros = len(df)

                guardar_temporal(lote_id, df)

                session["cenefas_sistemas_fecha_desde"] = fecha_desde
                session["cenefas_sistemas_fecha_hasta"] = fecha_hasta

        except Exception as e:
            print("ERROR DEBUG:", e)
            mensaje_error = f"Error de backend: {e}"

    return render_template(
        "cenefas_sistemas.html",
        preview=preview,
        mensaje_error=mensaje_error,
        total_registros=total_registros,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        grupo_sucursales=grupo_sucursales,
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