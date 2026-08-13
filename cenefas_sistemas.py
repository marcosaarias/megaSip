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

def preparar_df_sistemas(df):
    columnas_ocultar = ["dep", "departamento", "Dep", "Departamento"]
    return df.drop(columns=[c for c in columnas_ocultar if c in df.columns])

@cenefas_sistemas_bp.route("/", methods=["GET", "POST"])
@login_requerido("sistemas")
def index():

    preview = None
    mensaje_error = None
    total_registros = 0

    fecha_desde = (
        request.form.get("fecha_desde")
        or ""
    ).strip()

    fecha_hasta = (
        request.form.get("fecha_hasta")
        or ""
    ).strip()

    grupo_sucursales = (
        request.form.get("grupo_sucursales")
        or ""
    ).strip()

    codigos_sucursales = (
        request.form.get("codigos_sucursales")
        or ""
    ).strip().upper()

    if request.method == "POST":

        archivo = request.files.get(
            "archivo"
        )

        lote_id = session.get(
            "cenefas_sistemas_lote_id"
        )

        try:

            df = None

            print(
                "==== DEBUG CENEFAS SISTEMAS ===="
            )

            print(
                "Grupo seleccionado:",
                repr(grupo_sucursales)
            )

            print(
                "Códigos enviados:",
                repr(codigos_sucursales)
            )

            # ==================================================
            # ARCHIVO NUEVO
            # ==================================================

            if archivo and archivo.filename:

                print(
                    "Archivo recibido:",
                    archivo.filename
                )

                (
                    df,
                    _,
                    mensaje_error,
                    total_registros,
                ) = procesar_archivo_cenefas(
                    archivo=archivo,
                    tipo="mayorista",
                    fecha_desde=fecha_desde,
                    fecha_hasta=fecha_hasta,
                )

                if df is None:
                    raise ValueError(
                        mensaje_error
                        or (
                            "No se pudo procesar "
                            "el archivo."
                        )
                    )

                print(
                    "Sucursales ANTES "
                    "de aplicar selección:"
                )

                if "sucursales" in df.columns:
                    print(
                        df["sucursales"]
                        .head()
                        .tolist()
                    )

                # Siempre generar un lote nuevo
                lote_id = str(
                    uuid.uuid4()
                )

                session[
                    "cenefas_sistemas_lote_id"
                ] = lote_id

            # ==================================================
            # RECUPERAR TEMPORAL
            # ==================================================

            else:

                print(
                    "No vino archivo. "
                    "Recuperando temporal..."
                )

                if not lote_id:
                    raise ValueError(
                        "No existe un archivo "
                        "temporal para procesar."
                    )

                df = recuperar_temporal(
                    lote_id
                )

                if df is None:
                    raise ValueError(
                        "El archivo temporal "
                        "no existe o venció."
                    )

            # ==================================================
            # APLICAR SUCURSALES
            #
            # IMPORTANTE:
            # ESTE BLOQUE ESTÁ FUERA DEL IF/ELSE ANTERIOR
            # ==================================================

            if (
                df is not None
                and grupo_sucursales
            ):

                # ----------------------------------------------
                # SELECCIÓN PERSONALIZADA
                # ----------------------------------------------

                if (
                    grupo_sucursales
                    == "__personalizada__"
                ):

                    if not codigos_sucursales:
                        raise ValueError(
                            "Debe seleccionar "
                            "al menos una sucursal."
                        )

                    codigos = (
                        codigos_sucursales
                    )

                # ----------------------------------------------
                # GRUPO PREDEFINIDO
                # ----------------------------------------------

                else:

                    codigos = SUCURSAL_MAP.get(
                        grupo_sucursales,
                        "",
                    )

                    if not codigos:
                        raise ValueError(
                            "El grupo de sucursales "
                            "seleccionado no es válido."
                        )

                print(
                    "Aplicando grupo:",
                    grupo_sucursales
                )

                print(
                    "Códigos finales:",
                    codigos
                )

                # ESTE ES EL REEMPLAZO
                df["sucursales"] = codigos

                print(
                    "Sucursales DESPUÉS "
                    "de aplicar selección:"
                )

                print(
                    df["sucursales"]
                    .head()
                    .tolist()
                )

            # ==================================================
            # GENERAR PREVIEW
            # ==================================================

            if df is not None:

                df_salida = (
                    preparar_df_sistemas(
                        df
                    )
                )

                preview = (
                    df_salida.to_html(
                        classes=(
                            "table "
                            "table-striped "
                            "table-bordered"
                        ),
                        index=False,
                    )
                )

                total_registros = len(
                    df_salida
                )

                # Guardamos YA CON las sucursales elegidas.
                guardar_temporal(
                    lote_id,
                    df_salida,
                )

                session[
                    "cenefas_sistemas_fecha_desde"
                ] = fecha_desde

                session[
                    "cenefas_sistemas_fecha_hasta"
                ] = fecha_hasta

        except Exception as e:

            print(
                "ERROR DEBUG:",
                e
            )

            mensaje_error = (
                f"Error de backend: {e}"
            )

    return render_template(
        "cenefas_sistemas.html",
        preview=preview,
        mensaje_error=mensaje_error,
        total_registros=total_registros,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        grupo_sucursales=grupo_sucursales,
        sucursal_map=SUCURSAL_MAP,
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
        df.to_excel(writer, index=False, sheet_name="Hoja1")

    output.seek(0)

    nombre_archivo = f"cenefas_sistemas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    return send_file(
        output,
        as_attachment=True,
        download_name=nombre_archivo,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )