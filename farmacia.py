import os
import pandas as pd
import numpy as np
import sqlite3
from flask import Blueprint, render_template, request, send_file

farmacia_bp = Blueprint("farmacia", __name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "sip.s3db")

ARCHIVO_TEMP = os.path.join(os.path.dirname(__file__), "temp_procesado_farmacia.xlsx")

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


def autocompletar_super_desde_cenefas(df):
    if "Troquel" not in df.columns:
        return df

    conn = sqlite3.connect(DB_PATH)

    try:
        consulta = """
            SELECT Codigo, descripcion, cenefa
            FROM cenefas
        """
        cenefas_df = pd.read_sql_query(consulta, conn)
    finally:
        conn.close()

    # Normalizar Codigo de BD
    cenefas_df["Codigo_match"] = (
        cenefas_df["Codigo"]
        .astype(str)
        .str.strip()
        .str.replace(".0", "", regex=False)
        .str.lstrip("0")
    )

    # Evitar duplicados de código; si hay varios, toma el último
    cenefas_df = cenefas_df.dropna(subset=["Codigo_match"])
    cenefas_df = cenefas_df.drop_duplicates(subset=["Codigo_match"], keep="last")

    mapa_descripcion = dict(zip(cenefas_df["Codigo_match"], cenefas_df["descripcion"]))
    mapa_cenefa = dict(zip(cenefas_df["Codigo_match"], cenefas_df["cenefa"]))

    # Normalizar Troquel del Excel
    troquel_match = (
        df["Troquel"]
        .astype(str)
        .str.strip()
        .str.replace(".0", "", regex=False)
        .str.lstrip("0")
        .replace({"": np.nan, "nan": np.nan, "None": np.nan})
    )

    df["F-Super"] = troquel_match.map(mapa_descripcion).fillna("#N/D")
    df["A-Super"] = troquel_match.map(mapa_cenefa).fillna("#N/D")

    return df



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

                if "Troquel" in df.columns:
                    idx_troquel = df.columns.get_loc("Troquel")

                    nuevas_cols = ["F-Super", "A-Super", "F-Farmacia", "A-Farmacia"]

                    for i, col_nueva in enumerate(nuevas_cols, start=1):
                        if col_nueva not in df.columns:
                            df.insert(idx_troquel + i, col_nueva, None)
                    df = autocompletar_super_desde_cenefas(df)
                df = autocompletar_farmacia_desde_folder(df)

                if "Estado" in df.columns:
                    df = df[df["Estado"].notna()]

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

                    df.rename(columns={
                        "Col3": "Dif Cost",
                        "Col4": "dif Precio",
                        "Col5": "diferencia"
                    }, inplace=True)

                    df = df[df["diferencia"].notna()]

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


