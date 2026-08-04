import os
import pandas as pd
import numpy as np
from flask import session, request
from datetime import datetime
import uuid
from flask import Blueprint, render_template, request, send_file, g
from database.db import get_db_connection
from farmacia_folder import obtener_datos_farmacia_folder


farmacia_bp = Blueprint("farmacia", __name__)

#@farmacia_bp.route("/cenefas-farmacia", methods=["GET"])
#def cenefas_farmacia():
#    return render_template(
#        "farmacia/cenefas_farmacia.html",
#        datos=[]
#    )



@farmacia_bp.route("/cenefas-farmacia", methods=["GET"])
def cenefas_farmacia():

    tipo_cenefa = request.args.get(
        "tipo_cenefa",
        "folder"
    ).strip().lower()

    tipos_validos = {
        "folder",
        "diarios",
        "nutricia"
    }

    if tipo_cenefa not in tipos_validos:
        tipo_cenefa = "folder"

    datos = obtener_datos_farmacia_folder(tipo_cenefa)

    print(
        f"DEBUG CENEFAS FARMACIA [{tipo_cenefa}] - TOTAL:",
        len(datos),
        flush=True
    )

    if datos:
        print(
            "DEBUG PRIMER REGISTRO:",
            datos[0],
            flush=True
        )

    return render_template(
        "farmacia/cenefas_farmacia.html",
        datos=datos,
        tipo_cenefa=tipo_cenefa
    )

#@farmacia_bp.route("/cenefas-farmacia", methods=["GET"])
#def cenefas_farmacia():
#    conn = get_db_connection()
#    cur = conn.cursor()

#    try:
#        cur.execute("""
#            SELECT
#                troquel,
#                cod_barra,
#                descripcion,
#                normal,
#                oferta,
#                promo,
#                fecha_desde,
#                fecha_hasta
#            FROM farmacia_folder
#            ORDER BY id DESC
#        """)

#        datos = cur.fetchall()

#    finally:
#        cur.close()
#        conn.close()

#    return render_template(
#        "farmacia/cenefas_farmacia.html",
#        datos=datos
#    )




@farmacia_bp.before_request
def medir_ingreso_farmacia():
    crear_tabla_metricas()

    ahora = datetime.now()

    if "farmacia_session_id" not in session:
        session["farmacia_session_id"] = str(uuid.uuid4())
        session["farmacia_inicio"] = ahora.isoformat()

        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO farmacia_metricas (
                    session_id, ruta, metodo, fecha_ingreso,
                    ultima_actividad, duracion_segundos, ip, user_agent
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                session["farmacia_session_id"],
                request.path,
                request.method,
                ahora.isoformat(),
                ahora.isoformat(),
                0,
                request.remote_addr,
                request.headers.get("User-Agent", "")
            ))
            conn.commit()
        finally:
            conn.close()

    g.farmacia_request_time = ahora


@farmacia_bp.after_request
def actualizar_tiempo_farmacia(response):
    session_id = session.get("farmacia_session_id")
    inicio = session.get("farmacia_inicio")

    if session_id and inicio:
        ahora = datetime.now()
        inicio_dt = datetime.fromisoformat(inicio)
        duracion = int((ahora - inicio_dt).total_seconds())

        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                UPDATE farmacia_metricas
                SET ultima_actividad = %s,
                    duracion_segundos = %s,
                    ruta = %s
                WHERE session_id = %s
            """, (
                ahora.isoformat(),
                duracion,
                request.path,
                session_id
            ))
            conn.commit()
        finally:
            conn.close()

    return response


ARCHIVO_TEMP = os.path.join(os.path.dirname(__file__), "temp_procesado_farmacia.xlsx")

#medir tiempo de conexion
def crear_tabla_metricas():
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS farmacia_metricas (
                id SERIAL PRIMARY KEY,
                session_id TEXT,
                ruta TEXT,
                metodo TEXT,
                fecha_ingreso TEXT,
                ultima_actividad TEXT,
                duracion_segundos INTEGER,
                ip TEXT,
                user_agent TEXT
            )
        """)
        conn.commit()
    finally:
        cur.close()
        conn.close()


@farmacia_bp.route("/rubros")
def rubros_view():
    return render_template("farmacia/rubros.html")


@farmacia_bp.route("/subrubros")
def subrubros_view():
    return render_template("farmacia/subrubros.html")


@farmacia_bp.route("/laboratorios")
def laboratorios_view():
    return render_template("farmacia/laboratorios.html")


@farmacia_bp.route("/archivo-maestro")
def generar_archivo_maestro():
    return render_template("farmacia/archivo_maestro.html")


def limpiar_numero(serie):
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
    return out


def autocompletar_super_desde_cenefas(df):
    if "Troquel" not in df.columns:
        print("SUPER DEBUG: no existe columna Troquel en el Excel", flush=True)
        return df

    #conn = get_db_connection()
    conn = get_db_connection(real_dict=False)

    #try:
    #    consulta = """
    #        SELECT codigo, descripcion, cenefa
    #        FROM cenefas
    #    """
    #    cenefas_df = pd.read_sql_query(consulta, conn)
    #finally:
    #    conn.close()

    try:
        consulta = """
            SELECT
                codigo::text AS codigo,
                descripcion,
                cenefa
            FROM cenefas
            WHERE codigo IS NOT NULL
            AND trim(codigo::text) <> ''
            AND lower(trim(codigo::text)) <> 'codigo'
        """
        cenefas_df = pd.read_sql_query(consulta, conn)
    finally:
        conn.close()

    print("========== DEBUG SUPER ==========", flush=True)
    print("Filas BD cenefas:", len(cenefas_df), flush=True)
    print("Columnas BD cenefas:", cenefas_df.columns.tolist(), flush=True)
    print(cenefas_df.head(20).to_string(), flush=True)
    print("CODIGOS RAW BD:", cenefas_df["codigo"].head(20).tolist(), flush=True)

    cenefas_df["Codigo_match"] = (
        cenefas_df["codigo"]
        .astype(str)
        .str.strip()
        .str.replace(".0", "", regex=False)
        .str.lstrip("0")
        .replace({"": np.nan, "nan": np.nan, "None": np.nan})
    )

    cenefas_df = cenefas_df.dropna(subset=["Codigo_match"])
    cenefas_df = cenefas_df.drop_duplicates(subset=["Codigo_match"], keep="last")

    mapa_descripcion = dict(zip(cenefas_df["Codigo_match"], cenefas_df["descripcion"]))
    mapa_cenefa = dict(zip(cenefas_df["Codigo_match"], cenefas_df["cenefa"]))

    troquel_match = (
        df["Troquel"]
        .astype(str)
        .str.strip()
        .str.replace(".0", "", regex=False)
        .str.lstrip("0")
        .replace({"": np.nan, "nan": np.nan, "None": np.nan})
    )

    troqueles_excel = set(troquel_match.dropna().unique())
    troqueles_bd = set(cenefas_df["Codigo_match"].dropna().unique())
    interseccion = troqueles_excel.intersection(troqueles_bd)

    print("TOTAL TROQUELES EXCEL:", len(troqueles_excel), flush=True)
    print("TOTAL CODIGOS BD:", len(troqueles_bd), flush=True)
    print("COINCIDENCIAS SUPER:", len(interseccion), flush=True)
    print("EJEMPLOS EXCEL:", list(troqueles_excel)[:10], flush=True)
    print("EJEMPLOS BD:", list(troqueles_bd)[:10], flush=True)
    print("EJEMPLOS MATCH:", list(interseccion)[:10], flush=True)

    df["F-Super"] = troquel_match.map(mapa_descripcion)
    df["A-Super"] = troquel_match.map(mapa_cenefa)

    print("F-Super encontrados:", df["F-Super"].notna().sum(), flush=True)
    print("A-Super encontrados:", df["A-Super"].notna().sum(), flush=True)

    df["F-Super"] = df["F-Super"].fillna("")
    df["A-Super"] = df["A-Super"].fillna("#N/D")

    print("========== FIN DEBUG SUPER ==========", flush=True)

    return df



