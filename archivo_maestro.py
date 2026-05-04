import os
import uuid
import os
import uuid
import pandas as pd
from flask import Blueprint, render_template, request, send_file, flash, redirect, url_for

archivo_maestro_bp = Blueprint("archivo_maestro", __name__)

BASE_DIR = os.path.dirname(__file__)
CACHE_DIR = os.path.join(BASE_DIR, "cache_archivo_maestro")

os.makedirs(CACHE_DIR, exist_ok=True)

#@archivo_maestro_bp.route("/", methods=["GET", "POST"])
#def index():
#    preview = None
#    total_registros = None
#    mensaje_error = None
#    cache_id = None

#    if request.method == "POST":
#        archivo = request.files.get("archivo")

#        if not archivo or archivo.filename == "":
#            mensaje_error = "Debe seleccionar un archivo Excel."
#            return render_template(
#                "farmacia/archivo_maestro.html",
#                preview=preview,
#                total_registros=total_registros,
#                mensaje_error=mensaje_error,
#                cache_id=cache_id
#            )

#        try:
#            df = pd.read_excel(archivo)

#            print("COLUMNAS ORIGINALES:", df.columns.tolist())

#            df.columns = (
#                df.columns
#                .astype(str)
#                .str.strip()
#                .str.lower()
#            )

#            print("COLUMNAS NORMALIZADAS:", df.columns.tolist())
           
#            columna_costo = None
#            columna_iva = None

#            for col in df.columns:
#                if "costo" in col:
#                    columna_costo = col
#                if "iva" in col:
#                    columna_iva = col

#            if columna_costo is None:
#                mensaje_error = f"No se encontró ninguna columna de costo. Columnas detectadas: {df.columns.tolist()}"
#                return render_template(
#                    "farmacia/archivo_maestro.html",
#                    preview=preview,
#                    total_registros=total_registros,
#                    mensaje_error=mensaje_error,
#                    cache_id=cache_id
#                )

#            if columna_iva is None:
#                mensaje_error = f"No se encontró ninguna columna IVA. Columnas detectadas: {df.columns.tolist()}"
#                return render_template(
#                    "farmacia/archivo_maestro.html",
#                    preview=preview,
#                    total_registros=total_registros,
#                    mensaje_error=mensaje_error,
#                    cache_id=cache_id
#                )

#            df[columna_costo] = pd.to_numeric(
#                df[columna_costo],
#                errors="coerce"
#            )

#            df[columna_iva] = pd.to_numeric(
#                df[columna_iva],
#                errors="coerce"
#            )

#            columna_factor = 1 + (df[columna_iva] / 100)

           
#            df.insert(
#                loc=len(df.columns),  # temporal, después la movemos
#                column="tmp_factor",
#                value=columna_factor
#            )

            # Columna original
#            df["costo sin iva"] = df[columna_costo] * 100

            # Reordenar: poner la nueva antes de "costo sin iva"
 #           cols = df.columns.tolist()

#            idx = cols.index("costo sin iva")
#            cols.insert(idx, cols.pop(cols.index("tmp_factor")))

#            df = df[cols]

            # Quitar header (nombre vacío)
#            df.rename(columns={"tmp_factor": ""}, inplace=True)

#            total_registros = len(df)

#            preview = df.to_html(
#                classes="table table-striped table-bordered table-sm",
#                index=False
#            )

 #           cache_id = str(uuid.uuid4())
 #           archivo_cache = os.path.join(CACHE_DIR, f"{cache_id}.xlsx")

#            df.to_excel(archivo_cache, index=False)

 #           flash("Archivo previsualizado correctamente.", "success")

#        except Exception as e:
#            mensaje_error = f"Error al procesar el archivo: {str(e)}"

#    return render_template(
#        "farmacia/archivo_maestro.html",
#        preview=preview,
#        total_registros=total_registros,
#        mensaje_error=mensaje_error,
#        cache_id=cache_id
#    )


