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
    provincia = request.args.get("provincia", "").strip()

    filtros = []
    parametros = []

    if fecha_desde:
        filtros.append("fecha_pedido::date >= %s")
        parametros.append(fecha_desde)

    if fecha_hasta:
        filtros.append("fecha_pedido::date <= %s")
        parametros.append(fecha_hasta)

    if sucursal:
        filtros.append("UPPER(TRIM(sucursal_codigo)) = %s")
        parametros.append(sucursal)

    if provincia:
        filtros.append("LOWER(TRIM(provincia)) = LOWER(%s)")
        parametros.append(provincia)

    where_sql = ""

    if filtros:
        where_sql = "WHERE " + " AND ".join(filtros)

    resumen = {
        "pedidos_mes": 0,
        "clientes_unicos": 0,
        "retiro_tienda": 0,
        "pago_online": 0,
    }

    pedidos_por_dia = []
    por_provincia = []
    por_sucursal = []
    por_entrega = []
    por_pago = []
    sucursales_disponibles = []
    provincias_disponibles = []

    conn = None
    cur = None

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        consulta_resumen = f"""
            SELECT
                COUNT(
                    DISTINCT NULLIF(TRIM(numero_pedido), '')
                ) AS pedidos_mes,

                COUNT(
                    DISTINCT NULLIF(TRIM(dni), '')
                ) AS clientes_unicos,

                COUNT(
                    DISTINCT NULLIF(TRIM(numero_pedido), '')
                ) FILTER (
                    WHERE LOWER(TRIM(modalidad_entrega))
                          IN (
                              'retiro en tienda',
                              'retiro en sucursal'
                          )
                       OR LOWER(TRIM(modalidad_entrega))
                          LIKE '%retiro%'
                       OR LOWER(TRIM(modalidad_entrega))
                          LIKE '%pickup%'
                ) AS retiro_tienda,

                COUNT(
                    DISTINCT NULLIF(TRIM(numero_pedido), '')
                ) FILTER (
                    WHERE LOWER(TRIM(modalidad_pago))
                          = 'pago online'
                       OR LOWER(TRIM(modalidad_pago))
                          LIKE '%online%'
                       OR LOWER(TRIM(modalidad_pago))
                          LIKE '%mercado pago%'
                ) AS pago_online

            FROM cupones_sorteo
            {where_sql}
        """

        cur.execute(consulta_resumen, parametros)
        fila_resumen = cur.fetchone()

        if fila_resumen:
            resumen = {
                "pedidos_mes": convertir_entero(
                    fila_resumen["pedidos_mes"]
                ),
                "clientes_unicos": convertir_entero(
                    fila_resumen["clientes_unicos"]
                ),
                "retiro_tienda": convertir_entero(
                    fila_resumen["retiro_tienda"]
                ),
                "pago_online": convertir_entero(
                    fila_resumen["pago_online"]
                ),
            }

        consulta_por_dia = f"""
            SELECT
                TO_CHAR(fecha_pedido::date, 'DD/MM') AS fecha,
                COUNT(
                    DISTINCT NULLIF(TRIM(numero_pedido), '')
                ) AS total

            FROM cupones_sorteo
            {where_sql}

            GROUP BY fecha_pedido::date
            ORDER BY fecha_pedido::date ASC
        """

        cur.execute(consulta_por_dia, parametros)
        pedidos_por_dia = cur.fetchall()

        consulta_por_provincia = f"""
            SELECT
                COALESCE(
                    NULLIF(TRIM(provincia), ''),
                    'Sin provincia'
                ) AS provincia,

                COUNT(
                    DISTINCT NULLIF(TRIM(numero_pedido), '')
                ) AS total

            FROM cupones_sorteo
            {where_sql}

            GROUP BY
                COALESCE(
                    NULLIF(TRIM(provincia), ''),
                    'Sin provincia'
                )

            ORDER BY total DESC
        """

        cur.execute(consulta_por_provincia, parametros)
        por_provincia = cur.fetchall()

        consulta_por_sucursal = f"""
            SELECT
                COALESCE(
                    NULLIF(TRIM(sucursal_codigo), ''),
                    'SIN SUCURSAL'
                ) AS sucursal,

                COUNT(
                    DISTINCT NULLIF(TRIM(numero_pedido), '')
                ) AS total

            FROM cupones_sorteo
            {where_sql}

            GROUP BY
                COALESCE(
                    NULLIF(TRIM(sucursal_codigo), ''),
                    'SIN SUCURSAL'
                )

            ORDER BY total DESC
        """

        cur.execute(consulta_por_sucursal, parametros)
        por_sucursal = cur.fetchall()

        consulta_por_entrega = f"""
            SELECT
                CASE
                    WHEN LOWER(TRIM(modalidad_entrega))
                         LIKE '%retiro%'
                      OR LOWER(TRIM(modalidad_entrega))
                         LIKE '%pickup%'
                      OR LOWER(TRIM(modalidad_entrega))
                         LIKE '%tienda%'
                    THEN 'Retiro en tienda'

                    WHEN LOWER(TRIM(modalidad_entrega))
                         LIKE '%envio%'
                      OR LOWER(TRIM(modalidad_entrega))
                         LIKE '%envío%'
                      OR LOWER(TRIM(modalidad_entrega))
                         LIKE '%domicilio%'
                      OR LOWER(TRIM(modalidad_entrega))
                         LIKE '%delivery%'
                    THEN 'Envío a domicilio'

                    ELSE 'Sin definir'
                END AS modalidad,

                COUNT(
                    DISTINCT NULLIF(TRIM(numero_pedido), '')
                ) AS total

            FROM cupones_sorteo
            {where_sql}

            GROUP BY modalidad
            ORDER BY total DESC
        """

        cur.execute(consulta_por_entrega, parametros)
        por_entrega = cur.fetchall()

        consulta_por_pago = f"""
            SELECT
                CASE
                    WHEN LOWER(TRIM(modalidad_pago))
                         LIKE '%online%'
                      OR LOWER(TRIM(modalidad_pago))
                         LIKE '%mercado pago%'
                      OR LOWER(TRIM(modalidad_pago))
                         LIKE '%tarjeta%'
                    THEN 'Pago online'

                    WHEN LOWER(TRIM(modalidad_pago))
                         LIKE '%tienda%'
                      OR LOWER(TRIM(modalidad_pago))
                         LIKE '%efectivo%'
                      OR LOWER(TRIM(modalidad_pago))
                         LIKE '%contra entrega%'
                    THEN 'Pago en tienda'

                    ELSE 'Sin definir'
                END AS modalidad,

                COUNT(
                    DISTINCT NULLIF(TRIM(numero_pedido), '')
                ) AS total

            FROM cupones_sorteo
            {where_sql}

            GROUP BY modalidad
            ORDER BY total DESC
        """

        cur.execute(consulta_por_pago, parametros)
        por_pago = cur.fetchall()

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
                TRIM(provincia) AS provincia
            FROM cupones_sorteo
            WHERE provincia IS NOT NULL
              AND TRIM(provincia) <> ''
            ORDER BY provincia
        """)

        provincias_disponibles = [
            fila["provincia"]
            for fila in cur.fetchall()
            if fila["provincia"]
        ]

        print("DEBUG RESUMEN:", resumen, flush=True)
        print("DEBUG POR DIA:", pedidos_por_dia, flush=True)
        print("DEBUG POR PROVINCIA:", por_provincia, flush=True)
        print("DEBUG POR SUCURSAL:", por_sucursal, flush=True)
        print("DEBUG POR ENTREGA:", por_entrega, flush=True)
        print("DEBUG POR PAGO:", por_pago, flush=True)

    except Exception as error:
        print(
            f"ERROR GENERANDO DASHBOARD ECOMMERCE: {error}",
            flush=True
        )

    finally:
        if cur:
            cur.close()

        if conn:
            conn.close()

    return render_template(
        "publicidad/informes_ecommerce.html",
        resumen=resumen,
        pedidos_por_dia=pedidos_por_dia,
        por_provincia=por_provincia,
        por_sucursal=por_sucursal,
        por_entrega=por_entrega,
        por_pago=por_pago,
        sucursales_disponibles=sucursales_disponibles,
        provincias_disponibles=provincias_disponibles,
        filtros={
            "desde": fecha_desde,
            "hasta": fecha_hasta,
            "sucursal": sucursal,
            "provincia": provincia,
        }
    )