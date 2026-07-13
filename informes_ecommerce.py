from flask import Blueprint, render_template, request
from database.db import get_db_connection


informes_ecommerce_bp = Blueprint(
    "informes_ecommerce",
    __name__,
    url_prefix="/ecommerce/informes"
)


@informes_ecommerce_bp.route("/", methods=["GET", "POST"])
def informes():
    registros = []
    total_registros = 0
    error = None

    fecha_desde = request.form.get("fecha_desde", "")
    fecha_hasta = request.form.get("fecha_hasta", "")

    if request.method == "POST":
        conn = None
        cur = None

        try:
            conn = get_db_connection()
            cur = conn.cursor()

            query = """
                SELECT
                    codigo,
                    descripcion,
                    normal,
                    oferta,
                    cenefa,
                    desde,
                    hasta,
                    sucursales,
                    tipo_cenefa
                FROM cenefas
                WHERE desde::text = %s
                  AND hasta::text = %s
                ORDER BY descripcion ASC
            """

            cur.execute(
                query,
                (
                    str(fecha_desde).strip(),
                    str(fecha_hasta).strip()
                )
            )

            columnas = [desc[0] for desc in cur.description]
            filas = cur.fetchall()

            registros = [
                dict(zip(columnas, fila))
                for fila in filas
            ]

            total_registros = len(registros)

        except Exception as e:
            error = f"Error generando el informe: {e}"

        finally:
            if cur:
                cur.close()

            if conn:
                conn.close()

    return render_template(
        "informes_ecommerce.html",
        registros=registros,
        total_registros=total_registros,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        error=error
    )