@archivo_maestro_bp.route("/", methods=["GET", "POST"])
def index():
    preview = None
    total_registros = None
    mensaje_error = None
    cache_id = None

    if request.method == "POST":
        archivo = request.files.get("archivo")

        if not archivo or archivo.filename == "":
            mensaje_error = "Debe seleccionar un archivo Excel."
            return render_template(
                "farmacia/archivo_maestro.html",
                preview=preview,
                total_registros=total_registros,
                mensaje_error=mensaje_error,
                cache_id=cache_id
            )

        try:
            df = pd.read_excel(archivo)

            df.columns = (
                df.columns
                .astype(str)
                .str.strip()
                .str.lower()
            )

            columna_costo = None
            columna_iva = None

            for col in df.columns:
                if col == "costo":
                    columna_costo = col
                if col == "iva":
                    columna_iva = col

            if columna_costo is None:
                mensaje_error = f"No se encontró la columna costo. Columnas detectadas: {df.columns.tolist()}"
                return render_template(
                    "farmacia/archivo_maestro.html",
                    preview=preview,
                    total_registros=total_registros,
                    mensaje_error=mensaje_error,
                    cache_id=cache_id
                )

            if columna_iva is None:
                mensaje_error = f"No se encontró la columna IVA. Columnas detectadas: {df.columns.tolist()}"
                return render_template(
                    "farmacia/archivo_maestro.html",
                    preview=preview,
                    total_registros=total_registros,
                    mensaje_error=mensaje_error,
                    cache_id=cache_id
                )

            df[columna_costo] = pd.to_numeric(df[columna_costo], errors="coerce")
            df[columna_iva] = pd.to_numeric(df[columna_iva], errors="coerce")

            if "precio" not in df.columns:
                mensaje_error = f"No se encontró la columna precio. Columnas detectadas: {df.columns.tolist()}"
                return render_template(
                    "farmacia/archivo_maestro.html",
                    preview=preview,
                    total_registros=total_registros,
                    mensaje_error=mensaje_error,
                    cache_id=cache_id
                )
            df["precio"] = pd.to_numeric(df["precio"], errors="coerce")

            # Factor IVA: IVA 21 -> 1.21
            columna_factor = 1 + (df[columna_iva] / 100)

            # Columna sin encabezado con el factor
            df["tmp_factor"] = columna_factor.round(2)

            # Columna amarilla: costo * factor IVA
            df["costo con iva"] = (
                df[columna_costo] * columna_factor
            ).round(4)

            df["precio / costo con iva"] = (
                df["precio"] / df["costo con iva"]
            ).round(4)

            df["rent"] = (
                (df["precio"] / df["costo con iva"] - 1) * 10000
            ).round(2)

            # Columna costo sin iva
            df["costo sin iva"] = df[columna_costo] * 100

            # Poner tmp_factor antes de costo con iva
            cols = df.columns.tolist()
            cols.insert(
                cols.index("costo con iva"),
                cols.pop(cols.index("tmp_factor"))
            )
            df = df[cols]

            # Quitar header de tmp_factor
            df.rename(columns={"tmp_factor": ""}, inplace=True)

            total_registros = len(df)

            preview = df.to_html(
                classes="table table-striped table-bordered table-sm",
                index=False
            )

            cache_id = str(uuid.uuid4())
            archivo_cache = os.path.join(CACHE_DIR, f"{cache_id}.xlsx")

            df.to_excel(archivo_cache, index=False)

            flash("Archivo previsualizado correctamente.", "success")

        except Exception as e:
            mensaje_error = f"Error al procesar el archivo: {str(e)}"

    return render_template(
        "farmacia/archivo_maestro.html",
        preview=preview,
        total_registros=total_registros,
        mensaje_error=mensaje_error,
        cache_id=cache_id
    )

@archivo_maestro_bp.route("/descargar/<cache_id>")
def descargar_archivo(cache_id):
    archivo_cache = os.path.join(CACHE_DIR, f"{cache_id}.xlsx")

    if not os.path.exists(archivo_cache):
        flash("El archivo ya no está disponible para descargar.", "danger")
        return redirect(url_for("archivo_maestro.index"))

    return send_file(
        archivo_cache,
        as_attachment=True,
        download_name="archivo_maestro_previsualizado.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )