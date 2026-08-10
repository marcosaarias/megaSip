import json
from datetime import datetime

import pandas as pd
import psycopg2

from flask import (
    render_template,
    request,
    session,
)

from psycopg2.extras import RealDictCursor

from logs import guardar_log_compras
from sistemas import login_requerido


# ============================================================
# CONFIGURACION
# ============================================================

COLUMNAS_EDITABLES = {
    "descripcion",
    "normal",
    "oferta",
    "cenefa",
    "desde",
    "hasta",
}

LIMITE_POR_PAGINA = 200
MAX_CAMBIOS = 2000


# ============================================================
# VALIDACIONES
# ============================================================

def validar_fecha(valor):
    """
    Valida una fecha recibida desde el formulario HTML.
    Retorna YYYY-MM-DD.
    """

    valor = str(valor or "").strip()

    if not valor:
        raise ValueError(
            "La fecha no puede quedar vacía."
        )

    try:
        fecha = datetime.strptime(
            valor,
            "%Y-%m-%d",
        ).date()

    except ValueError as error:
        raise ValueError(
            f"La fecha '{valor}' no tiene "
            f"un formato válido."
        ) from error

    return fecha.isoformat()


def validar_precio(valor, limpiar_precio):
    """
    Normaliza un precio utilizando la función general
    de compras.py y evita guardar NaN en PostgreSQL.
    """

    precio = limpiar_precio(valor)

    if precio is None:
        raise ValueError(
            "El precio recibido no es válido."
        )

    try:
        if pd.isna(precio):
            raise ValueError(
                "El precio recibido no es válido."
            )

    except TypeError:
        pass

    if precio < 0:
        raise ValueError(
            "El precio no puede ser negativo."
        )

    return precio


# ============================================================
# REGISTRO DE RUTAS
# ============================================================

