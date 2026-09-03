from datetime import datetime

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
)

from psycopg2.extras import RealDictCursor

from database.db import get_db_connection
from sistemas import login_requerido


administrar_cenefas_farmacia_bp = Blueprint(
    "administrar_cenefas_farmacia",
    __name__,
    url_prefix="/farmacia/administrar-cenefas",
)


COLUMNAS_EDITABLES = {
    "troquel",
    "cod_barra",
    "descripcion",
    "normal",
    "oferta",
    "promo",
    "fecha_desde",
    "fecha_hasta",
    "tipo_cenefa",
}


TIPOS_CENEFA_VALIDOS = {
    "folder",
    "diarios",
    "nutricia",
}


# ============================================================
# UTILIDADES
# ============================================================

def normalizar_texto(valor):

    if valor is None:
        return ""

    return str(valor).strip()


def normalizar_precio(valor):

    valor = normalizar_texto(
        valor
    )

    if valor == "":
        return None

    valor = (
        valor
        .replace("$", "")
        .replace(" ", "")
    )

    if "," in valor and "." in valor:

        if valor.rfind(",") > valor.rfind("."):

            valor = (
                valor
                .replace(".", "")
                .replace(",", ".")
            )

        else:

            valor = valor.replace(
                ",",
                "",
            )

    elif "," in valor:

        valor = valor.replace(
            ",",
            ".",
        )

    try:

        numero = float(
            valor
        )

    except ValueError as error:

        raise ValueError(
            f"Precio inválido: {valor}"
        ) from error

    if numero < 0:

        raise ValueError(
            "Los precios no pueden ser negativos."
        )

    return numero


def validar_tipo_cenefa(valor):

    valor = (
        normalizar_texto(
            valor
        )
        .lower()
    )

    if valor not in TIPOS_CENEFA_VALIDOS:

        raise ValueError(
            f"Tipo de cenefa inválido: {valor}"
        )

    return valor


def validar_fecha(
    valor,
    nombre_campo,
):

    valor = normalizar_texto(
        valor
    )

    if not valor:

        raise ValueError(
            f"{nombre_campo} no puede estar vacía."
        )

    try:

        fecha = datetime.strptime(
            valor,
            "%Y-%m-%d",
        ).date()

    except ValueError as error:

        raise ValueError(
            f"{nombre_campo} no tiene "
            "un formato válido."
        ) from error

    return fecha


# ============================================================
# CONSULTAR REGISTROS
# ============================================================

def obtener_cenefas_farmacia(
    filtro_troquel="",
    filtro_descripcion="",
    filtro_tipo="",
):

    conn = get_db_connection()

    cursor = conn.cursor(
        cursor_factory=RealDictCursor
    )

    try:

        query = """
            SELECT
                id,
                troquel,
                cod_barra,
                descripcion,
                normal,
                oferta,
                promo,
                fecha_desde,
                fecha_hasta,
                tipo_cenefa,
                fecha_carga,
                lote_carga,
                usuario_carga
            FROM farmacia_folder
            WHERE 1 = 1
        """

        params = []

        if filtro_troquel:

            query += """
                AND troquel::text ILIKE %s
            """

            params.append(
                f"%{filtro_troquel}%"
            )

        if filtro_descripcion:

            query += """
                AND descripcion ILIKE %s
            """

            params.append(
                f"%{filtro_descripcion}%"
            )

        if filtro_tipo:

            query += """
                AND tipo_cenefa = %s
            """

            params.append(
                filtro_tipo
            )

        query += """
            ORDER BY
                fecha_carga DESC,
                id DESC
            LIMIT 1000
        """

        cursor.execute(
            query,
            params,
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        conn.close()


# ============================================================
# ACTUALIZAR REGISTRO
# ============================================================

def actualizar_cenefa_farmacia(
    registro_id,
    datos,
):

    try:

        registro_id = int(
            registro_id
        )

    except (
        TypeError,
        ValueError,
    ) as error:

        raise ValueError(
            "ID de registro inválido."
        ) from error


    troquel = normalizar_texto(
        datos.get(
            "troquel"
        )
    )

    cod_barra = normalizar_texto(
        datos.get(
            "cod_barra"
        )
    )

    descripcion = normalizar_texto(
        datos.get(
            "descripcion"
        )
    )

    promo = normalizar_texto(
        datos.get(
            "promo"
        )
    )

    fecha_desde = normalizar_texto(
        datos.get(
            "fecha_desde"
        )
    )

    fecha_hasta = normalizar_texto(
        datos.get(
            "fecha_hasta"
        )
    )

    tipo_cenefa = validar_tipo_cenefa(
        datos.get(
            "tipo_cenefa"
        )
    )

    normal = normalizar_precio(
        datos.get(
            "normal"
        )
    )

    oferta = normalizar_precio(
        datos.get(
            "oferta"
        )
    )


    # ========================================================
    # VALIDACIONES
    # ========================================================

    if not troquel:

        raise ValueError(
            "El troquel no puede estar vacío."
        )

    if not descripcion:

        raise ValueError(
            "La descripción no puede estar vacía."
        )


    desde_obj = validar_fecha(
        fecha_desde,
        "Fecha desde",
    )

    hasta_obj = validar_fecha(
        fecha_hasta,
        "Fecha hasta",
    )


    if desde_obj > hasta_obj:

        raise ValueError(
            "La fecha Desde no puede ser "
            "posterior a la fecha Hasta."
        )


    # ========================================================
    # BASE DE DATOS
    # ========================================================

    conn = get_db_connection()

    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            UPDATE farmacia_folder
            SET
                troquel = %s,
                cod_barra = %s,
                descripcion = %s,
                normal = %s,
                oferta = %s,
                promo = %s,
                fecha_desde = %s,
                fecha_hasta = %s,
                tipo_cenefa = %s
            WHERE id = %s
            """,
            (
                troquel,
                cod_barra,
                descripcion,
                normal,
                oferta,
                promo,
                fecha_desde,
                fecha_hasta,
                tipo_cenefa,
                registro_id,
            ),
        )

        if cursor.rowcount == 0:

            raise ValueError(
                "El registro no existe."
            )

        conn.commit()

    except Exception:

        conn.rollback()
        raise

    finally:

        cursor.close()
        conn.close()


# ============================================================
# ELIMINAR REGISTRO
# ============================================================

def eliminar_cenefa_farmacia(
    registro_id,
):

    try:

        registro_id = int(
            registro_id
        )

    except (
        TypeError,
        ValueError,
    ) as error:

        raise ValueError(
            "ID de registro inválido."
        ) from error


    conn = get_db_connection()

    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            DELETE FROM farmacia_folder
            WHERE id = %s
            """,
            (
                registro_id,
            ),
        )

        if cursor.rowcount == 0:

            raise ValueError(
                "El registro no existe."
            )

        conn.commit()

    except Exception:

        conn.rollback()
        raise

    finally:

        cursor.close()
        conn.close()


