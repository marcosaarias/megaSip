import json

import psycopg2

from flask import (
    render_template,
    request,
    session,
)

from psycopg2.extras import RealDictCursor

from logs import guardar_log_compras
from sistemas import login_requerido


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


def registrar_rutas_administrar_cenefas(
    compras_bp,
    get_db_connection,
    limpiar_precio,
):

    # =========================================================
    # LISTADO / FILTROS
    # =========================================================

    @compras_bp.route(
        "/cenefas/administrar",
        methods=["GET"],
        endpoint="administrar_cenefas",
    )
    @login_requerido("compras")
    def administrar_cenefas():

        codigo = request.args.get(
            "codigo",
            "",
        ).strip()

        descripcion = request.args.get(
            "descripcion",
            "",
        ).strip()

        tipo = request.args.get(
            "tipo",
            "",
        ).strip()

        sucursal = request.args.get(
            "sucursal",
            "",
        ).strip()

        lote = request.args.get(
            "lote",
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

        except (TypeError, ValueError):
            pagina = 1

        offset = (
            pagina - 1
        ) * LIMITE_POR_PAGINA

        condiciones = [
            "1 = 1"
        ]

        parametros = []

        if codigo:
            condiciones.append(
                """
                (
                    codigo::text ILIKE %s
                    OR ean::text ILIKE %s
                )
                """
            )

            termino = f"%{codigo}%"

            parametros.extend(
                [
                    termino,
                    termino,
                ]
            )

        if descripcion:
            condiciones.append(
                "descripcion ILIKE %s"
            )

            parametros.append(
                f"%{descripcion}%"
            )

        if tipo:
            condiciones.append(
                "tipo_cenefa = %s"
            )

            parametros.append(
                tipo
            )

        if sucursal:
            condiciones.append(
                """
                (
                    sucursales = %s
                    OR
                    (
                        ',' || sucursales || ','
                    ) LIKE %s
                )
                """
            )

            parametros.extend(
                [
                    sucursal,
                    f"%,{sucursal},%",
                ]
            )

        if lote:
            condiciones.append(
                "lote_carga ILIKE %s"
            )

            parametros.append(
                f"%{lote}%"
            )

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

        conn = get_db_connection()

        cursor = conn.cursor(
            cursor_factory=RealDictCursor
        )

        try:

            # -----------------------------------------------
            # TOTAL
            # -----------------------------------------------

            cursor.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM cenefas
                WHERE {where_sql}
                """,
                parametros,
            )

            total = cursor.fetchone()[
                "total"
            ]

            # -----------------------------------------------
            # REGISTROS
            # -----------------------------------------------

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

            # -----------------------------------------------
            # TIPOS DISPONIBLES
            # -----------------------------------------------

            cursor.execute(
                """
                SELECT DISTINCT tipo_cenefa
                FROM cenefas
                WHERE tipo_cenefa IS NOT NULL
                  AND tipo_cenefa <> ''
                ORDER BY tipo_cenefa
                """
            )

            tipos = [
                fila["tipo_cenefa"]
                for fila
                in cursor.fetchall()
            ]

            # -----------------------------------------------
            # SUCURSALES
            # -----------------------------------------------

            cursor.execute(
                """
                SELECT DISTINCT sucursales
                FROM cenefas
                WHERE sucursales IS NOT NULL
                  AND sucursales <> ''
                ORDER BY sucursales
                """
            )

            destinos = [
                fila["sucursales"]
                for fila
                in cursor.fetchall()
            ]

        finally:

            cursor.close()
            conn.close()

        paginas = max(
            (
                total
                + LIMITE_POR_PAGINA
                - 1
            )
            // LIMITE_POR_PAGINA,
            1,
        )

        return render_template(
            "sucursales/administrar-cenefas.html",

            registros=registros,

            total=total,
            pagina=pagina,
            paginas=paginas,

            tipos=tipos,
            destinos=destinos,

            filtro_codigo=codigo,
            filtro_descripcion=descripcion,
            filtro_tipo=tipo,
            filtro_sucursal=sucursal,
            filtro_lote=lote,
            filtro_fecha_desde=fecha_desde,
            filtro_fecha_hasta=fecha_hasta,

            mensaje_error=None,
            mensaje_exito=None,
        )


    # =========================================================
    # ACTUALIZAR CENEFAS
    # =========================================================

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

            cambios = json.loads(
                cambios_json
            )

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

            if len(cambios) > MAX_CAMBIOS:
                raise ValueError(
                    "La cantidad de cambios "
                    "supera el máximo permitido."
                )

            conn = (
                get_db_connection()
            )

            cursor = conn.cursor()

            actualizados = 0

            try:

                for cambio in cambios:

                    if not isinstance(
                        cambio,
                        dict,
                    ):
                        raise ValueError(
                            "Se recibió un cambio "
                            "inválido."
                        )

                    id_cenefa = cambio.get(
                        "id"
                    )

                    columna = cambio.get(
                        "columna"
                    )

                    valor = cambio.get(
                        "valor"
                    )

                    # -------------------------------------
                    # VALIDAR ID
                    # -------------------------------------

                    try:
                        id_cenefa = int(
                            id_cenefa
                        )

                    except (
                        TypeError,
                        ValueError,
                    ):
                        raise ValueError(
                            "Se recibió un ID "
                            "de cenefa inválido."
                        )

                    # -------------------------------------
                    # WHITELIST DE COLUMNAS
                    # -------------------------------------

                    if (
                        columna
                        not in
                        COLUMNAS_EDITABLES
                    ):
                        raise ValueError(
                            f"No está permitido "
                            f"modificar {columna}."
                        )

                    # -------------------------------------
                    # PRECIOS
                    # -------------------------------------

                    if columna in {
                        "normal",
                        "oferta",
                    }:

                        valor = (
                            limpiar_precio(
                                valor
                            )
                        )

                        if valor is None:
                            raise ValueError(
                                "El precio recibido "
                                "no es válido."
                            )

                    # -------------------------------------
                    # TEXTO
                    # -------------------------------------

                    elif columna in {
                        "descripcion",
                        "cenefa",
                    }:

                        valor = str(
                            valor or ""
                        ).strip()

                        if len(valor) > 250:
                            raise ValueError(
                                f"El contenido de "
                                f"{columna} supera "
                                f"los 250 caracteres."
                            )

                    # -------------------------------------
                    # FECHAS
                    # -------------------------------------

                    elif columna in {
                        "desde",
                        "hasta",
                    }:

                        valor = str(
                            valor or ""
                        ).strip()

                        if not valor:
                            raise ValueError(
                                "La vigencia no puede "
                                "quedar vacía."
                            )

                    # -------------------------------------
                    # UPDATE
                    # columna es segura porque pasó
                    # por COLUMNAS_EDITABLES
                    # -------------------------------------

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

                    if cursor.rowcount != 1:
                        raise ValueError(
                            f"No se encontró la "
                            f"cenefa ID {id_cenefa}."
                        )

                    actualizados += 1

                conn.commit()

            except Exception:

                conn.rollback()
                raise

            finally:

                cursor.close()
                conn.close()

            guardar_log_compras(
                usuario=usuario,
                nivel="INFO",
                origen="backend",
                modulo="administrar_cenefas",
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
                total_registros=actualizados,
            )

            mensaje = (
                f"Se guardaron correctamente "
                f"{actualizados} modificaciones."
            )

            return (
                mensaje,
                200,
            )

        except psycopg2.Error as error:

            guardar_log_compras(
                usuario=usuario,
                nivel="CRITICAL",
                origen="base_datos",
                modulo="administrar_cenefas",
                accion=(
                    "Error actualizando cenefas"
                ),
                detalle=str(error),
                estado="fallido",
                total_registros=0,
            )

            return (
                f"Error de base de datos: "
                f"{error}",
                500,
            )

        except Exception as error:

            guardar_log_compras(
                usuario=usuario,
                nivel="ERROR",
                origen="backend",
                modulo="administrar_cenefas",
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