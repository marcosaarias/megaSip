import os
import redis
from io import StringIO
import pandas as pd
import uuid
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, session
from database.db import get_db_connection

farmacia_folder_bp = Blueprint("farmacia_folder", __name__)
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis"),
    port=6379,
    db=0,
    decode_responses=True
)

def guardar_preview_farmacia(lote_id, df):
    redis_client.setex(
        lote_id,
        3600,
        df.to_json(orient="records")
    )

def recuperar_preview_farmacia(lote_id):
    data = redis_client.get(lote_id)

    if not data:
        return None

    return pd.read_json(StringIO(data), orient="records")


def normalizar_col(col):
    return (
        str(col).strip().lower()
        .replace(".", "")
        .replace(" ", "")
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )


ALIAS_FOLDER_FARMACIA = {
    "troquel": ["troquel"],
    "cod_barra": ["coddebarra", "codbarra", "codigobarra", "codebar"],
    "descripcion": ["descripcion", "descrip", "producto"],
    "normal": ["normal"],
    "oferta": ["oferta"],
    "promo": ["promo", "promocion"],
    "reconocido": ["reconoc", "reconocido"],
    "observacion": ["observ", "observacion"],
}

def formatear_precio_arg(valor):
    if valor is None or valor == "":
        return ""

    try:
        valor = float(valor)
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return valor

@farmacia_folder_bp.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        accion = request.form.get("accion")

        if accion == "transmitir":
            #datos = session.get("farmacia_folder_preview")
            #fecha_desde = session.get("farmacia_folder_fecha_desde")
            #fecha_hasta = session.get("farmacia_folder_fecha_hasta")

            #if not datos:
            lote_id = session.get("farmacia_folder_lote_id")
            fecha_desde = session.get("farmacia_folder_fecha_desde")
            fecha_hasta = session.get("farmacia_folder_fecha_hasta")

            df = recuperar_preview_farmacia(lote_id)

            if df is None:
                return render_template(
                    "farmacia_folder.html",
                    mensaje_error="No hay datos procesados para transmitir o expiró la previsualización."
                )

            #df = pd.DataFrame(datos)
            #borrar_folder_farmacia_vigente()
            borrar_folder_farmacia_vigente("folder")
            guardar_farmacia_folder_en_db(
                df,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                tipo_cenefa="folder"
            )

            #session.pop("farmacia_folder_preview", None)
            if lote_id:
                redis_client.delete(lote_id)

            session.pop("farmacia_folder_lote_id", None)
            session.pop("farmacia_folder_fecha_desde", None)
            session.pop("farmacia_folder_fecha_hasta", None)

            return redirect(url_for("farmacia_folder.index"))

        archivo = request.files.get("archivo")

        if archivo:
            fecha_desde = request.form.get("fecha_desde")
            fecha_hasta = request.form.get("fecha_hasta")

            df_raw = pd.read_excel(archivo, header=None)

            fila_header = None
            for i, row in df_raw.iterrows():
                valores = [normalizar_col(x) for x in row.values]

                if "troquel" in valores:
                    fila_header = i
                    break

            if fila_header is None:
                return render_template(
                    "farmacia_folder.html",
                    mensaje_error="No se encontró la columna Troquel en el archivo."
                )

            archivo.seek(0)

            df = pd.read_excel(archivo, header=fila_header)
            df.columns = [str(col).strip() for col in df.columns]

            column_mapping = {}
            cols_norm = {col: normalizar_col(col) for col in df.columns}

            for destino, alias_list in ALIAS_FOLDER_FARMACIA.items():
                for col, col_norm in cols_norm.items():
                    if col_norm in alias_list:
                        column_mapping[col] = destino
                        break

            df = df.rename(columns=column_mapping)

            requeridas = ["troquel", "descripcion", "normal", "oferta", "promo"]
            faltantes = [c for c in requeridas if c not in df.columns]

            if faltantes:
                return render_template(
                    "farmacia_folder.html",
                    mensaje_error=f"Faltan columnas requeridas: {', '.join(faltantes)}"
                )

            df = df[
                df["troquel"].notna()
                & (df["troquel"].astype(str).str.strip() != "")
                & (df["troquel"].astype(str).str.strip().str.lower() != "troquel")
            ].copy()

            df = df.where(pd.notna(df), None)

            #session["farmacia_folder_preview"] = df.to_dict(orient="records")
            
            lote_id = str(uuid.uuid4())
            guardar_preview_farmacia(lote_id, df)
            session["farmacia_folder_lote_id"] = lote_id

            session["farmacia_folder_fecha_desde"] = fecha_desde
            session["farmacia_folder_fecha_hasta"] = fecha_hasta

            #preview = df.to_html(
            #    classes="table table-striped table-hover table-bordered",
            #    index=False
            #)

            df_preview = df.copy()

            for col in ["normal", "oferta"]:
                if col in df_preview.columns:
                    df_preview[col] = df_preview[col].apply(formatear_precio_arg)

            preview = df_preview.to_html(
                classes="table table-striped table-hover table-bordered",
                index=False
            )

            return render_template(
                "farmacia_folder.html",
                preview=preview,
                total_registros=len(df),
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta
            )

    return render_template("farmacia_folder.html")


