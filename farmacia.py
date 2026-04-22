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

                # =========================
                # 🔍 DEBUG COLUMNAS ORIGINALES
                # =========================
                print("\n========= COLUMNAS ORIGINALES =========")
                for col in df.columns:
                    print(f"👉 '{col}'")
                print("=======================================\n")

                # 🔍 Normalizar nombres
                df.columns = [str(col).strip() for col in df.columns]

                # =========================
                # 🔍 DEBUG COLUMNAS NORMALIZADAS
                # =========================
                print("\n========= COLUMNAS NORMALIZADAS =========")
                for col in df.columns:
                    print(f"👉 '{col}'")
                print("=========================================\n")

                # 🔎 Buscar columnas clave
                col_precio = None
                col_codigo = None

                for col in df.columns:
                    col_lower = col.lower()

                    print(f"Analizando: {col_lower}")  # 👈 DEBUG

                    if "precio" in col_lower and "mi" in col_lower:
                        col_precio = col
                        print(f"✅ MATCH PRECIO: {col}")

                    if "cod" in col_lower and "product" in col_lower:
                        col_codigo = col
                        print(f"✅ MATCH CODIGO: {col}")

                # =========================
                # 🔍 RESULTADO MATCH
                # =========================
                print("\n========= RESULTADO MATCH =========")
                print(f"Precio detectado: {col_precio}")
                print(f"Codigo detectado: {col_codigo}")
                print("==================================\n")

                # =========================
                # 🧩 INSERTAR COLUMNAS
                # =========================
                if col_precio and col_codigo:

                    idx_precio = df.columns.get_loc(col_precio)
                    idx_codigo = df.columns.get_loc(col_codigo)

                    print(f"Posición Precio: {idx_precio}")
                    print(f"Posición Codigo: {idx_codigo}")

                    # 🔥 Insertar justo ANTES de Cod.Product
                    insert_pos = min(idx_precio, idx_codigo) + 1

                    nuevas_cols = ["Col1", "Col2", "Col3", "Col4", "Col5"]

                    for i, nueva in enumerate(nuevas_cols):
                        df.insert(insert_pos + i, nueva, "")

                    print("✅ Columnas insertadas correctamente")

                else:
                    print("❌ No se encontraron las columnas esperadas")

                # =========================
                # 👀 PREVIEW
                # =========================
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