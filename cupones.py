from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import pandas as pd
from database.db import get_db_connection

cupones_bp = Blueprint("cupones", __name__, url_prefix="/cupones")


def normalizar_sucursal_sorteo(valor):
    if not valor:
        return ""

    valor = str(valor).strip().upper()

    mapa = {
        "ALBERDISA01": "CO01",
        "ALBERDISA02": "CO02",
        "ALBERDISA04": "CO04",
        "ALBERDISA05": "CO05",
        "ALBERDISA06": "CO06",
        "ALBERDISA07": "CO07",
        "ALBERDISA08": "CO08",
        "ALBERDISA09": "CO09",
        "ALBERDISA10": "CO10",
        "ALBERDISA11": "CO11",
        "ALBERDISA12": "CO12",
        "ALBERDISA14": "CO14",
        "ALBERDISA15": "CO15",
        "ALBERDISA16": "CO16",
        "ALBERDISA17": "CO17",
        "ALBERDISA18": "CO18",
        "ALBERDISA19": "CO19",
        "ALBERDISA20": "CO20",
        "ALBERDISA21": "CO21",
        "ALBERDISA22": "CO22",
        "ALBERDISA23": "CO23",
        "ALBERDISA24": "CO24",
        "ALBERDISA25": "CO25",
        "ALBERDISA26": "CO26",
        "ALBERDISA27": "CO27",
        "ALBERDISA28": "CO28",
        "ALBERDISA29": "CO29",
        "MAYORISTA02": "MA02",
        "MA02": "MA02",
    }

    return mapa.get(valor, valor)


def crear_tabla_cupones_sorteo():
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cupones_sorteo (
                id SERIAL PRIMARY KEY,
                nombre TEXT,
                dni TEXT,
                telefono TEXT,
                sucursal_origen TEXT,
                sucursal_codigo TEXT,
                estado TEXT,
                fecha_transmision TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.commit()
    finally:
        cur.close()
        conn.close()


@cupones_bp.route("/", methods=["GET", "POST"])
def index():
    if session.get("usuario_rol") != "publicidad":
        return redirect(url_for("sistemas.login"))

    cupones = []
    total_filas = 0
    total_cupones = 0

    if request.method == "POST":
        archivo = request.files.get("archivo")

        if not archivo or archivo.filename == "":
            flash("Debe seleccionar un archivo Excel")
            return redirect(url_for("cupones.index"))

        df = pd.read_excel(archivo)
        total_filas = len(df)

        for _, fila in df.iterrows():
            estado = str(fila.get("Estado", "")).strip()

            if estado in ["Facturado", "Entregado"]:
                cupones.append({
                    "nombre": fila.get("Cliente", ""),
                    "dni": fila.get("Documento cliente", ""),
                    "telefono": fila.get("Teléfono", ""),
                    "sucursal": fila.get("Tienda", ""),
                    "estado": estado
                })

        total_cupones = len(cupones)
        session["cupones_generados"] = cupones

    return render_template(
        "publicidad/cupones.html",
        cupones=cupones,
        total_filas=total_filas,
        total_cupones=total_cupones
    )


@cupones_bp.route("/transmitir_sucursales", methods=["POST"])
def transmitir_sucursales():
    if session.get("usuario_rol") != "publicidad":
        return redirect(url_for("sistemas.login"))

    cupones = session.get("cupones_generados", [])

    if not cupones:
        flash("No hay cupones para transmitir")
        return redirect(url_for("cupones.index"))

    crear_tabla_cupones_sorteo()

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        for cupon in cupones:
            sucursal_origen = cupon.get("sucursal", "")
            sucursal_codigo = normalizar_sucursal_sorteo(sucursal_origen)

            cur.execute("""
                INSERT INTO cupones_sorteo (
                    nombre,
                    dni,
                    telefono,
                    sucursal_origen,
                    sucursal_codigo,
                    estado
                )
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                str(cupon.get("nombre", "")),
                str(cupon.get("dni", "")),
                str(cupon.get("telefono", "")),
                str(sucursal_origen),
                str(sucursal_codigo),
                str(cupon.get("estado", ""))
            ))

        conn.commit()
        flash("Cupones transmitidos correctamente a sucursales")

    except Exception as e:
        conn.rollback()
        flash(f"Error transmitiendo cupones: {e}")

    finally:
        cur.close()
        conn.close()

    return redirect(url_for("cupones.index"))


@cupones_bp.route("/sucursales_sorteo")
def sucursales_sorteo():
    if session.get("usuario_rol") != "sucursal":
        return redirect(url_for("sistemas.login"))

    crear_tabla_cupones_sorteo()

    sucursal_codigo = session.get("usuario_nombre", "").strip().upper()

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT
                nombre,
                dni,
                telefono,
                sucursal_origen,
                sucursal_codigo,
                estado,
                fecha_transmision
            FROM cupones_sorteo
            WHERE sucursal_codigo = %s
            ORDER BY fecha_transmision DESC, id DESC
        """, (sucursal_codigo,))

        cupones = cur.fetchall()

    finally:
        cur.close()
        conn.close()

    return render_template(
        "publicidad/sucursales_sorteo.html",
        cupones=cupones,
        sucursal=sucursal_codigo
    )