#def borrar_folder_farmacia_vigente():
#    conn = get_db_connection()
#    cur = conn.cursor()

#    try:
#        cur.execute("DELETE FROM farmacia_folder")
#        conn.commit()
#        print("Folder farmacia vigente eliminado correctamente.", flush=True)

#    except Exception as e:
#        conn.rollback()
#        print("Error borrando folder farmacia vigente:", e, flush=True)
#        raise

#    finally:
#        cur.close()
#        conn.close()


def borrar_folder_farmacia_vigente(tipo_cenefa):
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            DELETE FROM farmacia_folder
            WHERE tipo_cenefa = %s
            """,
            (tipo_cenefa,)
        )

        conn.commit()

        print(
            f"Cenefas tipo '{tipo_cenefa}' eliminadas correctamente.",
            flush=True
        )

    except Exception as e:
        conn.rollback()

        print(
            f"Error borrando cenefas tipo '{tipo_cenefa}':",
            e,
            flush=True
        )

        raise

    finally:
        cur.close()
        conn.close()

def guardar_farmacia_folder_en_db(
    df,
    usuario="sistema",
    lote_carga=None,
    fecha_desde=None,
    fecha_hasta=None,
    tipo_cenefa="folder"
):
    if lote_carga is None:
        lote_carga = (
            datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_"
            + str(uuid.uuid4())[:8]
        )

    fecha_carga = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        #cur.execute("DELETE FROM farmacia_folder")

        for _, row in df.iterrows():
            cur.execute(
                """
                INSERT INTO farmacia_folder (
                    troquel,
                    cod_barra,
                    descripcion,
                    normal,
                    oferta,
                    promo,
                    reconocido,
                    observacion,
                    fecha_desde,
                    fecha_hasta,
                    tipo_cenefa,
                    fecha_carga,
                    lote_carga,
                    usuario_carga
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    #row.get("Troquel"),
                    #row.get("Cod. de Barra"),
                    #row.get("DESCRIPCION"),
                    #row.get("NORMAL"),
                    #row.get("OFERTA"),
                    #row.get("PROMO"),
                    #row.get("Reconoc."),
                    #row.get("Observ"),
                    #fecha_desde,
                    #fecha_hasta,
                    #fecha_carga,
                    #lote_carga,
                    #usuario

                    row.get("troquel"),
                    row.get("cod_barra"),
                    row.get("descripcion"),
                    row.get("normal"),
                    row.get("oferta"),
                    row.get("promo"),
                    row.get("reconocido"),
                    row.get("observacion"),
                    fecha_desde,
                    fecha_hasta,
                    tipo_cenefa,
                    fecha_carga,
                    lote_carga,
                    usuario

                )
            )

        conn.commit()

        print("Guardado OK:", len(df))
        print("Lote carga:", lote_carga)

    except Exception as e:
        conn.rollback()
        print("Error guardando farmacia_folder:", e)
        raise

    finally:
        cur.close()
        conn.close()


#def obtener_datos_farmacia_folder():
#    conn = get_db_connection()
#    cur = conn.cursor()

#    try:
#        cur.execute(
#            """
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
#            WHERE tipo_cenefa = %s
#            ORDER BY id DESC
#            """,
#            ("folder",)
#        )

#        return cur.fetchall()

#    finally:
#        cur.close()
#        conn.close()

def obtener_datos_farmacia_folder(tipo_cenefa="folder"):
    tipos_validos = {
        "folder",
        "diarios",
        "nutricia",
    }

    tipo_cenefa = str(tipo_cenefa).strip().lower()

    if tipo_cenefa not in tipos_validos:
        tipo_cenefa = "folder"

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT
                troquel,
                cod_barra,
                descripcion,
                normal,
                oferta,
                promo,
                fecha_desde,
                fecha_hasta
            FROM farmacia_folder
            WHERE tipo_cenefa = %s
            ORDER BY id DESC
            """,
            (tipo_cenefa,),
        )

        return cur.fetchall()

    finally:
        cur.close()
        conn.close()