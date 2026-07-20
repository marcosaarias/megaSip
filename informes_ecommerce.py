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

    # ==========================================================
    # FILTROS
    # ==========================================================

    if fecha_desde:
        filtros.append("i.fecha_creacion::date >= %s")
        parametros.append(fecha_desde)

    if fecha_hasta:
        filtros.append("i.fecha_creacion::date <= %s")
        parametros.append(fecha_hasta)

    if sucursal:
        filtros.append(
            "UPPER(TRIM(COALESCE(i.sucursal_codigo, ''))) = %s"
        )
        parametros.append(sucursal)

    if provincia:
        filtros.append(
            "LOWER(TRIM(COALESCE(s.provincia, ''))) = LOWER(%s)"
        )
        parametros.append(provincia)

    where_sql = ""

    if filtros:
        where_sql = "WHERE " + " AND ".join(filtros)

    # ==========================================================
    # VALORES POR DEFECTO
    # ==========================================================

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
                        NULLIF(TRIM(i.id_pedido), ''),
                        i.id::text
                    )
                ) AS pedidos_mes,

                COUNT(
                    DISTINCT NULLIF(
                        TRIM(i.documento_cliente),
                        ''
                    )
                ) AS clientes_unicos,

                COUNT(
                    DISTINCT COALESCE(
                        NULLIF(TRIM(i.id_pedido), ''),
                        i.id::text
                    )
                ) FILTER (
                    WHERE
                        LOWER(
                            COALESCE(i.transportadora, '')
                        ) LIKE '%%retiro%%'

                        OR LOWER(
                            COALESCE(i.transportadora, '')
                        ) LIKE '%%pickup%%'

                        OR LOWER(
                            COALESCE(i.transportadora, '')
                        ) LIKE '%%tienda%%'
                ) AS retiro_tienda,

                COUNT(
                    DISTINCT COALESCE(
                        NULLIF(TRIM(i.id_pedido), ''),
                        i.id::text
                    )
                ) FILTER (
                    WHERE
                        LOWER(
                            COALESCE(i.medio_pago, '')
                        ) NOT LIKE '%%pago en tienda%%'

                        AND LOWER(
                            COALESCE(i.medio_pago, '')
                        ) NOT LIKE '%%efectivo%%'

                        AND TRIM(
                            COALESCE(i.medio_pago, '')
                        ) <> ''
                ) AS pago_online

            FROM informes i

            LEFT JOIN sucursales s
                ON s.codigo = i.sucursal_codigo

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

        # ==========================================================
        # EVOLUCIÓN DIARIA
        # ==========================================================

        consulta_por_dia = f"""
            SELECT
                TO_CHAR(
                    i.fecha_creacion::date,
                    'DD/MM'
                ) AS fecha,

                COUNT(
                    DISTINCT COALESCE(
                        NULLIF(TRIM(i.id_pedido), ''),
                        i.id::text
                    )
                ) AS total

            FROM informes i

            LEFT JOIN sucursales s
                ON s.codigo = i.sucursal_codigo

            {where_sql}

            GROUP BY i.fecha_creacion::date
            ORDER BY i.fecha_creacion::date ASC
        """

        cur.execute(consulta_por_dia, parametros)
        pedidos_por_dia = cur.fetchall()

        # ==========================================================
        # PEDIDOS POR PROVINCIA
        # ==========================================================

        consulta_por_provincia = f"""
            SELECT
                COALESCE(
                    NULLIF(TRIM(s.provincia), ''),
                    'Sin provincia'
                ) AS provincia,

                COUNT(
                    DISTINCT COALESCE(
                        NULLIF(TRIM(i.id_pedido), ''),
                        i.id::text
                    )
                ) AS total

            FROM informes i

            LEFT JOIN sucursales s
                ON s.codigo = i.sucursal_codigo

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
                    NULLIF(TRIM(i.sucursal_codigo), ''),
                    'SIN SUCURSAL'
                ) AS sucursal,

                COUNT(
                    DISTINCT COALESCE(
                        NULLIF(TRIM(i.id_pedido), ''),
                        i.id::text
                    )
                ) AS total

            FROM informes i

            LEFT JOIN sucursales s
                ON s.codigo = i.sucursal_codigo

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
                            COALESCE(i.transportadora, '')
                        ) LIKE '%%retiro%%'

                        OR LOWER(
                            COALESCE(i.transportadora, '')
                        ) LIKE '%%pickup%%'

                        OR LOWER(
                            COALESCE(i.transportadora, '')
                        ) LIKE '%%tienda%%'

                    THEN 'Retiro en tienda'

                    WHEN
                        LOWER(
                            COALESCE(i.transportadora, '')
                        ) LIKE '%%envio%%'

                        OR LOWER(
                            COALESCE(i.transportadora, '')
                        ) LIKE '%%envío%%'

                        OR LOWER(
                            COALESCE(i.transportadora, '')
                        ) LIKE '%%express%%'

                        OR LOWER(
                            COALESCE(i.transportadora, '')
                        ) LIKE '%%domicilio%%'

                        OR LOWER(
                            COALESCE(i.transportadora, '')
                        ) LIKE '%%delivery%%'

                    THEN 'Envío a domicilio'

                    ELSE 'Sin definir'
                END AS modalidad,

                COUNT(
                    DISTINCT COALESCE(
                        NULLIF(TRIM(i.id_pedido), ''),
                        i.id::text
                    )
                ) AS total

            FROM informes i

            LEFT JOIN sucursales s
                ON s.codigo = i.sucursal_codigo

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
                            COALESCE(i.medio_pago, '')
                        ) LIKE '%%pago en tienda%%'

                        OR LOWER(
                            COALESCE(i.medio_pago, '')
                        ) LIKE '%%efectivo%%'

                        OR LOWER(
                            COALESCE(i.medio_pago, '')
                        ) LIKE '%%contra entrega%%'

                    THEN 'Pago en tienda'

                    WHEN
                        TRIM(
                            COALESCE(i.medio_pago, '')
                        ) <> ''

                    THEN 'Pago online'

                    ELSE 'Sin definir'
                END AS modalidad,

                COUNT(
                    DISTINCT COALESCE(
                        NULLIF(TRIM(i.id_pedido), ''),
                        i.id::text
                    )
                ) AS total

            FROM informes i

            LEFT JOIN sucursales s
                ON s.codigo = i.sucursal_codigo

            {where_sql}

            GROUP BY 1
            ORDER BY total DESC
        """

        cur.execute(consulta_por_pago, parametros)
        por_pago = cur.fetchall()

        # ==========================================================
        # SUCURSALES DISPONIBLES
        # ==========================================================

        cur.execute("""
            SELECT
                UPPER(TRIM(codigo)) AS sucursal

            FROM sucursales

            WHERE activa = TRUE
              AND codigo IS NOT NULL
              AND TRIM(codigo) <> ''

            ORDER BY codigo
        """)

        sucursales_disponibles = [
            fila["sucursal"]
            for fila in cur.fetchall()
            if fila["sucursal"]
        ]

        # ==========================================================
        # PROVINCIAS DISPONIBLES
        # ==========================================================

        cur.execute("""
            SELECT DISTINCT
                TRIM(provincia) AS provincia

            FROM sucursales

            WHERE activa = TRUE
              AND provincia IS NOT NULL
              AND TRIM(provincia) <> ''

            ORDER BY provincia
        """)

        provincias_disponibles = [
            fila["provincia"]
            for fila in cur.fetchall()
            if fila["provincia"]
        ]

        print("========== DEBUG DASHBOARD ==========", flush=True)
        print("WHERE SQL:", where_sql, flush=True)
        print("PARAMETROS:", parametros, flush=True)
        print("RESUMEN:", resumen, flush=True)
        print("POR DIA:", pedidos_por_dia, flush=True)
        print("POR PROVINCIA:", por_provincia, flush=True)
        print("POR SUCURSAL:", por_sucursal, flush=True)
        print("POR ENTREGA:", por_entrega, flush=True)
        print("POR PAGO:", por_pago, flush=True)
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