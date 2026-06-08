import pandas as pd
import uuid
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for
from database.db import get_db_connection
farmacia_folder_bp = Blueprint("farmacia_folder", __name__)


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


@farmacia_folder_bp.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        archivo = request.files.get("archivo")

        if archivo:
            fecha_desde = request.form.get("fecha_desde")
            fecha_hasta = request.form.get("fecha_hasta")

            #df = pd.read_excel(archivo)
            #df.columns = [str(col).strip() for col in df.columns]

            df_raw = pd.read_excel(archivo, header=None)

            fila_header = None
            for i, row in df_raw.iterrows():
                valores = [normalizar_col(x) for x in row.values]

                if "troquel" in valores:
                    fila_header = i
                    break

            if fila_header is None:
                return "Error: no se encontró la columna Troquel en el archivo.", 400

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
                return f"Error: faltan columnas requeridas: {', '.join(faltantes)}", 400

            df = df[
            df["troquel"].notna()
            & (df["troquel"].astype(str).str.strip() != "")
            & (df["troquel"].astype(str).str.strip().str.lower() != "troquel")
            ].copy()

            print("COLUMNAS FINALES:", df.columns.tolist(), flush=True)
            print(df[["troquel", "descripcion", "promo"]].head(10).to_string(), flush=True) 

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