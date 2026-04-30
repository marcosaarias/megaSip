import os
import sqlite3
import pandas as pd
from flask import Blueprint, render_template, request, flash, redirect, url_for

rubros_bp = Blueprint("rubros", __name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "sip.s3db")


def guardar_tabla_rubros_en_db(df):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        for _, row in df.iterrows():
            idrubro = row.get("idrubro")
            nombre = row.get("nombre")

            if pd.isna(idrubro) or pd.isna(nombre):
                continue

            cursor.execute("""
                INSERT INTO rubros (idrubro, nombre)
                VALUES (?, ?)
                ON CONFLICT(idrubro) DO UPDATE SET
                    nombre = excluded.nombre
            """, (
                int(idrubro),
                str(nombre).strip()
            ))

        conn.commit()

    finally:
        conn.close()


@rubros_bp.route("/", methods=["GET", "POST"])
def rubros_view():

    if request.method == "POST":
        archivo = request.files.get("archivo")

        if not archivo or archivo.filename == "":
            flash("Debe seleccionar un archivo Excel", "danger")
            return redirect(url_for("rubros.rubros_view"))

        try:
            df = pd.read_excel(archivo)

            df.columns = (
                df.columns
                .str.strip()
                .str.lower()
                .str.replace(" ", "_")
            )

            columnas_requeridas = {"idrubro", "nombre"}

            if not columnas_requeridas.issubset(df.columns):
                flash("El Excel debe tener las columnas: idrubro y nombre", "danger")
                return redirect(url_for("rubros.rubros_view"))

            guardar_tabla_rubros_en_db(df)

            flash("Tabla rubros actualizada correctamente", "success")
            return redirect(url_for("rubros.rubros_view"))

        except Exception as e:
            flash(f"Error al procesar el archivo: {str(e)}", "danger")
            return redirect(url_for("rubros.rubros_view"))

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT idrubro, nombre
        FROM rubros
        ORDER BY idrubro
    """)

    rubros = cursor.fetchall()
    conn.close()

    return render_template(
        "farmacia/rubros.html",
        rubros=rubros
    )