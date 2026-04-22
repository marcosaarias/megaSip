import os
import pandas as pd
from flask import Blueprint, render_template, request

farmacia_bp = Blueprint("farmacia", __name__)

@farmacia_bp.route("/", methods=["GET", "POST"])
def index():
    preview = None
    error = None

    if request.method == "POST":
        archivo = request.files.get("archivo")

        if archivo:
            try:
                df = pd.read_excel(archivo)

                # 🔍 Normalizar nombres de columnas
                df.columns = [str(col).strip() for col in df.columns]

                # 🔎 Buscar columnas clave
                col_precio = None
                col_codigo = None

                for col in df.columns:
                    col_lower = col.lower()
                    if "precio" in col_lower and "mi" in col_lower:
                        col_precio = col
                    if "cod" in col_lower and "product" in col_lower:
                        col_codigo = col

                # ⚠️ Validar que existan
                if col_precio and col_codigo:
                    idx_precio = df.columns.get_loc(col_precio)

                    # 🧩 Crear columnas nuevas
                    nuevas_cols = [
                        "Col1", "Col2", "Col3", "Col4", "Col5"
                    ]

                    for i, nueva in enumerate(nuevas_cols):
                        df.insert(idx_precio + 1 + i, nueva, "")

                else:
                    print("⚠️ No se encontraron las columnas esperadas")

                # Preview
                df_preview = df.head(50)

                preview = df_preview.to_html(
                    classes="table table-striped table-hover table-bordered",
                    index=False
                )

            except Exception as e:
                error = f"Error procesando archivo: {e}"

    return render_template(
        "farmacia.html",
        preview=preview,
        error=error
    )