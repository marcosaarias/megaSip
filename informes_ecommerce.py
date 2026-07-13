from flask import Blueprint, render_template, request, redirect, url_for, session
from psycopg2.extras import RealDictCursor

from database.db import get_db_connection


informes_ecommerce_bp = Blueprint(
    "informes_ecommerce",
    __name__,
    url_prefix="/ecommerce/informes"
)


def convertir_entero(valor):
    try:
        return int(valor or 0)
    except (TypeError, ValueError):
        return 0


@informes_ecommerce_bp.route("/", methods=["GET"])
def informes():

    if session.get("usuario_rol") != "publicidad":
        return redirect(url_for("sistemas.login"))

    fecha_desde = request.args.get("desde", "").strip()
    fecha_hasta = request.args.get("hasta", "").strip()
    sucursal = request.args.get("sucursal", "").strip().upper()
    estado = request.args.get("estado", "").strip()

    filtros = []
    parametros = []

    if fecha_desde:
        filtros.append("fecha_transmision::date >= %s")
        parametros.append(fecha_desde)

    if fecha_hasta:
        filtros.append("fecha_transmision::date <= %s")
        parametros.append(fecha_hasta)

    if sucursal:
        filtros.append("UPPER(TRIM(sucursal_codigo)) = %s")
        parametros.append(sucursal)

    if estado:
        filtros.append("LOWER(TRIM(estado)) = LOWER(%s)")
        parametros.append(estado)

    where_sql = ""

    if filtros:
        where_sql = "WHERE " + " AND ".join(filtros)

    resumen = {
        "total_cupones": 0,
        "participantes_unicos": 0,
        "total_sucursales": 0,
        "total_facturados": 0,
        "total_entregados": 0,
    }

    por_sucursal = []
    por_estado = []
    por_dia = []
    ultimos_cupones = []
    sucursales_disponibles = []
    estados_disponibles = []

    conn = None
    cur = None

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        consulta_resumen = f"""
            SELECT
                COUNT(*) AS total_cupones,

                COUNT(
                    DISTINCT NULLIF(TRIM(dni), '')
                ) AS participantes_unicos,

                COUNT(
                    DISTINCT NULLIF(TRIM(sucursal_codigo), '')
                ) AS total_sucursales,

                COUNT(*) FILTER (
                    WHERE LOWER(TRIM(estado)) = 'facturado'
                ) AS total_facturados,

                COUNT(*) FILTER (
                    WHERE LOWER(TRIM(estado)) = 'entregado'
                ) AS total_entregados

            FROM cupones_sorteo
            {where_sql}
        """

        cur.execute(consulta_resumen, parametros)
        fila_resumen = cur.fetchone()

        if fila_resumen:
            resumen = {
                "total_cupones": convertir_entero(
                    fila_resumen["total_cupones"]
                ),
                "participantes_unicos": convertir_entero(
                    fila_resumen["participantes_unicos"]
                ),
                "total_sucursales": convertir_entero(
                    fila_resumen["total_sucursales"]
                ),
                "total_facturados": convertir_entero(
                    fila_resumen["total_facturados"]
                ),
                "total_entregados": convertir_entero(
                    fila_resumen["total_entregados"]
                ),
            }

        consulta_por_sucursal = f"""
            SELECT
                COALESCE(
                    NULLIF(TRIM(sucursal_codigo), ''),
                    'SIN SUCURSAL'
                ) AS sucursal,

                COUNT(*) AS cantidad,

                COUNT(
                    DISTINCT NULLIF(TRIM(dni), '')
                ) AS participantes

            FROM cupones_sorteo
            {where_sql}

            GROUP BY
                COALESCE(
                    NULLIF(TRIM(sucursal_codigo), ''),
                    'SIN SUCURSAL'
                )

            ORDER BY cantidad DESC
        """

        cur.execute(consulta_por_sucursal, parametros)
        por_sucursal = cur.fetchall()

        consulta_por_estado = f"""
            SELECT
                COALESCE(
                    NULLIF(TRIM(estado), ''),
                    'Sin estado'
                ) AS estado,

                COUNT(*) AS cantidad

            FROM cupones_sorteo
            {where_sql}

            GROUP BY
                COALESCE(
                    NULLIF(TRIM(estado), ''),
                    'Sin estado'
                )

            ORDER BY cantidad DESC
        """

        cur.execute(consulta_por_estado, parametros)
        por_estado = cur.fetchall()

        consulta_por_dia = f"""
            SELECT
                fecha_transmision::date AS fecha,
                COUNT(*) AS cantidad

            FROM cupones_sorteo
            {where_sql}

            GROUP BY fecha_transmision::date
            ORDER BY fecha_transmision::date ASC
        """

        cur.execute(consulta_por_dia, parametros)
        por_dia = cur.fetchall()

        consulta_ultimos = f"""
            SELECT
                id,
                nombre,
                dni,
                telefono,
                sucursal_origen,
                sucursal_codigo,
                estado,
                fecha_transmision

            FROM cupones_sorteo
            {where_sql}

            ORDER BY fecha_transmision DESC, id DESC
            LIMIT 500
        """

        cur.execute(consulta_ultimos, parametros)
        ultimos_cupones = cur.fetchall()

        cur.execute("""
            SELECT DISTINCT
                UPPER(TRIM(sucursal_codigo)) AS sucursal
            FROM cupones_sorteo
            WHERE sucursal_codigo IS NOT NULL
              AND TRIM(sucursal_codigo) <> ''
            ORDER BY sucursal
        """)

        sucursales_disponibles = [
            fila["sucursal"]
            for fila in cur.fetchall()
            if fila["sucursal"]
        ]

        cur.execute("""
            SELECT DISTINCT
                TRIM(estado) AS estado
            FROM cupones_sorteo
            WHERE estado IS NOT NULL
              AND TRIM(estado) <> ''
            ORDER BY estado
        """)

        estados_disponibles = [
            fila["estado"]
            for fila in cur.fetchall()
            if fila["estado"]
        ]

    except Exception as error:
        print(
            f"ERROR GENERANDO DASHBOARD DE CUPONES: {error}",
            flush=True
        )

    finally:
        if cur:
            cur.close()

        if conn:
            conn.close()

    max_sucursal = max(
        [
            convertir_entero(fila["cantidad"])
            for fila in por_sucursal
        ],
        default=1
    )

    max_estado = max(
        [
            convertir_entero(fila["cantidad"])
            for fila in por_estado
        ],
        default=1
    )

    max_dia = max(
        [
            convertir_entero(fila["cantidad"])
            for fila in por_dia
        ],
        default=1
    )

    return render_template(
        "publicidad/informes_ecommerce.html",
        resumen=resumen,
        por_sucursal=por_sucursal,
        por_estado=por_estado,
        por_dia=por_dia,
        ultimos_cupones=ultimos_cupones,
        sucursales_disponibles=sucursales_disponibles,
        estados_disponibles=estados_disponibles,
        max_sucursal=max_sucursal,
        max_estado=max_estado,
        max_dia=max_dia,
        filtros={
            "desde": fecha_desde,
            "hasta": fecha_hasta,
            "sucursal": sucursal,
            "estado": estado,
        }
    )