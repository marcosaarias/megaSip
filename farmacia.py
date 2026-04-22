import os
import pandas as pd
import numpy as np
from flask import Blueprint, render_template, request, send_file

farmacia_bp = Blueprint("farmacia", __name__)

ARCHIVO_TEMP = "temp_procesado_farmacia.xlsx"


def limpiar_numero(serie):
    print(f"\nDEBUG LIMPIEZA - dtype inicial: {serie.dtype}")
    print("ANTES:")
    print(serie.head(10))

    if not pd.api.types.is_object_dtype(serie):
        out = pd.to_numeric(serie, errors="coerce")
    else:
        s = (
            serie.astype(str)
            .str.replace("\xa0", "", regex=False)
            .str.replace(" ", "", regex=False)
            .str.strip()
        )

        s = s.replace({
            "": np.nan,
            "nan": np.nan,
            "None": np.nan,
            "NULL": np.nan,
            "NaN": np.nan,
            "#N/A": np.nan,
            "#VALUE!": np.nan,
            "#REF!": np.nan
        })

        def convertir_valor(x):
            if pd.isna(x):
                return np.nan

            x = str(x).strip()

            if "," in x and "." in x:
                if x.rfind(",") > x.rfind("."):
                    x = x.replace(".", "").replace(",", ".")
                else:
                    x = x.replace(",", "")
            elif "," in x:
                x = x.replace(",", ".")

            try:
                return float(x)
            except ValueError:
                return np.nan

        out = s.apply(convertir_valor)

    print("DESPUES:")
    print(out.head(10))
    print("NaN count:", out.isna().sum())
    print("---------\n")
    return out


@farmacia_bp.route("/", methods=["GET", "POST"])
def index():
    preview = None
    error = None

    if request.method == "POST":
        archivo = request.files.get("archivo")

        if archivo:
            try:
                df = pd.read_excel(archivo)

                df.columns = [str(col).strip() for col in df.columns]

                print("\n========== COLUMNAS DEL EXCEL ==========")
                for i, c in enumerate(df.columns):
                    print(f"{i}: '{c}'")
                print("========================================\n")

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

                    if "costo" in col_lower and "neto" in col_lower:
                        col_costo_neto = col

                if col_precio_mi and col_codigo:
                    idx_codigo = df.columns.get_loc(col_codigo)

                    nuevas_cols = ["Costo_tmp", "Precio_tmp", "Col3", "Col4", "Col5"]

                    for i, nueva in enumerate(nuevas_cols):
                        if nueva not in df.columns:
                            df.insert(idx_codigo + i, nueva, None)

                    print("\n========== DEBUG COLUMNAS DETECTADAS ==========")
                    print("Costo Neto:", col_costo_neto)
                    print("Costo:", col_costo)
                    print("Precio MI:", col_precio_mi)
                    print("Precio:", col_precio)
                    print("==============================================\n")

                    # Guardar originales sin tocar
                    df_debug = pd.DataFrame(index=df.index)
                    if col_costo_neto:
                        df_debug["Costo Neto ORIGINAL"] = df[col_costo_neto]
                    if col_costo:
                        df_debug["Costo ORIGINAL"] = df[col_costo]
                    if col_precio_mi:
                        df_debug["Precio Mi ORIGINAL"] = df[col_precio_mi]
                    if col_precio:
                        df_debug["Precio ORIGINAL"] = df[col_precio]

                    print("\n========== MUESTRA ORIGINAL ==========")
                    cols_print = [c for c in [
                        "Costo Neto ORIGINAL", "Costo ORIGINAL",
                        "Precio Mi ORIGINAL", "Precio ORIGINAL"
                    ] if c in df_debug.columns]
                    print(df_debug[cols_print].head(30).to_string())
                    print("======================================\n")

                    # Limpiar
                    for col in [col_costo, col_precio, col_costo_neto, col_precio_mi]:
                        if col:
                            df[col] = limpiar_numero(df[col])

                    # Comparativo
                    if col_costo_neto:
                        df_debug["Costo Neto LIMPIO"] = df[col_costo_neto]
                    if col_costo:
                        df_debug["Costo LIMPIO"] = df[col_costo]
                    if col_precio_mi:
                        df_debug["Precio Mi LIMPIO"] = df[col_precio_mi]
                    if col_precio:
                        df_debug["Precio LIMPIO"] = df[col_precio]

                    print("\n========== COMPARATIVO ==========")
                    cols_print = [c for c in [
                        "Costo Neto ORIGINAL", "Costo Neto LIMPIO",
                        "Costo ORIGINAL", "Costo LIMPIO",
                        "Precio Mi ORIGINAL", "Precio Mi LIMPIO",
                        "Precio ORIGINAL", "Precio LIMPIO"
                    ] if c in df_debug.columns]
                    print(df_debug[cols_print].head(40).to_string())
                    print("=================================\n")

                    print("\n========== NULOS ==========")
                    cols_debug = [c for c in [col_costo_neto, col_costo, col_precio_mi, col_precio] if c]
                    print(df[cols_debug].isna().sum())
                    print("===========================\n")

                    if col_costo:
                        df["Costo_tmp"] = df[col_costo]
                    if col_precio:
                        df["Precio_tmp"] = df[col_precio]

                    # Col3
                    if col_costo_neto and col_costo:
                        df["Col3"] = np.where(
                            df[col_costo_neto].notna() & df[col_costo].notna(),
                            df[col_costo_neto] - df[col_costo],
                            np.nan
                        )
                    else:
                        df["Col3"] = np.nan

                    # Col4
                    if col_precio_mi and col_precio:
                        df["Col4"] = np.where(
                            df[col_precio_mi].notna() & df[col_precio].notna(),
                            df[col_precio_mi] - df[col_precio],
                            np.nan
                        )
                    else:
                        df["Col4"] = np.nan

                    # Col5
                    col5 = []
                    for g4, g3 in zip(df["Col4"], df["Col3"]):
                        if pd.notna(g4) and abs(g4) < 1:
                            col5.append("menos de $1")
                        else:
                            col5.append(g3)
                    df["Col5"] = col5

                    print("\n========== MUESTRA FINAL ==========")
                    mostrar = [c for c in ["Costo Neto", "Costo", "Col3"] if c in df.columns]
                    print(df[mostrar].head(50).to_string())
                    print("===================================\n")

                    cols_a_borrar = [c for c in [col_costo, col_precio] if c]
                    df.drop(columns=cols_a_borrar, inplace=True, errors="ignore")

                    df.rename(columns={
                        "Costo_tmp": "Costo",
                        "Precio_tmp": "Precio"
                    }, inplace=True)

                else:
                    print("No se encontraron columnas clave")

                # Guardar archivo procesado para descarga
                df.to_excel(ARCHIVO_TEMP, index=False)

                preview = df.to_html(
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


@farmacia_bp.route("/descargar", methods=["GET"])
def descargar():
    if not os.path.exists(ARCHIVO_TEMP):
        return "No hay archivo procesado para descargar", 404

    return send_file(
        ARCHIVO_TEMP,
        as_attachment=True,
        download_name="farmacia_procesado.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )