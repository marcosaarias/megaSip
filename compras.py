import os
import pandas as pd
import numpy as np
import unicodedata
from flask import Blueprint, render_template, request, session, redirect, url_for
from sistemas import login_requerido
from logs import guardar_log_compras
from datetime import datetime
from datetime import timedelta
import uuid
import traceback
import sqlite3
import redis
import json
from io import StringIO
import re
import unicodedata

SUCURSAL_MAP = {
    "Total Empresa": "CO01,CO02,CO04,CO05,CO06,CO07,CO08,CO09,CO10,CO11,CO12,CO14,CO15,CO16,CO17,CO18,CO19,CO20,CO21,CO22,CO23,CO24,CO25,CO26,CO27,CO28,CO29,MA02",
    "Total Empresa - Mayorista": "CO05,CO09,CO12,CO15,CO21,CO29,MA02",
    "Jujuy - Mayorista": "CO05,CO12,CO15,MA02",
    "Salta - Mayorista": "CO09,CO29,CO21",
    "Oran - Mayorista": "CO21",
    "Total Empresa Minorista": "CO01,CO02,CO04,CO06,CO07,CO08,CO10,CO11,CO14,CO16,CO17,CO18,CO19,CO20,CO22,CO23,CO24,CO25,CO26,CO27,CO28",
    "Jujuy - Minoristas": "CO01,CO02,CO04,CO06,CO07,CO08,CO10,CO11,CO14,CO16,CO17,CO19,CO20,CO22,CO28",
    "Salta - Minoristas": "CO18,CO23",
    "Jujuy, Salta - Minoritas": "CO01,CO02,CO04,CO06,CO07,CO08,CO10,CO11,CO14,CO16,CO17,CO18,CO19,CO20,CO22,CO23,CO28",
    "Jujuy, Salta - Minoritas y Mayoristas": "CO01,CO02,CO04,CO05,CO06,CO07,CO08,CO09,CO10,CO11,CO12,CO14,CO15,CO16,CO17,CO18,CO19,CO20,CO21,CO22,CO23,CO28,CO29,MA02",
    "Jujuy - Minorista Y Mayorista": "CO01,CO02,CO04,CO05,CO06,CO07,CO08,CO10,CO11,CO12,CO14,CO15,CO16,CO17,CO19,CO20,CO22,CO28,MA02",
    "Tucuman": "CO24,CO25,CO26,CO27",
    "Jujuy Capital": "CO01,CO02,CO05,CO07,CO11,CO16,CO19,CO20,CO22"
}


# ---------------- REDIS ----------------

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=6379,
    db=0,
    decode_responses=True
)

def guardar_temporal(lote_id, df):
    redis_client.setex(
        lote_id,
        3600,  # expira en 1 hora
        df.to_json(orient="records")
    )

def recuperar_temporal(lote_id):
    data = redis_client.get(lote_id)
    if data:
        return pd.read_json(data, orient="records")
    return None



DB_PATH = os.path.join(os.path.dirname(__file__), "sip.s3db")

compras_bp = Blueprint("compras", __name__, url_prefix="/compras")
RUTA_MATERIAL = "/mnt/excel/ARCHIVOS IMPORTANTES/Base de datos completa.xlsx"
HEADERS = ["CODIGO", "ean", "DESCRIPCION", "Normal", "Oferta", "cenefa", "desde", "hasta", "sucursales", "CÓD. SUCURSALES"]

ALIAS = {
    "CODIGO": ["CODIGO", "codigo", "id", "cod", "material", "mat", "Cód.", "CODGO"],
    "ean": ["ean", "codigo ean"],
    "DESCRIPCION": ["descripcion", "DESCRIPCION", "Descripción", "Descrip", "nombre", "texto breve de material", "Texto breve de material"],
    "Normal": ["normal", "precio normal", "precio unitario", "Precio", "PVN", "pvn", "Nrmal"],
    "Oferta": ["oferta", "promo", "Ofrta"],
    "cenefa": ["cenefa", "cenefas", "Cenefas"],
    "desde": ["desde", "inicio"],
    "hasta": ["hasta", "fin"],
    "sucursales": ["sucursales", "tiendas"],
    "CÓD. SUCURSALES": ["codigos sucursales", "cod sucursales", "sucursales codigos"],
}

SUCURSAL_MAP = {
    "minorista": {
        "Total-empresa-minorista": "CO01,CO02,CO04,CO06,CO07,CO08,CO10,CO11,CO14,CO16,CO17,CO18,CO19,CO20,CO22,CO23,CO24,CO25,CO26,CO27,CO28",
        "tucuman": "CO24,CO25,CO26,CO27",
        "jujuy": "CO01,CO02,CO04,CO06,CO07,CO08,CO10,CO11,CO14,CO16,CO17,CO19,CO20,CO22,CO28",
        "salta": "CO18,CO23"
    },
    "mayorista": {
        "Total Empresa - Mayorista": "CO05,CO09,CO12,CO15,CO21,CO29,MA02",
        "jujuy": "CO05,CO12,CO15,MA02",
        "salta": "CO09,CO29,CO21",
        "oran": "CO21"
    }
}

# ---------------- EAN MAP ----------------

def cargar_material_map():
    try:
        material_df = pd.read_excel(
            RUTA_MATERIAL,
            sheet_name="Hoja2",
            dtype=str,
            header=1
        )

        material_df.columns = material_df.columns.str.strip().str.lower()

        material_df["material"] = (
            material_df["material"]
            .astype(str)
            .str.strip()
            .str.lstrip("0")
        )

        material_df["scaner"] = (
            material_df["scaner"]
            .astype(str)
            .str.strip()
        )

        material_df.dropna(subset=["material", "scaner"], inplace=True)

        return dict(zip(material_df["material"], material_df["scaner"]))

    except Exception as e:
        print("Error cargando archivo EAN:", e)
        return {}

