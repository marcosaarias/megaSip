import os
import sqlite3
import pandas as pd
import uuid
from datetime import datetime
from flask import Blueprint, render_template, request

farmacia_folder_bp = Blueprint("farmacia_folder", __name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "sip.s3db")


@farmacia_folder_bp.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        archivo = request.files.get("archivo")

        if archivo:
            fecha_desde = request.form.get("fecha_desde")
            fecha_hasta = request.form.get("fecha_hasta")

            df = pd.read_excel(archivo)
            df.columns = [str(col).strip() for col in df.columns]

            guardar_farmacia_folder_en_db(
                df,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta
            )

            return "Guardado OK"

    return render_template("farmacia_folder.html")


import os
import sqlite3
import pandas as pd
import uuid
from datetime import datetime
from flask import Blueprint, render_template, request

farmacia_folder_bp = Blueprint("farmacia_folder", __name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "sip.s3db")


@farmacia_folder_bp.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        archivo = request.files.get("archivo")

        if archivo:
            fecha_desde = request.form.get("fecha_desde")
            fecha_hasta = request.form.get("fecha_hasta")

            df = pd.read_excel(archivo)
            df.columns = [str(col).strip() for col in df.columns]

            guardar_farmacia_folder_en_db(
                df,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta
            )

            return "Guardado OK"

    return render_template("farmacia_folder.html")


def guardar_farmacia_folder_en_db(df, usuario="sistema", lote_carga=None, fecha_desde=None, fecha_hasta=None):
    if lote_carga is None:
        lote_carga = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + str(uuid.uuid4())[:8]

    fecha_carga = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # HOTFIX: limpiar datos anteriores del folder
        cursor.execute("DELETE FROM farmacia_folder")

        for _, row in df.iterrows():
            cursor.execute("""
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
                    fecha_carga,
                    lote_carga,
                    usuario_carga
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row.get("Troquel"),
                row.get("Cod. de Barra"),
                row.get("DESCRIPCION"),
                row.get("NORMAL"),
                row.get("OFERTA"),
                row.get("PROMO"),
                row.get("Reconoc."),
                row.get("Observ"),
                fecha_desde,
                fecha_hasta,
                fecha_carga,
                lote_carga,
                usuario
            ))

        conn.commit()
        print("Guardado OK:", len(df))
        print("Lote carga:", lote_carga)

    except Exception as e:
        conn.rollback()
        print("Error guardando farmacia_folder:", e)
        raise

    finally:
        conn.close()