@farmacia_bp.route("/", methods=["GET", "POST"])
def index():
    vigencia_farmacia_desde, vigencia_farmacia_hasta = obtener_vigencia_farmacia()
    vigencia_super_desde, vigencia_super_hasta = obtener_vigencia_super()
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
                    if col_costo:
                        df["Costo_tmp"] = df[col_costo]
                    if col_precio:
                        df["Precio_tmp"] = df[col_precio]

                    if col_costo_neto and col_costo:
                        df["Col3"] = np.where(
                            df[col_costo_neto].notna() & df[col_costo].notna(),
                            df[col_costo_neto] - df[col_costo],
                            np.nan
                        )
                    else:
                        df["Col3"] = np.nan
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
                    cols_a_borrar = [c for c in [col_costo, col_precio] if c]
                    df.drop(columns=cols_a_borrar, inplace=True, errors="ignore")

                    df.rename(columns={
                        "Costo_tmp": "Costo",
                        "Precio_tmp": "Precio"
                    }, inplace=True)

                else:
                    print("No se encontraron columnas clave")

                df = df.dropna(axis=1, how="all")

                df = df.loc[:, ~df.columns.str.contains("^Unnamed")]

                columnas_a_eliminar = [
                    "diferencia", "codebar", "Droga", "Precio Pami", "Cantidad", "Unidades",
                    "Activo", "Visible", "Tipo Bonif.", "Bonif.", "Tipo Bonif. Dif",
                    "Bonif Diferencial", "e-commerce", "Delivery", "Cod. en Proveedor",
                    "ABC", "Estacional", "Margen", "Etiqueta Electronica", "Tipo Bonif. Dif.", 
                    "Bonif. Diferencial", "Codebar","A-Farmacia","A-Super"
                ]

                df = df.drop(columns=columnas_a_eliminar, errors="ignore")

                orden_columnas = [
                    "Estado",
                    "Cod.Producto",
                    "Costo Neto",
                    "Precio Mi",
                    "Costo",
                    "Precio",
                    "Dif Cost",
                    "dif Precio",
                    "Troquel",
                    "F-Super",
                    "F-Farmacia",
                    "Producto",
                    "codebar1",
                    "IVA",
                    "laboratorio",
                    "Rubro",
                    "Sub Rubro"

                    ]

                orden_columnas_final = []

                for col_deseada in orden_columnas:
                    for col_real in df.columns:
                        if col_deseada.strip().lower() == str(col_real).strip().lower():
                            orden_columnas_final.append(col_real)
                            break

                columnas_restantes = [
                    col for col in df.columns
                    if col not in orden_columnas_final
                ]

                df = df[orden_columnas_final + columnas_restantes]

                df.to_excel(ARCHIVO_TEMP, index=False)

                preview = df.to_html(
                    classes="table table-striped table-hover table-bordered",
                    index=False
                )

            except Exception as e:
                error = f"Error procesando archivo: {e}"

    vigencia_farmacia_desde, vigencia_farmacia_hasta = obtener_vigencia_farmacia()
    vigencia_super_desde, vigencia_super_hasta = obtener_vigencia_super()

    return render_template(
        "farmacia.html",

        preview=preview,
        error=error,
        vigencia_farmacia_desde=vigencia_farmacia_desde,
        vigencia_farmacia_hasta=vigencia_farmacia_hasta,
        vigencia_super_desde=vigencia_super_desde,
        vigencia_super_hasta=vigencia_super_hasta
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
        df["F-Farmacia"] = ""
        df["A-Farmacia"] = "#N/D"
        return df

    debug_troquel_excel = (
        df[col_troquel]
        .astype(str)
        .str.strip()
        .str.replace(".0", "", regex=False)
        .str.lstrip("0")
        .replace({"": np.nan, "nan": np.nan, "None": np.nan})
    )

    #conn = get_db_connection()
    conn = get_db_connection(real_dict=False)

    try:
        consulta = """
            SELECT
                troquel,
                descripcion,
                promo
            FROM farmacia_folder
            WHERE tipo_cenefa = 'folder'
        """
        folder_df = pd.read_sql_query(consulta, conn)
    finally:
        conn.close()

    folder_df["troquel_match"] = (
        folder_df["troquel"]
        .astype(str)
        .str.strip()
        .str.replace(".0", "", regex=False)
        .str.lstrip("0")
        .replace({"": np.nan, "nan": np.nan, "None": np.nan})
    )

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

    df["F-Farmacia"] = troquel_match.map(mapa_descripcion)
    df["A-Farmacia"] = troquel_match.map(mapa_promo)

    df["F-Farmacia"] = df["F-Farmacia"].replace(
        {"": np.nan, "nan": np.nan, "None": np.nan}
    ).fillna("")

    df["A-Farmacia"] = df["A-Farmacia"].replace(
        {"": np.nan, "nan": np.nan, "None": np.nan}
    ).fillna("#N/D")


    return df



#===============================================
# Obtener vigencias de folder farmacias
#===============================================

def obtener_vigencia_farmacia():
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT
                MIN(fecha_desde) AS desde_min,
                MAX(fecha_hasta) AS hasta_max
            FROM farmacia_folder
            WHERE tipo_cenefa = 'folder'
              AND fecha_desde IS NOT NULL
              AND fecha_hasta IS NOT NULL
              AND fecha_desde <> 'fecha_desde'
              AND fecha_hasta <> 'fecha_hasta'
              AND fecha_desde <> ''
              AND fecha_hasta <> ''
        """)

        row = cur.fetchone()

        print("================================", flush=True)
        print("DEBUG VIGENCIA FARMACIA", flush=True)
        print("ROW:", row, flush=True)

    finally:
        cur.close()
        conn.close()

    if not row or not row["desde_min"] or not row["hasta_max"]:
        return "-", "-"

    return (
        pd.to_datetime(row["desde_min"]).strftime("%d/%m/%Y"),
        pd.to_datetime(row["hasta_max"]).strftime("%d/%m/%Y")
    )

def obtener_vigencia_farmacia():
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT
                MIN(fecha_desde) AS desde_min,
                MAX(fecha_hasta) AS hasta_max
            FROM farmacia_folder
            WHERE fecha_desde IS NOT NULL
              AND fecha_hasta IS NOT NULL
              AND fecha_desde <> 'fecha_desde'
              AND fecha_hasta <> 'fecha_hasta'
              AND fecha_desde <> ''
              AND fecha_hasta <> ''
        """)

        row = cur.fetchone()

        print("================================", flush=True)
        print("DEBUG VIGENCIA FARMACIA", flush=True)
        print("ROW:", row, flush=True)
        print("TIPO:", type(row), flush=True)

        if row:
            try:
                print("KEYS:", list(row.keys()), flush=True)
            except Exception as e:
                print("NO TIENE KEYS():", e, flush=True)

    finally:
        cur.close()
        conn.close()

    if not row:
        print("SIN RESULTADOS", flush=True)
        return "-", "-"

    try:
        desde = row["desde_min"]
        hasta = row["hasta_max"]
    except Exception as e:
        print("ERROR ACCEDIENDO POR NOMBRE:", e, flush=True)

        try:
            desde = row[0]
            hasta = row[1]
            print("ACCESO POR INDICE OK", flush=True)
        except Exception as e2:
            print("ERROR ACCEDIENDO POR INDICE:", e2, flush=True)
            return "-", "-"

    print("DESDE RAW:", desde, flush=True)
    print("HASTA RAW:", hasta, flush=True)

    if not desde or not hasta:
        print("DESDE/HASTA VACIOS", flush=True)
        return "-", "-"

    try:
        desde_fmt = pd.to_datetime(desde).strftime("%d/%m/%Y")
        hasta_fmt = pd.to_datetime(hasta).strftime("%d/%m/%Y")

        print("DESDE FORMATEADO:", desde_fmt, flush=True)
        print("HASTA FORMATEADO:", hasta_fmt, flush=True)

        return desde_fmt, hasta_fmt

    except Exception as e:
        print("ERROR FORMATEANDO FECHAS:", e, flush=True)
        return "-", "-"