def autocompletar_farmacia_desde_folder(df):
    col_troquel = None

    for col in df.columns:
        col_lower = str(col).strip().lower()

        if col_lower in ["troquel", "troq", "nro troquel", "n° troquel", "numero troquel", "número troquel"]:
            col_troquel = col
            break

        if "troquel" in col_lower:
            col_troquel = col
            break

    if col_troquel is None:
        print("No se encontró columna Troquel en el Excel", flush=True)
        df["F-Farmacia"] = "#N/D"
        df["A-Farmacia"] = "#N/D"
        return df

    print("Columna troquel usada para farmacia:", col_troquel, flush=True)

    print("\n========== DEBUG TROQUEL EXCEL ==========", flush=True)
    print("Nombre exacto columna:", repr(col_troquel), flush=True)
    print("Tipo columna:", df[col_troquel].dtype, flush=True)
    print("Cantidad filas:", len(df), flush=True)
    print("Nulos:", df[col_troquel].isna().sum(), flush=True)

    print("\nPrimeros 20 valores CRUDOS:", flush=True)
    print(df[col_troquel].head(20).apply(repr).to_string(), flush=True)

    debug_troquel_excel = (
        df[col_troquel]
        .astype(str)
        .str.strip()
        .str.replace(".0", "", regex=False)
        .str.lstrip("0")
        .replace({"": np.nan, "nan": np.nan, "None": np.nan})
    )

    print("\nPrimeros 20 valores NORMALIZADOS:", flush=True)
    print(debug_troquel_excel.head(20).apply(repr).to_string(), flush=True)

    print("\nValores únicos normalizados, primeros 30:", flush=True)
    print(debug_troquel_excel.dropna().unique()[:30], flush=True)
    print("=========================================\n", flush=True)

    conn = sqlite3.connect(DB_PATH)

    try:
        consulta = """
            SELECT troquel, descripcion, promo
            FROM farmacia_folder
        """
        folder_df = pd.read_sql_query(consulta, conn)
    finally:
        conn.close()

    print("\n========== DEBUG BD ORIGINAL ==========", flush=True)
    print("Filas traídas de farmacia_folder:", len(folder_df), flush=True)
    print("Columnas BD:", folder_df.columns.tolist(), flush=True)
    print("Tipos BD:", flush=True)
    print(folder_df.dtypes, flush=True)

    print("\nPrimeras 20 filas BD:", flush=True)
    print(folder_df.head(20).to_string(), flush=True)
    print("=======================================\n", flush=True)

    folder_df["troquel_match"] = (
        folder_df["troquel"]
        .astype(str)
        .str.strip()
        .str.replace(".0", "", regex=False)
        .str.lstrip("0")
        .replace({"": np.nan, "nan": np.nan, "None": np.nan})
    )

    print("\n========== DEBUG TROQUEL BD ==========", flush=True)
    print("Tipo troquel BD:", folder_df["troquel"].dtype, flush=True)

    print("\nPrimeros 20 troqueles BD CRUDOS:", flush=True)
    print(folder_df["troquel"].head(20).apply(repr).to_string(), flush=True)

    print("\nPrimeros 20 troqueles BD NORMALIZADOS:", flush=True)
    print(folder_df["troquel_match"].head(20).apply(repr).to_string(), flush=True)

    print("\nValores únicos BD normalizados, primeros 30:", flush=True)
    print(folder_df["troquel_match"].dropna().unique()[:30], flush=True)
    print("======================================\n", flush=True)

    folder_df["descripcion"] = folder_df["descripcion"].replace(
        {"": np.nan, "nan": np.nan, "None": np.nan}
    )

    folder_df["promo"] = folder_df["promo"].replace(
        {"": np.nan, "nan": np.nan, "None": np.nan}
    )

    folder_df = folder_df.dropna(subset=["troquel_match"])
    folder_df = folder_df.drop_duplicates(subset=["troquel_match"], keep="last")

    mapa_descripcion = dict(zip(folder_df["troquel_match"], folder_df["descripcion"]))
    mapa_promo = dict(zip(folder_df["troquel_match"], folder_df["promo"]))

    troquel_match = (
        df[col_troquel]
        .astype(str)
        .str.strip()
        .str.replace(".0", "", regex=False)
        .str.lstrip("0")
        .replace({"": np.nan, "nan": np.nan, "None": np.nan})
    )

    troqueles_excel = set(troquel_match.dropna().unique())
    troqueles_bd = set(folder_df["troquel_match"].dropna().unique())

    interseccion = troqueles_excel.intersection(troqueles_bd)

    print("\n========== DEBUG MATCH TROQUEL ==========", flush=True)
    print("Total troqueles Excel:", len(troqueles_excel), flush=True)
    print("Total troqueles BD:", len(troqueles_bd), flush=True)
    print("Coincidencias:", len(interseccion), flush=True)

    print("\nEjemplos Excel:", flush=True)
    print(list(troqueles_excel)[:20], flush=True)

    print("\nEjemplos BD:", flush=True)
    print(list(troqueles_bd)[:20], flush=True)

    print("\nEjemplos coincidencias:", flush=True)
    print(list(interseccion)[:20], flush=True)
    print("=========================================\n", flush=True)

    df["F-Farmacia"] = troquel_match.map(mapa_descripcion)
    df["A-Farmacia"] = troquel_match.map(mapa_promo)

    print("\n========== DEBUG RESULTADO MAP ==========", flush=True)
    print("F-Farmacia encontrados antes fillna:", df["F-Farmacia"].notna().sum(), flush=True)
    print("A-Farmacia encontrados antes fillna:", df["A-Farmacia"].notna().sum(), flush=True)

    print("\nMuestra resultado antes fillna:", flush=True)
    print(df[[col_troquel, "F-Farmacia", "A-Farmacia"]].head(30).to_string(), flush=True)
    print("========================================\n", flush=True)

    df["F-Farmacia"] = df["F-Farmacia"].replace(
        {"": np.nan, "nan": np.nan, "None": np.nan}
    ).fillna("#N/D")

    df["A-Farmacia"] = df["A-Farmacia"].replace(
        {"": np.nan, "nan": np.nan, "None": np.nan}
    ).fillna("#N/D")

    print("\n========== DEBUG RESULTADO FINAL ==========", flush=True)
    print("F-Farmacia distintos de #N/D:", (df["F-Farmacia"] != "#N/D").sum(), flush=True)
    print("A-Farmacia distintos de #N/D:", (df["A-Farmacia"] != "#N/D").sum(), flush=True)

    print("\nMuestra resultado final:", flush=True)
    print(df[[col_troquel, "F-Farmacia", "A-Farmacia"]].head(30).to_string(), flush=True)
    print("==========================================\n", flush=True)

    return df

#================================================
# descarga de archivo
#================================================

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