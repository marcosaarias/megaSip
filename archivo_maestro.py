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