MATERIAL_MAP = cargar_material_map()

#def completar_ean(df):
#    if "CODIGO" not in df.columns:
#        return df
#    codigos_str = (
#        pd.to_numeric(df["CODIGO"], errors="coerce")
#        .fillna(0)
#        .astype(int)
#        .astype(str)
#    )
#    material_map_normalized = {
#        str(int(float(k))) if str(k).replace(".", "", 1).isdigit()
#        else str(k).strip(): v
#        for k, v in MATERIAL_MAP.items()
#    }
#    mapped = codigos_str.map(material_map_normalized).fillna("")
#    if "ean" not in df.columns:
#        df.insert(1, "ean", mapped)
#    else:
#        df["ean"] = df["ean"].replace(["nan", "NaN", "None"], "")
#        df["ean"] = df["ean"].fillna(mapped)
#    return df


def completar_ean(df):
    if "CODIGO" not in df.columns:
        return df

    codigos_str = (
        df["CODIGO"]
        .astype(str)
        .str.strip()
        .str.replace(".0", "", regex=False)
        .str.lstrip("0")
    )

    material_map_normalized = {}

    for k, v in MATERIAL_MAP.items():
        try:
            key = str(int(float(str(k).strip())))
        except:
            key = str(k).strip()

        material_map_normalized[key.lstrip("0")] = v

    mapped = codigos_str.map(material_map_normalized).fillna("")

    if "EAN" in df.columns:
        df["EAN"] = df["EAN"].replace("", mapped).fillna(mapped)
    else:
        df.insert(df.columns.get_loc("CODIGO") + 1, "EAN", mapped)

    return df

# ---------------- UTIL ----------------

def normalizar_texto(texto):
    if not texto:
        return ""
    texto = str(texto).strip().lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = texto.encode("ascii", "ignore").decode("utf-8")
    return texto

# ---------------- PROCESAMIENTO COMUN ----------------
"""
def procesar_archivo_cenefas(archivo, tipo, fecha_desde, fecha_hasta):
    preview = None
    mensaje_error = None
    total_registros = 0
    df = None

    if archivo and archivo.filename != "":

        df_temp = pd.read_excel(archivo, header=None)

        fila_header = None
        for i, row in df_temp.iterrows():
            valores = [normalizar_texto(x) for x in row.values]
            if "codigo" in valores:
                fila_header = i
                break

        if fila_header is None:
            mensaje_error = "No se encontró la fila de encabezados (CODIGO)."
            return None, None, mensaje_error, 0

        archivo.seek(0)
        df = pd.read_excel(archivo, header=fila_header)

        df.columns = [normalizar_texto(col).strip() for col in df.columns]

        column_mapping = {}

        for header in HEADERS:
            header_norm = normalizar_texto(header)
            posibles = ALIAS.get(header, [])
            posibles_norm = [normalizar_texto(p) for p in posibles]

            for col in df.columns:
                if col == header_norm or col in posibles_norm:
                    column_mapping[col] = header
                    break

        if not column_mapping:
            mensaje_error = "No se encontraron columnas válidas."
            return None, None, mensaje_error, 0

        df = df.rename(columns=column_mapping)

        if tipo in SUCURSAL_MAP:
            clave_total = (
                "Total Empresa - Mayorista"
                if tipo == "mayorista"
                else "Total-empresa-minorista"
            )

            if "sucursales" not in df.columns:
                df["sucursales"] = ""

            def generar_codigos(valor):
                if pd.isna(valor) or str(valor).strip() == "":
                    return SUCURSAL_MAP[tipo].get(clave_total, "")

                provincia = normalizar_texto(valor)

                return SUCURSAL_MAP[tipo].get(
                    provincia,
                    SUCURSAL_MAP[tipo].get(clave_total, "")
                )

            df["sucursales"] = df["sucursales"].apply(generar_codigos)

        columnas_validas = [col for col in df.columns if col in HEADERS]
        df = df[columnas_validas]

        df = df.replace(r'^\s*$', pd.NA, regex=True)
        df = df.dropna(how="all")

        if "CODIGO" in df.columns:
            df["CODIGO"] = pd.to_numeric(df["CODIGO"], errors="coerce")
            df = df.dropna(subset=["CODIGO"])
            df["CODIGO"] = df["CODIGO"].astype(int)

        df = completar_ean(df)

        if "ean" in df.columns:
            df.rename(columns={"ean": "EAN"}, inplace=True)

        columnas = list(df.columns)
        if "CODIGO" in columnas and "EAN" in columnas:
            columnas.remove("EAN")
            index_codigo = columnas.index("CODIGO")
            columnas.insert(index_codigo + 1, "EAN")
            df = df[columnas]

        if "Oferta" in df.columns:
            df["Oferta"] = pd.to_numeric(df["Oferta"], errors="coerce")
            df["Oferta"] = np.floor(df["Oferta"] * 100) / 100

        if "Normal" in df.columns:
            df["Normal"] = pd.to_numeric(df["Normal"], errors="coerce")
            df["Normal"] = np.floor(df["Normal"] * 100) / 100

        if fecha_desde:
            df["Desde"] = fecha_desde

        if fecha_hasta:
            df["Hasta"] = fecha_hasta

        df = df.reset_index(drop=True)
        total_registros = len(df)
        df = df.fillna("")

        preview = df.to_html(
            classes="table table-striped table-bordered",
            index=False
        )

    return df, preview, mensaje_error, total_registros
"""