# ============================================================
# VISTA PRINCIPAL
# ============================================================

@administrar_cenefas_farmacia_bp.route(
    "/",
    methods=["GET"],
)
@login_requerido("adm-farmacia")
def administrar():

    filtro_troquel = (
        request.args.get(
            "troquel",
            "",
        )
        .strip()
    )

    filtro_descripcion = (
        request.args.get(
            "descripcion",
            "",
        )
        .strip()
    )

    filtro_tipo = (
        request.args.get(
            "tipo",
            "",
        )
        .strip()
        .lower()
    )


    if (
        filtro_tipo
        and filtro_tipo
        not in TIPOS_CENEFA_VALIDOS
    ):

        filtro_tipo = ""


    registros = obtener_cenefas_farmacia(
        filtro_troquel=(
            filtro_troquel
        ),
        filtro_descripcion=(
            filtro_descripcion
        ),
        filtro_tipo=(
            filtro_tipo
        ),
    )


    return render_template(
        "farmacia/administrar_cenefas.html",
        registros=registros,
        filtro_troquel=filtro_troquel,
        filtro_descripcion=(
            filtro_descripcion
        ),
        filtro_tipo=filtro_tipo,
        tipos_cenefa=sorted(
            TIPOS_CENEFA_VALIDOS
        ),
    )


# ============================================================
# GUARDAR CAMBIOS
# ============================================================

@administrar_cenefas_farmacia_bp.route(
    "/actualizar/<int:registro_id>",
    methods=["POST"],
)
@login_requerido("adm-farmacia")
def actualizar(
    registro_id,
):

    try:

        actualizar_cenefa_farmacia(
            registro_id=registro_id,
            datos=request.form,
        )

        return jsonify({
            "ok": True,
            "mensaje": (
                "Cenefa actualizada "
                "correctamente."
            ),
            "id": registro_id,
        }), 200


    except ValueError as error:

        return jsonify({
            "ok": False,
            "mensaje": str(
                error
            ),
            "id": registro_id,
        }), 400


    except Exception as error:

        print(
            "ERROR ACTUALIZANDO "
            "CENEFA FARMACIA:",
            repr(error),
            flush=True,
        )

        return jsonify({
            "ok": False,
            "mensaje": (
                "Ocurrió un error al "
                "actualizar la cenefa."
            ),
            "id": registro_id,
        }), 500


# ============================================================
# ELIMINAR
# ============================================================

@administrar_cenefas_farmacia_bp.route(
    "/eliminar/<int:registro_id>",
    methods=["POST"],
)
@login_requerido("adm-farmacia")
def eliminar(
    registro_id,
):

    try:

        eliminar_cenefa_farmacia(
            registro_id
        )

        flash(
            "Cenefa eliminada correctamente.",
            "success",
        )

    except ValueError as error:

        flash(
            str(error),
            "danger",
        )

    except Exception as error:

        print(
            "ERROR ELIMINANDO "
            "CENEFA FARMACIA:",
            repr(error),
            flush=True,
        )

        flash(
            (
                "Ocurrió un error al "
                "eliminar la cenefa."
            ),
            "danger",
        )


    return redirect(
        request.referrer
        or url_for(
            "administrar_cenefas_farmacia.administrar"
        )
    )