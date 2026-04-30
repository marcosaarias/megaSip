import os
import sqlite3
import pandas as pd
from flask import Blueprint, render_template, request, flash, redirect, url_for

subrubros_bp = Blueprint("subrubros", __name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "sip.s3db")


def guardar_tabla_subrubros_en_db(df):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        for _, row in df.iterrows():
            idsubrubro = row.get("idsubrubro")
            idrubro = row.get("idrubro")
            nombre = row.get("nombre")

            if pd.isna(idsubrubro) or pd.isna(idrubro) or pd.isna(nombre):
                continue

            cursor.execute("""
                INSERT INTO subrubros (idsubrubro, idrubro, nombre)
                VALUES (?, ?, ?)
                ON CONFLICT(idsubrubro) DO UPDATE SET
                    idrubro = excluded.idrubro,
                    nombre = excluded.nombre
            """, (
                int(idsubrubro),
                int(idrubro),
                str(nombre).strip()
            ))

        conn.commit()

    finally:
        conn.close()


@subrubros_bp.route("/", methods=["GET", "POST"])
def subrubros_view():

    if request.method == "POST":
        archivo = request.files.get("archivo")

        if not archivo or archivo.filename == "":
            flash("Debe seleccionar un archivo Excel", "danger")
            return redirect(url_for("subrubros.subrubros_view"))

        try:
            df = pd.read_excel(archivo)

            df.columns = (
                df.columns
                .str.strip()
                .str.lower()
                .str.replace(" ", "_")
            )

            columnas_requeridas = {"idsubrubro", "idrubro", "nombre"}

            if not columnas_requeridas.issubset(df.columns):
                flash("El Excel debe tener las columnas: idsubrubro, idrubro y nombre", "danger")
                return redirect(url_for("subrubros.subrubros_view"))

            guardar_tabla_subrubros_en_db(df)

            flash("Tabla subrubros actualizada correctamente", "success")
            return redirect(url_for("subrubros.subrubros_view"))

        except Exception as e:
            flash(f"Error al procesar el archivo: {str(e)}", "danger")
            return redirect(url_for("subrubros.subrubros_view"))

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT idsubrubro, idrubro, nombre
        FROM subrubros
        ORDER BY idsubrubro
    """)

    subrubros = cursor.fetchall()
    conn.close()

    return render_template(
        "farmacia/subrubros.html",
        subrubros=subrubros
    )