def registrar_rutas_administrar_cenefas(
    compras_bp,
    get_db_connection,
    limpiar_precio,
):

    # ========================================================
    # ADMINISTRAR CENEFAS
    # ========================================================

    @compras_bp.route(
        "/cenefas/administrar",
        methods=["GET"],
        endpoint="administrar_cenefas",
    )
    @login_requerido("compras")
    def administrar_cenefas():

        # ----------------------------------------------------
        # FILTROS
        # ----------------------------------------------------

        codigo = request.args.get(
            "codigo",
            "",
        ).strip()

        fecha_desde = request.args.get(
            "fecha_desde",
            "",
        ).strip()

        fecha_hasta = request.args.get(
            "fecha_hasta",
            "",
        ).strip()

        # ----------------------------------------------------
        # PAGINACION
        # ----------------------------------------------------

        try:
            pagina = max(
                int(
                    request.args.get(
                        "pagina",
                        1,
                    )
                ),
                1,
            )

        except (
            TypeError,
            ValueError,
        ):
            pagina = 1

        offset = (
            pagina - 1
        ) * LIMITE_POR_PAGINA

        # ----------------------------------------------------
        # CONSTRUCCION DE FILTROS SQL
        # ----------------------------------------------------

        condiciones = [
            "1 = 1",
        ]

        parametros = []

        # ====================================================
        # CODIGO / EAN
        # ====================================================

        if codigo:

            termino = (
                f"%{codigo}%"
            )

            condiciones.append(
                """
                (
                    codigo::text ILIKE %s
                    OR
                    ean::text ILIKE %s
                )
                """
            )

            parametros.extend(
                [
                    termino,
                    termino,
                ]
            )

        # ====================================================
        # VIGENCIA
        #
        # Ejemplo:
        #
        # Buscar 10/08 - 16/08
        #
        # Una cenefa se muestra si su período se cruza
        # con el período buscado.
        # ====================================================

        if fecha_desde:

            condiciones.append(
                "hasta >= %s"
            )

            parametros.append(
                fecha_desde
            )

        if fecha_hasta:

            condiciones.append(
                "desde <= %s"
            )

            parametros.append(
                fecha_hasta
            )

        where_sql = (
            " AND ".join(
                condiciones
            )
        )

        # ----------------------------------------------------
        # BASE DE DATOS
        # ----------------------------------------------------

        conn = get_db_connection()

        cursor = conn.cursor(
            cursor_factory=RealDictCursor
        )

        try:

            # =================================================
            # TOTAL DE REGISTROS
            # =================================================

            cursor.execute(
                f"""
                SELECT
                    COUNT(*) AS total
                FROM cenefas
                WHERE {where_sql}
                """,
                parametros,
            )

            resultado_total = (
                cursor.fetchone()
            )

            total = (
                resultado_total["total"]
                if resultado_total
                else 0
            )

            # =================================================
            # LISTADO
            # =================================================

            parametros_listado = (
                parametros.copy()
            )

            parametros_listado.extend(
                [
                    LIMITE_POR_PAGINA,
                    offset,
                ]
            )

            cursor.execute(
                f"""
                SELECT
                    id,
                    codigo,
                    ean,
                    dep,
                    departamento,
                    descripcion,
                    normal,
                    oferta,
                    cenefa,
                    desde,
                    hasta,
                    sucursales,
                    tipo_cenefa,
                    fecha_carga,
                    lote_carga,
                    usuario_carga
                FROM cenefas
                WHERE {where_sql}
                ORDER BY
                    fecha_carga DESC,
                    id DESC
                LIMIT %s
                OFFSET %s
                """,
                parametros_listado,
            )

            registros = (
                cursor.fetchall()
            )

        finally:

            cursor.close()
            conn.close()

        # ----------------------------------------------------
        # PAGINAS
        # ----------------------------------------------------

        paginas = max(
            (
                total
                + LIMITE_POR_PAGINA
                - 1
            )
            // LIMITE_POR_PAGINA,
            1,
        )

        # Evita pedir páginas inexistentes.
        if pagina > paginas:
            pagina = paginas

        return render_template(
            "sucursales/administrar-cenefas.html",

            registros=registros,

            total=total,
            pagina=pagina,
            paginas=paginas,

            filtro_codigo=codigo,
            filtro_fecha_desde=fecha_desde,
            filtro_fecha_hasta=fecha_hasta,

            mensaje_error=None,
            mensaje_exito=None,
        )


    # ========================================================
    # ACTUALIZAR CENEFAS
    # ========================================================

    @compras_bp.route(
        "/cenefas/administrar/actualizar",
        methods=["POST"],
        endpoint="actualizar_cenefas",
    )
    @login_requerido("compras")
    def actualizar_cenefas():

        usuario = session.get(
            "usuario_nombre",
            "desconocido",
        )

        cambios_json = (
            request.form.get(
                "cambios",
                "[]",
            )
        )

        try:

            # =================================================
            # DECODIFICAR JSON
            # =================================================

            try:
                cambios = json.loads(
                    cambios_json
                )

            except json.JSONDecodeError as error:
                raise ValueError(
                    "No se pudieron interpretar "
                    "las modificaciones."
                ) from error

            if not isinstance(
                cambios,
                list,
            ):
                raise ValueError(
                    "El formato de cambios "
                    "no es válido."
                )

            if not cambios:
                raise ValueError(
                    "No existen cambios "
                    "para guardar."
                )

            if (
                len(cambios)
                > MAX_CAMBIOS
            ):
                raise ValueError(
                    "La cantidad de cambios "
                    "supera el máximo permitido."
                )

            # =================================================
            # BASE DE DATOS
            # =================================================

            conn = (
                get_db_connection()
            )

            cursor = (
                conn.cursor()
            )

            actualizados = 0

            try:

                for cambio in cambios:

                    # -----------------------------------------
                    # ESTRUCTURA DEL CAMBIO
                    # -----------------------------------------

                    if not isinstance(
                        cambio,
                        dict,
                    ):
                        raise ValueError(
                            "Se recibió una "
                            "modificación inválida."
                        )

                    id_cenefa = (
                        cambio.get("id")
                    )

                    columna = (
                        cambio.get(
                            "columna"
                        )
                    )

                    valor = (
                        cambio.get(
                            "valor"
                        )
                    )

                    # -----------------------------------------
                    # ID
                    # -----------------------------------------

                    try:
                        id_cenefa = int(
                            id_cenefa
                        )

                    except (
                        TypeError,
                        ValueError,
                    ) as error:

                        raise ValueError(
                            "Se recibió un ID "
                            "de cenefa inválido."
                        ) from error

                    if id_cenefa <= 0:
                        raise ValueError(
                            "El ID de cenefa "
                            "no es válido."
                        )

                    # -----------------------------------------
                    # WHITELIST
                    # -----------------------------------------

                    if (
                        columna
                        not in
                        COLUMNAS_EDITABLES
                    ):
                        raise ValueError(
                            f"No está permitido "
                            f"modificar la columna "
                            f"'{columna}'."
                        )

                    # -----------------------------------------
                    # PRECIOS
                    # -----------------------------------------

                    if columna in {
                        "normal",
                        "oferta",
                    }:

                        valor = validar_precio(
                            valor,
                            limpiar_precio,
                        )

                    # -----------------------------------------
                    # TEXTO
                    # -----------------------------------------

                    elif columna in {
                        "descripcion",
                        "cenefa",
                    }:

                        valor = str(
                            valor or ""
                        ).strip()

                        if (
                            len(valor)
                            > 250
                        ):
                            raise ValueError(
                                f"El contenido de "
                                f"{columna} supera "
                                f"los 250 caracteres."
                            )

                    # -----------------------------------------
                    # FECHAS
                    # -----------------------------------------

                    elif columna in {
                        "desde",
                        "hasta",
                    }:

                        valor = validar_fecha(
                            valor
                        )

                    # -----------------------------------------
                    # UPDATE
                    #
                    # El nombre de columna es seguro
                    # porque pasó por COLUMNAS_EDITABLES.
                    # -----------------------------------------

                    cursor.execute(
                        f"""
                        UPDATE cenefas
                        SET {columna} = %s
                        WHERE id = %s
                        """,
                        (
                            valor,
                            id_cenefa,
                        ),
                    )

                    if (
                        cursor.rowcount
                        != 1
                    ):
                        raise ValueError(
                            f"No se encontró "
                            f"la cenefa con ID "
                            f"{id_cenefa}."
                        )

                    actualizados += 1

                # =================================================
                # VALIDAR RANGO DE FECHAS
                # =================================================

                ids_modificados = list(
                    {
                        int(cambio["id"])
                        for cambio in cambios
                        if cambio.get("id")
                    }
                )

                if ids_modificados:

                    cursor.execute(
                        """
                        SELECT
                            id,
                            desde,
                            hasta
                        FROM cenefas
                        WHERE id = ANY(%s)
                        """,
                        (
                            ids_modificados,
                        ),
                    )

                    fechas = (
                        cursor.fetchall()
                    )

                    for (
                        id_registro,
                        desde,
                        hasta,
                    ) in fechas:

                        if (
                            desde
                            and hasta
                            and desde > hasta
                        ):
                            raise ValueError(
                                f"La cenefa ID "
                                f"{id_registro} tiene "
                                f"una vigencia inválida: "
                                f"Desde es posterior "
                                f"a Hasta."
                            )

                conn.commit()

            except Exception:

                conn.rollback()
                raise

            finally:

                cursor.close()
                conn.close()

            # =================================================
            # LOG
            # =================================================

            guardar_log_compras(
                usuario=usuario,
                nivel="INFO",
                origen="backend",
                modulo=(
                    "administrar_cenefas"
                ),
                accion=(
                    "Modificar cenefas "
                    "transmitidas"
                ),
                detalle=(
                    f"Se guardaron "
                    f"{actualizados} "
                    f"modificaciones."
                ),
                estado="exitoso",
                total_registros=(
                    actualizados
                ),
            )

            mensaje = (
                f"Se guardaron correctamente "
                f"{actualizados} modificaciones."
            )

            return (
                mensaje,
                200,
            )

        # =====================================================
        # ERROR POSTGRESQL
        # =====================================================

        except psycopg2.Error as error:

            guardar_log_compras(
                usuario=usuario,
                nivel="CRITICAL",
                origen="base_datos",
                modulo=(
                    "administrar_cenefas"
                ),
                accion=(
                    "Error actualizando cenefas"
                ),
                detalle=str(error),
                estado="fallido",
                total_registros=0,
            )

            return (
                "Error de base de datos: "
                f"{error}",
                500,
            )

        # =====================================================
        # OTROS ERRORES
        # =====================================================

        except Exception as error:

            guardar_log_compras(
                usuario=usuario,
                nivel="ERROR",
                origen="backend",
                modulo=(
                    "administrar_cenefas"
                ),
                accion=(
                    "Error actualizando cenefas"
                ),
                detalle=str(error),
                estado="fallido",
                total_registros=0,
            )

            return (
                str(error),
                400,
            )