def procesar_archivo_cenefas(archivo, tipo, fecha_desde, fecha_hasta):
    preview = None
    mensaje_error = None
    total_registros = 0
    df = None

    if archivo and archivo.filename != "":

        excel_file = pd.ExcelFile(archivo)

        hoja_objetivo = None
        for hoja in excel_file.sheet_names:
            if normalizar_texto(hoja).strip() in ["cenefa", "cenefas"]:
                hoja_objetivo = hoja
                break

        if hoja_objetivo is None:
            mensaje_error = "No se encontró la hoja 'Cenefas'."
            return None, None, mensaje_error, 0

        df_temp = pd.read_excel(excel_file, sheet_name=hoja_objetivo, header=None)

        fila_header = None
        for i, row in df_temp.iterrows():
            valores = [normalizar_texto(x) for x in row.values]
            if "codigo" in valores:
                fila_header = i
                break

        if fila_header is None:
            mensaje_error = "No se encontró la fila de encabezados (CODIGO)."
            return None, None, mensaje_error, 0

        df = pd.read_excel(excel_file, sheet_name=hoja_objetivo, header=fila_header)

        df.columns = [normalizar_texto(col).strip() for col in df.columns]

        column_mapping = {}

        for header in HEADERS:
            header_norm = normalizar_texto(header)
            posibles = ALIAS.get(header, [])
            posibles_norm = [normalizar_texto(p) for p in posibles]

            for col in df.columns:
                if col == header_norm or col in posibles_norm:
                    column_mapping[col] = header
                    break

        if not column_mapping:
            mensaje_error = "No se encontraron columnas válidas."
            return None, None, mensaje_error, 0

        df = df.rename(columns=column_mapping)

        if tipo in SUCURSAL_MAP:
            clave_total = (
                "Total Empresa - Mayorista"
                if tipo == "mayorista"
                else "Total-empresa-minorista"
            )

            if "sucursales" not in df.columns:
                df["sucursales"] = ""

            def generar_codigos(valor):
                if pd.isna(valor) or str(valor).strip() == "":
                    return SUCURSAL_MAP[tipo].get(clave_total, "")

                provincia = normalizar_texto(valor)

                return SUCURSAL_MAP[tipo].get(
                    provincia,
                    SUCURSAL_MAP[tipo].get(clave_total, "")
                )


        columnas_validas = [col for col in df.columns if col in HEADERS]
        df = df[columnas_validas]

        df = df.replace(r'^\s*$', pd.NA, regex=True)
        df = df.dropna(how="all")

        if "CODIGO" in df.columns:
            df["CODIGO"] = pd.to_numeric(df["CODIGO"], errors="coerce")
            df = df.dropna(subset=["CODIGO"])
            df["CODIGO"] = df["CODIGO"].astype(int)

        df = completar_ean(df)

        if "ean" in df.columns:
            df.rename(columns={"ean": "EAN"}, inplace=True)

        columnas = list(df.columns)
        if "CODIGO" in columnas and "EAN" in columnas:
            columnas.remove("EAN")
            index_codigo = columnas.index("CODIGO")
            columnas.insert(index_codigo + 1, "EAN")
            df = df[columnas]

        if "Oferta" in df.columns:
            df["Oferta"] = pd.to_numeric(df["Oferta"], errors="coerce")
            df["Oferta"] = np.floor(df["Oferta"] * 100) / 100

        if "Normal" in df.columns:
            df["Normal"] = pd.to_numeric(df["Normal"], errors="coerce")
            df["Normal"] = np.floor(df["Normal"] * 100) / 100

        if fecha_desde:
            df["Desde"] = fecha_desde

        if fecha_hasta:
            df["Hasta"] = fecha_hasta

        df = df.reset_index(drop=True)
        total_registros = len(df)
        df = df.fillna("")

        preview = df.to_html(
            classes="table table-striped table-bordered",
            index=False
        )

    return df, preview, mensaje_error, total_registros

def guardar_cenefas_en_db(df, tipo_cenefa, usuario="sistema", lote_carga=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if lote_carga is None:
        lote_carga = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + str(uuid.uuid4())[:8]

    fecha_carga = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for _, row in df.iterrows():
        cursor.execute("""
            INSERT INTO cenefas
            (
                Codigo, ean, descripcion, Normal, Oferta, cenefa,
                desde, hasta, sucursales, tipo_cenefa,
                fecha_carga, lote_carga, usuario_carga
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row.get("CODIGO"),
            row.get("EAN"),
            row.get("DESCRIPCION"),
            row.get("Normal"),
            row.get("Oferta"),
            row.get("cenefa"),
            row.get("Desde"),
            row.get("Hasta"),
            row.get("sucursales"),
            tipo_cenefa,
            fecha_carga,
            lote_carga,
            usuario
        ))

    conn.commit()
    conn.close()

    return lote_carga, fecha_carga




# ---------------- ROUTES ----------------

@compras_bp.route("/")
def dashboard():
    return render_template("compras.html")

@compras_bp.route("/folder", methods=["GET", "POST"])
def folder():
    preview = None
    tipo = None
    mensaje_error = None
    total_registros = 0
    fecha_desde = None
    fecha_hasta = None

    if request.method == "POST":
        archivo = request.files.get("archivo")
        tipo = request.form.get("tipo")
        fecha_desde = request.form.get("fecha_desde")
        fecha_hasta = request.form.get("fecha_hasta")
        usuario = session.get("usuario_nombre", "desconocido")

        try:
            df, preview, mensaje_error, total_registros = procesar_archivo_cenefas(
                archivo=archivo,
                tipo=tipo,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta
            )

            if df is not None:
                #guardar_cenefas_en_db(df, "folder")
                usuario = session.get("usuario_nombre", "desconocido")
                lote_carga, fecha_carga = guardar_cenefas_en_db(df, "folder", usuario=usuario)

                guardar_log_compras(
                    usuario=usuario,
                    nivel="INFO",
                    origen="backend",
                    modulo="folder",
                    accion="Carga de folder",
                    archivo=archivo.filename if archivo else None,
                    detalle="Archivo procesado y guardado correctamente",
                    estado="exitoso",
                    total_registros=total_registros
                )
            else:
                guardar_log_compras(
                    usuario=usuario,
                    nivel="ERROR",
                    origen="validacion",
                    modulo="folder",
                    accion="Error carga folder",
                    archivo=archivo.filename if archivo else None,
                    detalle=mensaje_error or "No se pudo procesar el archivo",
                    estado="fallido",
                    total_registros=0
                )

        except sqlite3.Error as e:
            mensaje_error = f"Error de base de datos: {e}"

            guardar_log_compras(
                usuario=usuario,
                nivel="CRITICAL",
                origen="base_datos",
                modulo="folder",
                accion="Error guardando folder",
                archivo=archivo.filename if archivo else None,
                detalle=str(e),
                estado="fallido",
                total_registros=0,
                error_trace=traceback.format_exc()
            )

        except Exception as e:
            mensaje_error = f"Error de backend: {e}"

            guardar_log_compras(
                usuario=usuario,
                nivel="ERROR",
                origen="backend",
                modulo="folder",
                accion="Excepción en folder",
                archivo=archivo.filename if archivo else None,
                detalle=str(e),
                estado="fallido",
                total_registros=0,
                error_trace=traceback.format_exc()
            )

    return render_template(
        "folder.html",
        preview=preview,
        tipo=tipo,
        mensaje_error=mensaje_error,
        total_registros=total_registros,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta
    )

@compras_bp.route("/cenefas", methods=["GET", "POST"])
def cenefas():
    tipo = request.args.get("tipo", "folder")
    return render_template(
        "cenefas.html",
        tipo=tipo
    )

@compras_bp.route("/ofertas/<modo>", methods=["GET", "POST"])
def ofertas(modo):
    modos_validos = {
        "competencia": "Oferta por Competencia",
        "interna": "Oferta Interna",
        "vencimientos": "Oferta por Vencimientos"
    }

    if modo not in modos_validos:
        return "Modo no válido", 404

    preview = None
    mensaje_error = None
    total_registros = 0
    fecha_desde = None
    fecha_hasta = None
    tipo = "mayorista"

    if request.method == "POST":
        archivo = request.files.get("archivo")
        fecha_desde = request.form.get("fecha_desde")
        fecha_hasta = request.form.get("fecha_hasta")
        tipo = request.form.get("tipo", "mayorista")

        df, preview, mensaje_error, total_registros = procesar_archivo_cenefas(
            archivo=archivo,
            tipo=tipo,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta
        )

        if df is not None:
                lote_id = str(uuid.uuid4())

                guardar_temporal(lote_id, df)

                session["ofertas_lote_id"] = lote_id
                session["ofertas_preview_modo"] = modo
                session["ofertas_preview_tipo"] = tipo
                session["ofertas_preview_fecha_desde"] = fecha_desde
                session["ofertas_preview_fecha_hasta"] = fecha_hasta

    return render_template(
        "ofertas.html",
        modo=modo,
        titulo_vista=modos_validos[modo],
        preview=preview,
        tipo=tipo,
        mensaje_error=mensaje_error,
        total_registros=total_registros,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta
    )

@compras_bp.route("/transmitir_ofertas", methods=["POST"])
def transmitir_ofertas():
    lote_id = session.get("ofertas_lote_id")
    df = recuperar_temporal(lote_id)
    modo = session.get("ofertas_preview_modo")
    tipo = session.get("ofertas_preview_tipo", "mayorista")
    fecha_desde = session.get("ofertas_preview_fecha_desde")
    fecha_hasta = session.get("ofertas_preview_fecha_hasta")
    usuario = session.get("usuario_nombre", "desconocido")

    modos_validos = {
        "competencia": "Oferta por Competencia",
        "interna": "Oferta Interna",
        "vencimientos": "Oferta por Vencimientos"
    }

    if not lote_id or df is None or not modo:
        guardar_log_compras(
            usuario=usuario,
            nivel="ERROR",
            origen="validacion",
            modulo="transmitir",
            accion="Transmitir ofertas",
            detalle="No hay datos para transmitir",
            estado="fallido",
            total_registros=0
        )
        return "No hay datos para transmitir.", 400

    try:
        #if df is None:
        #    return "Los datos ya no están disponibles. Volvé a cargar el archivo.", 400

        usuario = session.get("usuario_nombre", "desconocido")
        lote_carga, fecha_carga = guardar_cenefas_en_db(df, modo, usuario=usuario)
        redis_client.delete(lote_id) 
        guardar_log_compras(
            usuario=usuario,
            nivel="INFO",
            origen="backend",
            modulo="transmitir",
            accion="Transmitir ofertas",
            detalle="Datos transmitidos correctamente",
            estado="exitoso",
            total_registros=len(df)
        )

        session.pop("ofertas_preview_data", None)
        session.pop("ofertas_preview_modo", None)
        session.pop("ofertas_preview_tipo", None)
        session.pop("ofertas_preview_fecha_desde", None)
        session.pop("ofertas_preview_fecha_hasta", None)

        return render_template(
            "ofertas.html",
            modo=modo,
            titulo_vista=modos_validos.get(modo, "Ofertas"),
            preview="<div class='alert alert-success'>Datos transmitidos correctamente.</div>",
            tipo=tipo,
            mensaje_error=None,
            total_registros=0,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta
        )

    except sqlite3.Error as e:
        guardar_log_compras(
            usuario=usuario,
            nivel="CRITICAL",
            origen="base_datos",
            modulo="transmitir",
            accion="Error transmitiendo ofertas",
            detalle=str(e),
            estado="fallido",
            total_registros=0,
            error_trace=traceback.format_exc()
        )
        return f"Error de base de datos: {e}", 500

    except Exception as e:
        guardar_log_compras(
            usuario=usuario,
            nivel="ERROR",
            origen="backend",
            modulo="transmitir",
            accion="Excepción transmitiendo ofertas",
            detalle=str(e),
            estado="fallido",
            total_registros=0,
            error_trace=traceback.format_exc()
        )
        return f"Error interno: {e}", 500


@compras_bp.route("/sucursal")
@login_requerido("sucursal")
def sucursal():
    from datetime import datetime

    def convertir_fecha(valor):
        if not valor:
            return None

        valor = str(valor).strip()

        for formato in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(valor, formato).date()
            except:
                pass

        return None
        
    def formatear_fecha(valor):
        fecha = convertir_fecha(valor)
        if not fecha:
            return ""
        return fecha.strftime("%d/%m/%Y")

    sucursal_codigo = session.get("usuario_nombre", "").strip().upper()
    tipo = request.args.get("tipo", "folder")
    #hoy = datetime.now().date()
    hoy = datetime.now().date() + timedelta(days=2)

    print("DEBUG sucursal usuario:", sucursal_codigo)
    print("DEBUG fecha hoy:", hoy)
    print("DEBUG tipo solicitado:", tipo)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT Codigo, ean, descripcion, Normal, Oferta, cenefa,
               desde, hasta, sucursales, tipo_cenefa,
               fecha_carga, lote_carga, usuario_carga
        FROM cenefas
        WHERE tipo_cenefa = ?
        ORDER BY fecha_carga DESC, desde DESC
    """, (tipo,))

    rows = cursor.fetchall()
    conn.close()

    filtradas = []

    for r in rows:
        sucursales = str(r[8]).upper().replace(" ", "")
        lista_suc = [s.strip() for s in sucursales.split(",")]

        print("DEBUG sucursales registro:", lista_suc)

        desde = convertir_fecha(r[6])
        hasta = convertir_fecha(r[7])

        if not desde or not hasta:
            print("ERROR fecha:", r[6], r[7])
            continue

        print("DEBUG desde:", desde, "hasta:", hasta)

        if sucursal_codigo in lista_suc and desde <= hoy <= hasta:
            filtradas.append({
                "Codigo": r[0],
                "ean": r[1],
                "descripcion": r[2],
                "Normal": r[3],
                "Oferta": r[4],
                "cenefa": r[5],
                #"desde": r[6],
                #"hasta": r[7],
                "desde": formatear_fecha(r[6]),
                "hasta": formatear_fecha(r[7]),
                "sucursales": r[8],
                "tipo_cenefa": r[9],
                "fecha_carga": r[10],
                "lote_carga": r[11],
                "usuario_carga": r[12],
                "es_nueva": False
            })

    lote_mas_reciente = None
    ultima_fecha_carga = None
    ultimo_usuario_carga = None

    if filtradas:
        ordenadas_por_carga = sorted(
            [x for x in filtradas if x["fecha_carga"]],
            key=lambda x: x["fecha_carga"],
            reverse=True
        )

        if ordenadas_por_carga:
            lote_mas_reciente = ordenadas_por_carga[0]["lote_carga"]
            ultima_fecha_carga = ordenadas_por_carga[0]["fecha_carga"]
            ultimo_usuario_carga = ordenadas_por_carga[0]["usuario_carga"]

        for item in filtradas:
            if item["lote_carga"] == lote_mas_reciente:
                item["es_nueva"] = True

    print("DEBUG registros vigentes encontrados:", len(filtradas))
    print("DEBUG lote más reciente:", lote_mas_reciente)

    return render_template(
        "sucursales.html",
        datos=filtradas,
        tipo=tipo,
        ultima_fecha_carga=ultima_fecha_carga,
        ultimo_usuario_carga=ultimo_usuario_carga
    )


    # --------------- FARMACIA --------------


@compras_bp.route("/farmacia_folder", methods=["GET", "POST"])
@login_requerido("farmacia")
def farmacia_folder():
    preview = None
    mensaje_error = None
    total_registros = 0
    fecha_desde = None
    fecha_hasta = None

    if request.method == "POST":
        archivo = request.files.get("archivo")
        fecha_desde = request.form.get("fecha_desde")
        fecha_hasta = request.form.get("fecha_hasta")

        df, preview, mensaje_error, total_registros = procesar_archivo_cenefas(
            archivo=archivo,
            tipo=None,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta
        )

        if df is not None:
            # Farmacia no usa mayorista/minorista, así que no toca sucursales por mapa
            if "sucursales" not in df.columns:
                df["sucursales"] = ""

            guardar_cenefas_en_db(df, "farmacia")

    return render_template(
        "farmacia_folder.html",
        preview=preview,
        mensaje_error=mensaje_error,
        total_registros=total_registros,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta
    )



# Historial cenefas

@compras_bp.route("/historico")
@login_requerido("sucursal")
def historico_cenefas():
    filtro_codigo = request.args.get("codigo", "").strip()
    filtro_tipo = request.args.get("tipo", "").strip()
    filtro_lote = request.args.get("lote", "").strip()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
        SELECT id, Codigo, ean, descripcion, Normal, Oferta, cenefa,
               desde, hasta, sucursales, tipo_cenefa,
               fecha_carga, lote_carga, usuario_carga
        FROM cenefas
        WHERE 1=1
    """
    params = []

    if filtro_codigo:
        query += " AND Codigo LIKE ?"
        params.append(f"%{filtro_codigo}%")

    if filtro_tipo:
        query += " AND tipo_cenefa = ?"
        params.append(filtro_tipo)

    if filtro_lote:
        query += " AND lote_carga LIKE ?"
        params.append(f"%{filtro_lote}%")

    query += " ORDER BY fecha_carga DESC, id DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    datos = []
    for r in rows:
        datos.append({
            "id": r["id"],
            "Codigo": r["Codigo"],
            "ean": r["ean"],
            "descripcion": r["descripcion"],
            "Normal": r["Normal"],
            "Oferta": r["Oferta"],
            "cenefa": r["cenefa"],
            "desde": r["desde"],
            "hasta": r["hasta"],
            "sucursales": r["sucursales"],
            "tipo_cenefa": r["tipo_cenefa"],
            "fecha_carga": r["fecha_carga"],
            "lote_carga": r["lote_carga"],
            "usuario_carga": r["usuario_carga"],
        })

    return render_template(
        "historico_cenefas.html",
        datos=datos,
        filtro_codigo=filtro_codigo,
        filtro_tipo=filtro_tipo,
        filtro_lote=filtro_lote
    )

#====================================
# DIARIOS
#====================================

def formatear_moneda(valor):
    """Convierte 17999.0 a 17.999,00"""
    try:
        if valor == "" or pd.isna(valor):
            return ""
        num_formateado = "{:,.2f}".format(float(valor))
        return num_formateado.replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return valor


def normalizar_sucursales(valor, nombre_hoja):
    if not valor or str(valor).strip() == "":
        return detectar_sucursales(nombre_hoja)

    valor_str = str(valor).strip()

    # 🔹 si ya son códigos → respetar
    if re.search(r"\b(CO\d+|MA\d+)\b", valor_str):
        return valor_str

    texto = normalizar_texto(valor_str)

    es_mayorista = "mayorista" in texto
    es_minorista = "minorista" in texto

    regiones = []
    if "jujuy" in texto:
        regiones.append("jujuy")
    if "salta" in texto:
        regiones.append("salta")
    if "oran" in texto:
        regiones.append("oran")
    if "tucuman" in texto:
        regiones.append("tucuman")

    resultado = []

    for region in regiones:

        # 🔹 TUCUMAN → siempre minorista
        if region == "tucuman":
            resultado.append("CO24,CO25,CO26,CO27")
            continue

        # 🔹 ORAN → mayorista
        if region == "oran":
            resultado.append("CO21")
            continue

        # 🔹 MAYORISTA
        if es_mayorista and not es_minorista:
            if region == "jujuy":
                resultado.append("CO05,CO12,CO15,MA02")
            elif region == "salta":
                resultado.append("CO09,CO29,CO21")

        # 🔹 MINORISTA
        elif es_minorista and not es_mayorista:
            if region == "jujuy":
                resultado.append("CO01,CO02,CO04,CO06,CO07,CO08,CO10,CO11,CO14,CO16,CO17,CO19,CO20,CO22,CO28")
            elif region == "salta":
                resultado.append("CO18,CO23")

        # 🔥 SIN ESPECIFICAR → AMBOS (TU REGLA)
        else:
            if region == "jujuy":
                resultado.append("CO01,CO02,CO04,CO05,CO06,CO07,CO08,CO10,CO11,CO12,CO14,CO15,CO16,CO17,CO19,CO20,CO22,CO28,MA02")
            elif region == "salta":
                resultado.append("CO18,CO23,CO09,CO29,CO21")

    # 🔥 combinar y limpiar duplicados
    if resultado:
        codigos = ",".join(resultado).split(",")
        codigos_unicos = sorted(set(c.strip() for c in codigos if c.strip()))
        return ",".join(codigos_unicos)

    # 🔹 fallback
    return detectar_sucursales(nombre_hoja)



SUCURSAL_MAP_DIARIO = {
    "jujuy_minorista": "CO01,CO02,CO04,CO06,CO07,CO08,CO10,CO11,CO14,CO16,CO17,CO19,CO20,CO22,CO28",
    "jujuy_mayorista": "CO05,CO12,CO15,MA02",
    "salta": "CO18,CO23",
    "salta_mayorista": "CO09,CO29,CO21",
    "tucuman": "CO24,CO25,CO26,CO27"
}

def detectar_sucursales(nombre_hoja):
    hoja = normalizar_texto(nombre_hoja)

    if "jujuy mayorista" in hoja:
        return SUCURSAL_MAP_DIARIO["jujuy_mayorista"]

    elif "jujuy" in hoja:
        return SUCURSAL_MAP_DIARIO["jujuy_minorista"]

    elif "salta mayorista" in hoja:
        return SUCURSAL_MAP_DIARIO["salta_mayorista"]

    elif "salta" in hoja:
        return SUCURSAL_MAP_DIARIO["salta"]

    elif "tucuman" in hoja:
        return SUCURSAL_MAP_DIARIO["tucuman"]

    return ""

    return ",".join([p for p in partes if p])


@compras_bp.route("/diario", methods=["GET", "POST"])
def diario():
    import uuid

    preview = {}
    total_registros = {}
    hojas_orden = []
    cache_id = None

    HEADERS_DIARIO = [
        "CODIGO", "DESCRIPCION", "EAN",
        "Normal", "Oferta",
        "desde", "hasta",
        "sucursales", "cenefa"
    ]

    if request.method == "POST":
        archivo = request.files.get("archivo")

        fecha_desde_raw = request.form.get("fecha_desde")
        fecha_hasta_raw = request.form.get("fecha_hasta")

        if archivo:
            try:
                cache_id = str(uuid.uuid4())

                f_desde = pd.to_datetime(fecha_desde_raw).strftime('%d/%m/%Y') if fecha_desde_raw else ""
                f_hasta = pd.to_datetime(fecha_hasta_raw).strftime('%d/%m/%Y') if fecha_hasta_raw else ""

                xls = pd.read_excel(archivo, sheet_name=None)

                for nombre_hoja, df in xls.items():

                    # 🔹 descartar hojas vacías
                    df_check = df.replace(r'^\s*$', pd.NA, regex=True)
                    if df_check.dropna(how="all").empty:
                        continue

                    # 🔹 normalizar columnas
                    df.columns = [normalizar_texto(col).strip() for col in df.columns]

                    # 🔹 mapear columnas con ALIAS
                    column_mapping = {}

                    for header in HEADERS_DIARIO:
                        header_norm = normalizar_texto(header)
                        posibles = ALIAS.get(header, [])
                        posibles_norm = [normalizar_texto(p) for p in posibles]

                        for col in df.columns:
                            if col == header_norm or col in posibles_norm:
                                column_mapping[col] = header
                                break

                    if not column_mapping:
                        continue

                    df = df.rename(columns=column_mapping)

                    # 🔹 limpiar CODIGO
                    if "CODIGO" in df.columns:
                        df["CODIGO"] = (
                            df["CODIGO"]
                            .astype(str)
                            .str.strip()
                            .str.replace(".0", "", regex=False)
                            .str.lstrip("0")
                        )

                    df = completar_ean(df)

                    # 🔹 fechas
                    df["desde"] = f_desde
                    df["hasta"] = f_hasta

                    # 🔹 sucursales
                    if "sucursales" not in df.columns:
                        df["sucursales"] = detectar_sucursales(nombre_hoja)
                    else:
                        df["sucursales"] = df["sucursales"].apply(
                            lambda x: normalizar_sucursales(x, nombre_hoja)
                        )

                    # 🔹 limpiar filas vacías
                    df = df.replace(r'^\s*$', pd.NA, regex=True).dropna(how="all")

                    if "cenefa" in df.columns:
                        
                        df = df[df["cenefa"].notna()]
                        df["cenefa"] = df["cenefa"].str.strip()
                        df = df[
                            (df["cenefa"] != "") &
                            (~df["cenefa"].str.lower().str.contains("ya esta activo", na=False))
                        ]

                    if df.empty:
                        continue

                    # 🔹 recortar columnas (solo una vez)
                    columnas_validas = [col for col in HEADERS_DIARIO if col in df.columns]
                    df = df[columnas_validas]

                    # 🔹 validar CODIGO numérico
                    if "CODIGO" in df.columns:
                        df["CODIGO"] = pd.to_numeric(df["CODIGO"], errors="coerce")
                        df = df.dropna(subset=["CODIGO"])
                        df["CODIGO"] = df["CODIGO"].astype(int)

                    df = df.fillna("")

                    # 🔹 formatear precios
                    for col in ["Normal", "Oferta"]:
                        if col in df.columns:
                            df[col] = df[col].apply(formatear_moneda)

                    if df.empty:
                        continue

                    # 🔥 guardar en Redis
                    redis_client.set(
                        f"diario:{cache_id}:{nombre_hoja}",
                        df.to_json(orient="records"),
                        ex=3600
                    )

                    preview[nombre_hoja] = df.to_html(
                        classes="table table-sm table-striped",
                        index=False
                    )

                    total_registros[nombre_hoja] = len(df)

                hojas_orden = list(preview.keys())

            except Exception as e:
                print(f"Error procesando diario: {e}")

    return render_template(
        "diario.html",
        preview=preview,
        total_registros=total_registros,
        hojas_orden=hojas_orden,
        cache_id=cache_id
    )

@compras_bp.route("/diario/descargar/<hoja>")
def descargar_diario(hoja):
    from flask import request, send_file
    import pandas as pd
    import io
    from io import StringIO

    cache_id = request.args.get("cache_id")

    if not cache_id:
        return "Cache inválido", 400

    data = redis_client.get(f"diario:{cache_id}:{hoja}")

    if not data:
        return "No hay datos", 404

    df = pd.read_json(StringIO(data), orient="records")

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)

    output.seek(0)

    return send_file(
        output,
        download_name=f"{hoja}.xlsx",
        as_attachment=True
    )


    #=========================================
    # Transmision no esta activa todavia
    #=========================================

@compras_bp.route("/diario/transmitir/<hoja>", methods=["POST"])
def transmitir_diario(hoja):
    from flask import session, redirect, url_for, flash
    import pandas as pd

    data = session.get("diario_data", {}).get(hoja)

    if not data:
        flash("No hay datos para transmitir", "danger")
        return redirect(url_for("compras.diario"))

    df = pd.read_json(data, orient="records")

    print(f"Transmitiendo {hoja} ({len(df)} registros)")

    flash(f"{hoja} transmitido correctamente", "success")
    return redirect(url_for("compras.diario"))



#==========================================================
# SALTA REFRESCOS
#==========================================================

# =========================
# MAPA
# =========================
SUCURSAL_MAP = {
    "Total Empresa": "CO01,CO02,CO04,CO05,CO06,CO07,CO08,CO09,CO10,CO11,CO12,CO14,CO15,CO16,CO17,CO18,CO19,CO20,CO21,CO22,CO23,CO24,CO25,CO26,CO27,CO28,CO29,MA02"
}

# =========================
# NORMALIZAR TEXTO
# =========================
def normalizar_texto(texto):
    if not texto:
        return ""

    texto = str(texto).replace("\xa0", " ")
    texto = texto.lower().strip()

    texto = unicodedata.normalize("NFKD", texto)
    texto = texto.encode("ascii", "ignore").decode("utf-8")

    texto = re.sub(r"[-_/|,]+", " ", texto)
    texto = " ".join(texto.split())

    return texto


# =========================
# DETECTAR COLUMNA
# =========================
def detectar_columna_sucursales(df):
    for i in range(df.shape[1]):
        valores = df.iloc[:, i].astype(str).str.lower()

        if valores.str.contains("jujuy|salta|tucuman", na=False).any():
            print(f"✅ Columna de sucursales detectada: {i}")
            return i

    print("❌ No se encontró columna de sucursales")
    return None


# =========================
# MAPEO FINAL
# =========================
def mapear_sucursales(texto):
    if not texto:
        return ""

    if all(x in texto for x in ["jujuy", "salta", "tucuman"]):
        return SUCURSAL_MAP.get("Total Empresa", "")

    return ""


# =========================
# RUTA PRINCIPAL
# =========================
@compras_bp.route("/refrescos", methods=["GET", "POST"])
def refrescos():
    preview = None
    total_registros = 0
    cache_id = None

    if request.method == "POST":
        archivo = request.files.get("archivo")
        f_desde_raw = request.form.get("fecha_desde")
        f_hasta_raw = request.form.get("fecha_hasta")

        if archivo:
            try:
                import uuid
                cache_id = str(uuid.uuid4())

                f_desde = pd.to_datetime(f_desde_raw).strftime("%d/%m/%Y") if f_desde_raw else ""
                f_hasta = pd.to_datetime(f_hasta_raw).strftime("%d/%m/%Y") if f_hasta_raw else ""

                df_raw = pd.read_excel(archivo, header=None)

                # =========================
                # DETECTAR CABECERA
                # =========================
                mask = df_raw.astype(str).apply(
                    lambda x: x.str.contains(r"Cód\.", case=False, na=False)
                ).any(axis=1)

                if not mask.any():
                    raise ValueError("No se encontró la cabecera 'Cód.' en el archivo.")

                header_idx = df_raw[mask].index[0]
                df_data = df_raw.iloc[header_idx + 1:].copy()

                # =========================
                # DEBUG COLUMNAS
                # =========================
                print("\n===== DEBUG COLUMNAS =====")
                for i in range(df_data.shape[1]):
                    print(f"\nCol {i}:")
                    print(df_data.iloc[:, i].dropna().head(3))
                print("==========================\n")

                df_final = pd.DataFrame()

                # =========================
                # CODIGO
                # =========================
                df_final["CODIGO"] = (
                    df_data.iloc[:, 0]
                    .astype(str)
                    .str.strip()
                    .str.replace(".0", "", regex=False)
                    .str.lstrip("0")
                )

                df_final = completar_ean(df_final)

                # =========================
                # RESTO
                # =========================
                df_final["descripcion"] = df_data.iloc[:, 1].astype(str).str.strip()
                df_final["Normal"] = df_data.iloc[:, 2]

                df_final["Oferta"] = df_data.iloc[:, 5].replace(
                    ["nan", "None", "", "NaN"], pd.NA
                )

                df_final["Cenefa"] = df_data.iloc[:, 6].replace(
                    ["nan", "None", "", "NaN"], pd.NA
                )

                df_final["desde"] = f_desde
                df_final["hasta"] = f_hasta

                # =========================
                # 🔥 DETECTAR SUCURSALES
                # =========================
                col_suc = detectar_columna_sucursales(df_data)

                if col_suc is None:
                    raise ValueError("No se pudo detectar la columna de sucursales")

                df_final["Sucursales"] = df_data.iloc[:, col_suc]

                # =========================
                # LIMPIEZA
                # =========================
                df_final["Sucursales"] = df_final["Sucursales"].astype(str)
                df_final["Sucursales"] = df_final["Sucursales"].apply(normalizar_texto)

                df_final["Sucursales"] = df_final["Sucursales"].apply(
                    lambda x: x if ("jujuy" in x or "salta" in x or "tucuman" in x) else pd.NA
                )

                # 🔥 FFILL
                cols_to_fill = ["Oferta", "Cenefa", "Sucursales"]
                df_final[cols_to_fill] = df_final[cols_to_fill].ffill()

                # =========================
                # MAPEO
                # =========================
                df_final["Sucursales"] = df_final["Sucursales"].apply(mapear_sucursales)

                # =========================
                # LIMPIEZA FINAL
                # =========================
                df_final["CODIGO"] = pd.to_numeric(df_final["CODIGO"], errors="coerce")
                df_final = df_final.dropna(subset=["CODIGO"])
                df_final["CODIGO"] = df_final["CODIGO"].astype(int)

                df_final["descripcion"] = df_final["descripcion"].replace(
                    ["nan", "None", "NaN"], ""
                ).fillna("")

                for col in ["Normal", "Oferta"]:
                    if col in df_final.columns:
                        df_final[col] = df_final[col].apply(formatear_moneda)

                df_final = df_final.fillna("")

                # =========================
                # OUTPUT
                # =========================
                if not df_final.empty:
                    total_registros = len(df_final)

                    redis_client.set(
                        f"refrescos:{cache_id}",
                        df_final.to_json(orient="records"),
                        ex=3600
                    )

                    preview = df_final.to_html(
                        classes="table table-sm table-hover table-bordered text-center",
                        index=False,
                        na_rep=""
                    )
                else:
                    preview = "<div class='alert alert-warning'>No se encontraron registros válidos.</div>"

            except Exception as e:
                preview = f"<div class='alert alert-danger'>Error procesando Refrescos: {e}</div>"

    return render_template(
        "saltarefrescos.html",
        preview=preview,
        total_registros=total_registros,
        cache_id=cache_id
    )


@compras_bp.route("/refrescos/descargar")
def descargar_refrescos():
    from flask import request, send_file
    from io import StringIO
    import io

    cache_id = request.args.get("cache_id")

    if not cache_id:
        return "Cache inválido", 400

    data = redis_client.get(f"refrescos:{cache_id}")

    if not data:
        return "No hay datos", 404

    df = pd.read_json(StringIO(data), orient="records")

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)

    output.seek(0)

    return send_file(
        output,
        download_name="refrescos.xlsx",
        as_attachment=True
    )