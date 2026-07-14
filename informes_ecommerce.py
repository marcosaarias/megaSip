import traceback

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
)
from psycopg2.extras import RealDictCursor

from database.db import get_db_connection


informes_ecommerce_bp = Blueprint(
    "informes_ecommerce",
    __name__,
    url_prefix="/ecommerce/informes",
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
        filtros.append(
            "UPPER(TRIM(COALESCE(sucursal_codigo::text, ''))) = %s"
        )
        parametros.append(sucursal)

    if provincia:
        filtros.append(
            "LOWER(TRIM(COALESCE(provincia::text, ''))) = LOWER(%s)"
        )
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

        # ==========================================================
        # INDICADORES PRINCIPALES
        # ==========================================================

        consulta_resumen = f"""
            SELECT
                COUNT(
                    DISTINCT COALESCE(
                        NULLIF(TRIM(numero_pedido::text), ''),
                        id::text
                    )
                ) AS pedidos_mes,

                COUNT(
                    DISTINCT NULLIF(TRIM(dni::text), '')
                ) AS clientes_unicos,

                COUNT(
                    DISTINCT COALESCE(
                        NULLIF(TRIM(numero_pedido::text), ''),
                        id::text
                    )
                ) FILTER (
                    WHERE
                        LOWER(
                            COALESCE(modalidad_entrega::text, '')
                        ) LIKE '%%retiro%%'

                        OR LOWER(
                            COALESCE(modalidad_entrega::text, '')
                        ) LIKE '%%pickup%%'

                        OR LOWER(
                            COALESCE(modalidad_entrega::text, '')
                        ) LIKE '%%tienda%%'
                ) AS retiro_tienda,

                COUNT(
                    DISTINCT COALESCE(
                        NULLIF(TRIM(numero_pedido::text), ''),
                        id::text
                    )
                ) FILTER (
                    WHERE
                        LOWER(
                            COALESCE(modalidad_pago::text, '')
                        ) LIKE '%%online%%'

                        OR LOWER(
                            COALESCE(modalidad_pago::text, '')
                        ) LIKE '%%mercado pago%%'

                        OR LOWER(
                            COALESCE(modalidad_pago::text, '')
                        ) LIKE '%%tarjeta%%'
                ) AS pago_online

            FROM cupones_sorteo
            {where_sql}
        """

        print("====================================", flush=True)
        print("CONSULTA RESUMEN", flush=True)
        print(consulta_resumen, flush=True)
        print("PARAMETROS:", parametros, flush=True)

        cur.execute(consulta_resumen, parametros)
        fila_resumen = cur.fetchone()

        print("FILA RESUMEN:", fila_resumen, flush=True)
        print("====================================", flush=True)

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

        print("RESUMEN FINAL:", resumen, flush=True)

        # ==========================================================
        # EVOLUCION DIARIA
        # ==========================================================

        consulta_por_dia = f"""
            SELECT
                TO_CHAR(fecha_pedido::date, 'DD/MM') AS fecha,

                COUNT(
                    DISTINCT COALESCE(
                        NULLIF(TRIM(numero_pedido::text), ''),
                        id::text
                    )
                ) AS total

            FROM cupones_sorteo
            {where_sql}

            GROUP BY fecha_pedido::date
            ORDER BY fecha_pedido::date ASC
        """

        cur.execute(consulta_por_dia, parametros)
        pedidos_por_dia = cur.fetchall()

        # ==========================================================
        # PEDIDOS POR PROVINCIA
        # ==========================================================

        consulta_por_provincia = f"""
            SELECT
                COALESCE(
                    NULLIF(TRIM(provincia::text), ''),
                    'Sin provincia'
                ) AS provincia,

                COUNT(
                    DISTINCT COALESCE(
                        NULLIF(TRIM(numero_pedido::text), ''),
                        id::text
                    )
                ) AS total

            FROM cupones_sorteo
            {where_sql}

            GROUP BY 1
            ORDER BY total DESC
        """

        cur.execute(consulta_por_provincia, parametros)
        por_provincia = cur.fetchall()

        # ==========================================================
        # PEDIDOS POR SUCURSAL
        # ==========================================================

        consulta_por_sucursal = f"""
            SELECT
                COALESCE(
                    NULLIF(TRIM(sucursal_codigo::text), ''),
                    'SIN SUCURSAL'
                ) AS sucursal,

                COUNT(
                    DISTINCT COALESCE(
                        NULLIF(TRIM(numero_pedido::text), ''),
                        id::text
                    )
                ) AS total

            FROM cupones_sorteo
            {where_sql}

            GROUP BY 1
            ORDER BY total DESC
        """

        cur.execute(consulta_por_sucursal, parametros)
        por_sucursal = cur.fetchall()

        # ==========================================================
        # MODALIDAD DE ENTREGA
        # ==========================================================

        consulta_por_entrega = f"""
            SELECT
                CASE
                    WHEN
                        LOWER(
                            COALESCE(modalidad_entrega::text, '')
                        ) LIKE '%%retiro%%'

                        OR LOWER(
                            COALESCE(modalidad_entrega::text, '')
                        ) LIKE '%%pickup%%'

                        OR LOWER(
                            COALESCE(modalidad_entrega::text, '')
                        ) LIKE '%%tienda%%'

                    THEN 'Retiro en tienda'

                    WHEN
                        LOWER(
                            COALESCE(modalidad_entrega::text, '')
                        ) LIKE '%%envio%%'

                        OR LOWER(
                            COALESCE(modalidad_entrega::text, '')
                        ) LIKE '%%envío%%'

                        OR LOWER(
                            COALESCE(modalidad_entrega::text, '')
                        ) LIKE '%%domicilio%%'

                        OR LOWER(
                            COALESCE(modalidad_entrega::text, '')
                        ) LIKE '%%delivery%%'

                    THEN 'Envío a domicilio'

                    ELSE 'Sin definir'
                END AS modalidad,

                COUNT(
                    DISTINCT COALESCE(
                        NULLIF(TRIM(numero_pedido::text), ''),
                        id::text
                    )
                ) AS total

            FROM cupones_sorteo
            {where_sql}

            GROUP BY 1
            ORDER BY total DESC
        """

        cur.execute(consulta_por_entrega, parametros)
        por_entrega = cur.fetchall()

        # ==========================================================
        # MODALIDAD DE PAGO
        # ==========================================================

        consulta_por_pago = f"""
            SELECT
                CASE
                    WHEN
                        LOWER(
                            COALESCE(modalidad_pago::text, '')
                        ) LIKE '%%online%%'

                        OR LOWER(
                            COALESCE(modalidad_pago::text, '')
                        ) LIKE '%%mercado pago%%'

                        OR LOWER(
                            COALESCE(modalidad_pago::text, '')
                        ) LIKE '%%tarjeta%%'

                    THEN 'Pago online'

                    WHEN
                        LOWER(
                            COALESCE(modalidad_pago::text, '')
                        ) LIKE '%%tienda%%'

                        OR LOWER(
                            COALESCE(modalidad_pago::text, '')
                        ) LIKE '%%efectivo%%'

                        OR LOWER(
                            COALESCE(modalidad_pago::text, '')
                        ) LIKE '%%contra entrega%%'

                    THEN 'Pago en tienda'

                    ELSE 'Sin definir'
                END AS modalidad,

                COUNT(
                    DISTINCT COALESCE(
                        NULLIF(TRIM(numero_pedido::text), ''),
                        id::text
                    )
                ) AS total

            FROM cupones_sorteo
            {where_sql}

            GROUP BY 1
            ORDER BY total DESC
        """

        cur.execute(consulta_por_pago, parametros)
        por_pago = cur.fetchall()

        # ==========================================================
        # OPCIONES DE FILTROS
        # ==========================================================

        cur.execute("""
            SELECT DISTINCT
                UPPER(TRIM(sucursal_codigo::text)) AS sucursal

            FROM cupones_sorteo

            WHERE sucursal_codigo IS NOT NULL
              AND TRIM(sucursal_codigo::text) <> ''

            ORDER BY sucursal
        """)

        sucursales_disponibles = [
            fila["sucursal"]
            for fila in cur.fetchall()
            if fila["sucursal"]
        ]

        cur.execute("""
            SELECT DISTINCT
                TRIM(provincia::text) AS provincia

            FROM cupones_sorteo

            WHERE provincia IS NOT NULL
              AND TRIM(provincia::text) <> ''

            ORDER BY provincia
        """)

        provincias_disponibles = [
            fila["provincia"]
            for fila in cur.fetchall()
            if fila["provincia"]
        ]

        # ==========================================================
        # DEBUG FINAL
        # ==========================================================

        print("========== DEBUG DASHBOARD ==========", flush=True)
        print("WHERE SQL:", where_sql, flush=True)
        print("PARAMETROS:", parametros, flush=True)
        print("DEBUG RESUMEN:", resumen, flush=True)
        print("DEBUG POR DIA:", pedidos_por_dia, flush=True)
        print("DEBUG POR PROVINCIA:", por_provincia, flush=True)
        print("DEBUG POR SUCURSAL:", por_sucursal, flush=True)
        print("DEBUG POR ENTREGA:", por_entrega, flush=True)
        print("DEBUG POR PAGO:", por_pago, flush=True)
        print("=====================================", flush=True)

    except Exception as error:
        if conn:
            conn.rollback()

        print(
            f"ERROR GENERANDO DASHBOARD ECOMMERCE: {error}",
            flush=True,
        )

        traceback.print_exc()

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
        },
    )