#================================================================
# obtener vigencia super
#================================================================

def obtener_vigencia_super():
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT
                MIN(desde) AS desde_min,
                MAX(hasta) AS hasta_max
            FROM cenefas
            WHERE tipo_cenefa = 'minorista'
              AND desde IS NOT NULL
              AND hasta IS NOT NULL
              AND desde <> 'desde'
              AND hasta <> 'hasta'
              AND desde <> ''
              AND hasta <> ''
            """
        )

        row = cur.fetchone()

    finally:
        cur.close()
        conn.close()

    if not row:
        return "-", "-"

    try:
        desde = row["desde_min"]
        hasta = row["hasta_max"]
    except (TypeError, KeyError):
        desde = row[0]
        hasta = row[1]

    if not desde or not hasta:
        return "-", "-"

    try:
        return (
            pd.to_datetime(desde).strftime("%d/%m/%Y"),
            pd.to_datetime(hasta).strftime("%d/%m/%Y"),
        )

    except Exception as error:
        print(
            "ERROR FORMATEANDO VIGENCIA SUPER:",
            repr(error),
            flush=True,
        )

        return "-", "-"


@farmacia_bp.route("/informes-uso")
def informes_uso_farmacia():

    #conn = get_db_connection()
    conn = get_db_connection(real_dict=False)

    try:
        query = """
            SELECT
                session_id AS Sesion,
                ip AS IP,
                ruta AS Pantalla,
                metodo AS Metodo,
                fecha_ingreso AS Ingreso,
                ultima_actividad AS Ultima_Actividad,
                ROUND(duracion_segundos / 60.0, 2) AS Minutos,
                user_agent AS Navegador
            FROM farmacia_metricas
            ORDER BY ultima_actividad DESC
        """

        df = pd.read_sql_query(query, conn)

    finally:
        conn.close()

    tabla = df.to_html(
        classes="table table-striped table-hover table-bordered",
        index=False
    )

    return render_template(
        "farmacia/informes_uso.html",
        tabla=tabla
    )



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