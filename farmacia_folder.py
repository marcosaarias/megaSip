import pandas as pd
import uuid
from datetime import datetime
from flask import Blueprint, render_template, request
from database.db import get_db_connection
farmacia_folder_bp = Blueprint("farmacia_folder", __name__)


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

            #return "Guardado OK"
            return redirect(url_for("farmacia_folder.index"))

    return render_template("farmacia_folder.html")


def guardar_farmacia_folder_en_db(
    df,
    usuario="sistema",
    lote_carga=None,
    fecha_desde=None,
    fecha_hasta=None
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
        cur.execute("DELETE FROM farmacia_folder")

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
                    fecha_carga,
                    lote_carga,
                    usuario_carga
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                """,
                (
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