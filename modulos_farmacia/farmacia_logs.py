from datetime import datetime

from flask import (
    Blueprint,
    render_template,
    request,
    session,
    redirect,
    url_for,
)

from psycopg2.extras import RealDictCursor

from database.db import get_db_connection


# ============================================================
# BLUEPRINT
# ============================================================

farmacia_logs_bp = Blueprint(
    "farmacia_logs",
    __name__,
    url_prefix="/farmacia/logs",
)


# ============================================================
# CONSTANTES
# ============================================================

MODULOS_VALIDOS = {
    "folder",
    "diarios",
    "nutricia",
}

ACCIONES_VALIDAS = {
    "procesar",
    "transmitir",
}

ESTADOS_VALIDOS = {
    "exitoso",
    "error",
}


# ============================================================
# NORMALIZAR TEXTO
# ============================================================

def limpiar_texto(valor):
    if valor is None:
        return None

    valor = str(valor).strip()

    if not valor:
        return None

    return valor


# ============================================================
# CONVERTIR TOTAL REGISTROS
# ============================================================

def limpiar_total_registros(valor):
    try:
        return int(valor or 0)

    except (TypeError, ValueError):
        return 0


# ============================================================
# GUARDAR LOG
# ============================================================

def guardar_log_farmacia(
    modulo,
    accion,
    estado,
    usuario=None,
    archivo=None,
    total_registros=0,
    fecha_desde=None,
    fecha_hasta=None,
    cache_id=None,
    lote_carga=None,
    detalle=None,
    error=None,
):
    """
    Registra un evento relacionado con el procesamiento
    o transmisión de archivos de Farmacia.

    IMPORTANTE:
    Un fallo al guardar el log NO debe romper el proceso
    principal de Farmacia.
    """

    modulo = limpiar_texto(modulo)
    accion = limpiar_texto(accion)
    estado = limpiar_texto(estado)

    if modulo:
        modulo = modulo.lower()

    if accion:
        accion = accion.lower()

    if estado:
        estado = estado.lower()

    # --------------------------------------------------------
    # VALIDACIONES
    # --------------------------------------------------------

    if modulo not in MODULOS_VALIDOS:
        print(
            "LOG FARMACIA - módulo inválido:",
            repr(modulo),
            flush=True,
        )
        return False

    if accion not in ACCIONES_VALIDAS:
        print(
            "LOG FARMACIA - acción inválida:",
            repr(accion),
            flush=True,
        )
        return False

    if estado not in ESTADOS_VALIDOS:
        print(
            "LOG FARMACIA - estado inválido:",
            repr(estado),
            flush=True,
        )
        return False

    usuario = limpiar_texto(usuario)
    archivo = limpiar_texto(archivo)
    cache_id = limpiar_texto(cache_id)
    lote_carga = limpiar_texto(lote_carga)
    detalle = limpiar_texto(detalle)
    error = limpiar_texto(error)

    total_registros = limpiar_total_registros(
        total_registros
    )

    conn = None
    cur = None

    try:

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO farmacia_transmisiones_log (
                modulo,
                accion,
                estado,
                usuario,
                archivo,
                total_registros,
                fecha_desde,
                fecha_hasta,
                cache_id,
                lote_carga,
                detalle,
                error,
                fecha_evento
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                CURRENT_TIMESTAMP
            )
            """,
            (
                modulo,
                accion,
                estado,
                usuario,
                archivo,
                total_registros,
                fecha_desde or None,
                fecha_hasta or None,
                cache_id,
                lote_carga,
                detalle,
                error,
            ),
        )

        conn.commit()

        print(
            "LOG FARMACIA GUARDADO:",
            f"modulo={modulo}",
            f"accion={accion}",
            f"estado={estado}",
            f"cache_id={cache_id}",
            flush=True,
        )

        return True

    except Exception as exc:

        if conn:
            conn.rollback()

        # MUY IMPORTANTE:
        # El log no debe hacer fallar una transmisión correcta.
        print(
            "ERROR GUARDANDO LOG FARMACIA:",
            repr(exc),
            flush=True,
        )

        return False

    finally:

        if cur:
            cur.close()

        if conn:
            conn.close()


# ============================================================
# OBTENER LOGS
# ============================================================

def obtener_logs_farmacia(
    modulo=None,
    estado=None,
    accion=None,
    usuario=None,
    fecha_desde=None,
    fecha_hasta=None,
    limite=500,
):
    conn = get_db_connection()

    cur = conn.cursor(
        cursor_factory=RealDictCursor
    )

    try:

        condiciones = []
        parametros = []

        # ----------------------------------------------------
        # MODULO
        # ----------------------------------------------------

        if modulo:

            condiciones.append(
                "LOWER(modulo) = LOWER(%s)"
            )

            parametros.append(modulo)

        # ----------------------------------------------------
        # ESTADO
        # ----------------------------------------------------

        if estado:

            condiciones.append(
                "LOWER(estado) = LOWER(%s)"
            )

            parametros.append(estado)

        # ----------------------------------------------------
        # ACCION
        # ----------------------------------------------------

        if accion:

            condiciones.append(
                "LOWER(accion) = LOWER(%s)"
            )

            parametros.append(accion)

        # ----------------------------------------------------
        # USUARIO
        # ----------------------------------------------------

        if usuario:

            condiciones.append(
                "usuario ILIKE %s"
            )

            parametros.append(
                f"%{usuario}%"
            )

        # ----------------------------------------------------
        # FECHA DESDE
        # ----------------------------------------------------

        if fecha_desde:

            condiciones.append(
                "fecha_evento::date >= %s"
            )

            parametros.append(
                fecha_desde
            )

        # ----------------------------------------------------
        # FECHA HASTA
        # ----------------------------------------------------

        if fecha_hasta:

            condiciones.append(
                "fecha_evento::date <= %s"
            )

            parametros.append(
                fecha_hasta
            )

        # ----------------------------------------------------
        # WHERE
        # ----------------------------------------------------

        where_sql = ""

        if condiciones:

            where_sql = (
                "WHERE "
                + " AND ".join(condiciones)
            )

        # ----------------------------------------------------
        # LIMITE
        # ----------------------------------------------------

        try:
            limite = int(limite)

        except (TypeError, ValueError):
            limite = 500

        limite = max(
            1,
            min(limite, 2000)
        )

        parametros.append(limite)

        # ----------------------------------------------------
        # CONSULTA
        # ----------------------------------------------------

        cur.execute(
            f"""
            SELECT
                id,
                modulo,
                accion,
                estado,
                usuario,
                archivo,
                total_registros,
                fecha_desde,
                fecha_hasta,
                cache_id,
                lote_carga,
                detalle,
                error,
                fecha_evento
            FROM farmacia_transmisiones_log

            {where_sql}

            ORDER BY
                fecha_evento DESC,
                id DESC

            LIMIT %s
            """,
            parametros,
        )

        return cur.fetchall()

    finally:

        cur.close()
        conn.close()


# ============================================================
# OBTENER KPIs
# ============================================================

def obtener_kpis_farmacia(
    fecha_desde=None,
    fecha_hasta=None,
):
    conn = get_db_connection()

    cur = conn.cursor(
        cursor_factory=RealDictCursor
    )

    try:

        condiciones = []
        parametros = []

        if fecha_desde:

            condiciones.append(
                "fecha_evento::date >= %s"
            )

            parametros.append(
                fecha_desde
            )

        if fecha_hasta:

            condiciones.append(
                "fecha_evento::date <= %s"
            )

            parametros.append(
                fecha_hasta
            )

        where_sql = ""

        if condiciones:

            where_sql = (
                "WHERE "
                + " AND ".join(condiciones)
            )

        cur.execute(
            f"""
            SELECT

                COUNT(*) FILTER (
                    WHERE
                        accion = 'procesar'
                        AND estado = 'exitoso'
                ) AS procesados,

                COUNT(*) FILTER (
                    WHERE
                        accion = 'transmitir'
                        AND estado = 'exitoso'
                ) AS transmitidos,

                COUNT(*) FILTER (
                    WHERE
                        estado = 'error'
                ) AS errores,

                COALESCE(
                    SUM(total_registros) FILTER (
                        WHERE
                            accion = 'transmitir'
                            AND estado = 'exitoso'
                    ),
                    0
                ) AS registros_transmitidos

            FROM farmacia_transmisiones_log

            {where_sql}
            """,
            parametros,
        )

        resultado = cur.fetchone()

        return resultado or {
            "procesados": 0,
            "transmitidos": 0,
            "errores": 0,
            "registros_transmitidos": 0,
        }

    finally:

        cur.close()
        conn.close()


# ============================================================
# PROCESADOS SIN TRANSMITIR
# ============================================================

def obtener_pendientes_transmision(
    fecha_desde=None,
    fecha_hasta=None,
):
    """
    Busca archivos que fueron procesados correctamente
    pero que todavía no tienen una transmisión exitosa
    asociada al mismo cache_id.
    """

    conn = get_db_connection()

    cur = conn.cursor(
        cursor_factory=RealDictCursor
    )

    try:

        condiciones = [
            "p.accion = 'procesar'",
            "p.estado = 'exitoso'",
            "p.cache_id IS NOT NULL",
        ]

        parametros = []

        if fecha_desde:

            condiciones.append(
                "p.fecha_evento::date >= %s"
            )

            parametros.append(
                fecha_desde
            )

        if fecha_hasta:

            condiciones.append(
                "p.fecha_evento::date <= %s"
            )

            parametros.append(
                fecha_hasta
            )

        where_sql = (
            " AND ".join(condiciones)
        )

        cur.execute(
            f"""
            SELECT
                p.id,
                p.modulo,
                p.usuario,
                p.archivo,
                p.total_registros,
                p.fecha_desde,
                p.fecha_hasta,
                p.cache_id,
                p.fecha_evento

            FROM farmacia_transmisiones_log p

            WHERE
                {where_sql}

                AND NOT EXISTS (
                    SELECT 1

                    FROM farmacia_transmisiones_log t

                    WHERE
                        t.cache_id = p.cache_id
                        AND t.modulo = p.modulo
                        AND t.accion = 'transmitir'
                        AND t.estado = 'exitoso'
                )

            ORDER BY
                p.fecha_evento DESC
            """,
            parametros,
        )

        return cur.fetchall()

    finally:

        cur.close()
        conn.close()


# ============================================================
# OBTENER RESUMEN POR PROCESO
# ============================================================

def obtener_resumen_procesos(
    fecha_desde=None,
    fecha_hasta=None,
    limite=200,
):
    """
    Devuelve una fila por cache_id.

    Permite representar:

        procesado -> transmitido
        procesado -> error
        procesado -> pendiente
    """

    conn = get_db_connection()

    cur = conn.cursor(
        cursor_factory=RealDictCursor
    )

    try:

        condiciones = [
            "cache_id IS NOT NULL"
        ]

        parametros = []

        if fecha_desde:

            condiciones.append(
                "fecha_evento::date >= %s"
            )

            parametros.append(
                fecha_desde
            )

        if fecha_hasta:

            condiciones.append(
                "fecha_evento::date <= %s"
            )

            parametros.append(
                fecha_hasta
            )

        where_sql = (
            "WHERE "
            + " AND ".join(condiciones)
        )

        try:
            limite = int(limite)

        except (TypeError, ValueError):
            limite = 200

        limite = max(
            1,
            min(limite, 1000)
        )

        parametros.append(limite)

        cur.execute(
            f"""
            SELECT
                cache_id,

                MAX(modulo) AS modulo,

                MAX(usuario) AS usuario,

                MAX(archivo) AS archivo,

                MAX(total_registros)
                    FILTER (
                        WHERE accion = 'procesar'
                    )
                    AS total_registros,

                MAX(fecha_desde)
                    AS fecha_desde,

                MAX(fecha_hasta)
                    AS fecha_hasta,

                MAX(fecha_evento)
                    FILTER (
                        WHERE
                            accion = 'procesar'
                            AND estado = 'exitoso'
                    )
                    AS fecha_procesado,

                MAX(fecha_evento)
                    FILTER (
                        WHERE
                            accion = 'transmitir'
                            AND estado = 'exitoso'
                    )
                    AS fecha_transmitido,

                BOOL_OR(
                    accion = 'procesar'
                    AND estado = 'exitoso'
                ) AS procesado_ok,

                BOOL_OR(
                    accion = 'transmitir'
                    AND estado = 'exitoso'
                ) AS transmitido_ok,

                BOOL_OR(
                    estado = 'error'
                ) AS tiene_error,

                MAX(error)
                    FILTER (
                        WHERE estado = 'error'
                    )
                    AS ultimo_error,

                MAX(lote_carga)
                    FILTER (
                        WHERE
                            accion = 'transmitir'
                            AND estado = 'exitoso'
                    )
                    AS lote_carga

            FROM farmacia_transmisiones_log

            {where_sql}

            GROUP BY
                cache_id

            ORDER BY
                MAX(fecha_evento) DESC

            LIMIT %s
            """,
            parametros,
        )

        procesos = cur.fetchall()

        # ----------------------------------------------------
        # ESTADO OPERATIVO
        # ----------------------------------------------------

        for proceso in procesos:

            if proceso["transmitido_ok"]:

                proceso[
                    "estado_operativo"
                ] = "transmitido"

            elif proceso["tiene_error"]:

                proceso[
                    "estado_operativo"
                ] = "error"

            elif proceso["procesado_ok"]:

                proceso[
                    "estado_operativo"
                ] = "pendiente"

            else:

                proceso[
                    "estado_operativo"
                ] = "desconocido"

        return procesos

    finally:

        cur.close()
        conn.close()


# ============================================================
# VISTA PRINCIPAL DE MONITOREO
# ============================================================

@farmacia_logs_bp.route("/")
def index():

    # --------------------------------------------------------
    # SEGURIDAD
    # --------------------------------------------------------

    rol = session.get(
        "usuario_rol"
    )

    roles_permitidos = {
        "sistemas",
        "adm-farmacia",
    }

    if rol not in roles_permitidos:

        return redirect(
            url_for("sistemas.login")
        )

    # --------------------------------------------------------
    # FILTROS
    # --------------------------------------------------------

    modulo = request.args.get(
        "modulo",
        "",
    ).strip().lower()

    estado = request.args.get(
        "estado",
        "",
    ).strip().lower()

    accion = request.args.get(
        "accion",
        "",
    ).strip().lower()

    usuario = request.args.get(
        "usuario",
        "",
    ).strip()

    fecha_desde = request.args.get(
        "desde",
        "",
    ).strip()

    fecha_hasta = request.args.get(
        "hasta",
        "",
    ).strip()

    # --------------------------------------------------------
    # LOGS
    # --------------------------------------------------------

    logs = obtener_logs_farmacia(
        modulo=modulo or None,
        estado=estado or None,
        accion=accion or None,
        usuario=usuario or None,
        fecha_desde=fecha_desde or None,
        fecha_hasta=fecha_hasta or None,
    )

    # --------------------------------------------------------
    # KPIs
    # --------------------------------------------------------

    kpis = obtener_kpis_farmacia(
        fecha_desde=fecha_desde or None,
        fecha_hasta=fecha_hasta or None,
    )

    # --------------------------------------------------------
    # PENDIENTES
    # --------------------------------------------------------

    pendientes = obtener_pendientes_transmision(
        fecha_desde=fecha_desde or None,
        fecha_hasta=fecha_hasta or None,
    )

    # --------------------------------------------------------
    # PROCESOS AGRUPADOS
    # --------------------------------------------------------

    procesos = obtener_resumen_procesos(
        fecha_desde=fecha_desde or None,
        fecha_hasta=fecha_hasta or None,
    )

    # --------------------------------------------------------
    # TEMPLATE
    # --------------------------------------------------------

    return render_template(
        "farmacia/logs.html",

        logs=logs,
        kpis=kpis,
        pendientes=pendientes,
        procesos=procesos,

        filtro_modulo=modulo,
        filtro_estado=estado,
        filtro_accion=accion,
        filtro_usuario=usuario,
        filtro_desde=fecha_desde,
        filtro_hasta=fecha_hasta,
    )