import os
import sqlite3
from datetime import datetime
from flask import Blueprint, render_template, request
from sistemas import login_requerido

logs_bp = Blueprint("logs", __name__, url_prefix="/logs")

DB_PATH = os.path.join(os.path.dirname(__file__), "sip.s3db")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_logs_compras_table():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs_compras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            usuario TEXT,
            nivel TEXT NOT NULL,
            origen TEXT NOT NULL,
            modulo TEXT NOT NULL,
            accion TEXT NOT NULL,
            archivo TEXT,
            detalle TEXT,
            estado TEXT NOT NULL,
            total_registros INTEGER DEFAULT 0,
            error_trace TEXT
        )
    """)

    conn.commit()
    conn.close()


def guardar_log_compras(
    usuario,
    nivel,
    origen,
    modulo,
    accion,
    archivo=None,
    detalle="",
    estado="exitoso",
    total_registros=0,
    error_trace=None,
    fecha=None
):
    conn = get_db_connection()
    cursor = conn.cursor()

    if fecha is None:
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO logs_compras (
            fecha, usuario, nivel, origen, modulo, accion,
            archivo, detalle, estado, total_registros, error_trace
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        fecha,
        usuario,
        nivel,
        origen,
        modulo,
        accion,
        archivo,
        detalle,
        estado,
        total_registros,
        error_trace
    ))

    conn.commit()
    conn.close()


init_logs_compras_table()


@logs_bp.route("/compras")
@login_requerido("sistemas")
def logs_compras():
    conn = get_db_connection()
    cursor = conn.cursor()

    filtros = {
        "nivel": request.args.get("nivel", "").strip(),
        "origen": request.args.get("origen", "").strip(),
        "modulo": request.args.get("modulo", "").strip(),
        "estado": request.args.get("estado", "").strip(),
        "q": request.args.get("q", "").strip(),
    }

    query = """
        SELECT id, fecha, usuario, nivel, origen, modulo, accion,
               archivo, detalle, estado, total_registros, error_trace
        FROM logs_compras
        WHERE 1=1
    """
    params = []

    if filtros["nivel"]:
        query += " AND nivel = ?"
        params.append(filtros["nivel"])

    if filtros["origen"]:
        query += " AND origen = ?"
        params.append(filtros["origen"])

    if filtros["modulo"]:
        query += " AND modulo = ?"
        params.append(filtros["modulo"])

    if filtros["estado"]:
        query += " AND estado = ?"
        params.append(filtros["estado"])

    if filtros["q"]:
        query += """
            AND (
                usuario LIKE ?
                OR accion LIKE ?
                OR archivo LIKE ?
                OR detalle LIKE ?
                OR error_trace LIKE ?
            )
        """
        like_value = f"%{filtros['q']}%"
        params.extend([like_value, like_value, like_value, like_value, like_value])

    query += " ORDER BY id DESC"

    cursor.execute(query, params)
    logs = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) AS total FROM logs_compras")
    total_eventos = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM logs_compras
        WHERE date(fecha) = date('now')
    """)
    eventos_hoy = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM logs_compras
        WHERE date(fecha) = date('now')
          AND nivel IN ('ERROR', 'CRITICAL')
    """)
    errores_hoy = cursor.fetchone()["total"]

    cursor.execute("""
        SELECT fecha, accion
        FROM logs_compras
        WHERE nivel IN ('ERROR', 'CRITICAL')
        ORDER BY id DESC
        LIMIT 1
    """)
    ultimo_error_row = cursor.fetchone()

    cursor.execute("""
        SELECT fecha, accion
        FROM logs_compras
        WHERE estado = 'exitoso'
        ORDER BY id DESC
        LIMIT 1
    """)
    ultima_ejecucion_row = cursor.fetchone()

    conn.close()

    resumen = {
        "total_eventos": total_eventos,
        "eventos_hoy": eventos_hoy,
        "errores_hoy": errores_hoy,
        "ultimo_error": (
            f"{ultimo_error_row['fecha']} - {ultimo_error_row['accion']}"
            if ultimo_error_row else ""
        ),
        "ultima_ejecucion": (
            f"{ultima_ejecucion_row['fecha']} - {ultima_ejecucion_row['accion']}"
            if ultima_ejecucion_row else ""
        )
    }

    return render_template(
        "logs_compras.html",
        logs=logs,
        resumen=resumen,
        filtros=filtros
    )


@logs_bp.route("/farmacia")
@login_requerido("sistemas")
def logs_farmacia():
    return render_template("logs_farmacia.html")