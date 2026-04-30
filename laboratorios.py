import os
import sqlite3
import pandas as pd
from flask import Blueprint, render_template, request, flash, redirect, url_for

laboratorios_bp = Blueprint("laboratorios", __name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "sip.s3db")


def guardar_tabla_laboratorios_en_db(df):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        for _, row in df.iterrows():
            codigo = row.get("codigo")
            nombre = row.get("nombre")

            if pd.isna(codigo) or pd.isna(nombre):
                continue

            cursor.execute("""
                INSERT INTO laboratorios (codigo, nombre)
                VALUES (?, ?)
                ON CONFLICT(codigo) DO UPDATE SET
                    nombre = excluded.nombre
            """, (
                int(codigo),
                str(nombre).strip()
            ))

        conn.commit()

    finally:
        conn.close()


@laboratorios_bp.route("/", methods=["GET", "POST"])
def laboratorios_view():

    if request.method == "POST":
        archivo = request.files.get("archivo")

        if not archivo or archivo.filename == "":
            flash("Debe seleccionar un archivo Excel", "danger")
            return redirect(url_for("laboratorios.laboratorios_view"))

        try:
            df = pd.read_excel(archivo)

            df.columns = (
                df.columns
                .str.strip()
                .str.lower()
                .str.replace(" ", "_")
            )

            columnas_requeridas = {"codigo", "nombre"}

            if not columnas_requeridas.issubset(df.columns):
                flash("El Excel debe tener las columnas: codigo y nombre", "danger")
                return redirect(url_for("laboratorios.laboratorios_view"))

            guardar_tabla_laboratorios_en_db(df)

            flash("Tabla laboratorios actualizada correctamente", "success")
            return redirect(url_for("laboratorios.laboratorios_view"))

        except Exception as e:
            flash(f"Error al procesar el archivo: {str(e)}", "danger")
            return redirect(url_for("laboratorios.laboratorios_view"))

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT codigo, nombre
        FROM laboratorios
        ORDER BY codigo
    """)

    laboratorios = cursor.fetchall()
    conn.close()

    return render_template(
        "farmacia/laboratorios.html",
        laboratorios=laboratorios
    )