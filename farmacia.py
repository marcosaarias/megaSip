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

                # 🔍 Normalizar nombres
                df.columns = [str(col).strip() for col in df.columns]

                print("\n===== DEBUG COLUMNAS =====")
                for col in df.columns:
                    print(f"👉 '{col}'")
                print("===========================\n")

                # 🔎 Detectar columnas
                col_precio_mi = None
                col_codigo = None
                col_costo = None
                col_precio = None
                col_costo_neto = None

                for col in df.columns:
                    col_lower = col.lower()

                    if "precio mi" in col_lower:
                        col_precio_mi = col

                    if "cod" in col_lower and "product" in col_lower:
                        col_codigo = col

                    if col_lower == "costo":
                        col_costo = col

                    if col_lower == "precio":
                        col_precio = col

                    if "costo neto" in col_lower:
                        col_costo_neto = col

                print("MATCH:")
                print("Precio MI:", col_precio_mi)
                print("Código:", col_codigo)
                print("Costo:", col_costo)
                print("Precio:", col_precio)
                print("Costo Neto:", col_costo_neto)

                # ✅ VALIDACIÓN
                if col_precio_mi and col_codigo:
                    idx_codigo = df.columns.get_loc(col_codigo)

                    # 🔥 Insertar columnas nuevas antes de Cod.Producto
                    nuevas_cols = ["Costo_tmp", "Precio_tmp", "Col3", "Col4", "Col5"]

                    for i, nueva in enumerate(nuevas_cols):
                        df.insert(idx_codigo + i, nueva, "")

                    # 🔥 Convertir a numérico (clave para cálculos)
                    if col_costo:
                        df[col_costo] = pd.to_numeric(df[col_costo], errors="coerce")

                    if col_precio:
                        df[col_precio] = pd.to_numeric(df[col_precio], errors="coerce")

                    if col_costo_neto:
                        df[col_costo_neto] = pd.to_numeric(df[col_costo_neto], errors="coerce")

                    if col_precio_mi:
                        df[col_precio_mi] = pd.to_numeric(df[col_precio_mi], errors="coerce")

                    # 🔥 MOVER datos
                    if col_costo:
                        df["Costo_tmp"] = df[col_costo]

                    if col_precio:
                        df["Precio_tmp"] = df[col_precio]

                    # 🔥 CALCULOS
                    if col_costo_neto and col_costo:
                        df["Col3"] = df[col_costo_neto] - df[col_costo]

                    if col_precio_mi and col_precio:
                        df["Col4"] = df[col_precio_mi] - df[col_precio]

                    # 🔥 BORRAR columnas originales
                    cols_a_borrar = []
                    if col_costo:
                        cols_a_borrar.append(col_costo)
                    if col_precio:
                        cols_a_borrar.append(col_precio)

                    df.drop(columns=cols_a_borrar, inplace=True)

                    # 🔥 RENOMBRAR columnas nuevas
                    df.rename(columns={
                        "Costo_tmp": "Costo",
                        "Precio_tmp": "Precio"
                    }, inplace=True)

                else:
                    print("⚠️ No se encontraron columnas clave")

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