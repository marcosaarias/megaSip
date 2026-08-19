import pandas as pd

from flask import (
    Blueprint,
    render_template,
    request,
    flash,
    redirect,
    url_for,
)

from psycopg2.extras import RealDictCursor

from database.db import get_db_connection


subrubros_bp = Blueprint(
    "subrubros",
    __name__,
)


# ============================================================
# GUARDAR / ACTUALIZAR SUBRUBROS
# ============================================================

def guardar_tabla_subrubros_en_db(df):

    conn = get_db_connection()

    cursor = conn.cursor(
        cursor_factory=RealDictCursor
    )

    insertados = 0
    actualizados = 0
    omitidos = 0

    try:

        for _, row in df.iterrows():

            idsubrubro = row.get(
                "idsubrubro"
            )

            idrubro = row.get(
                "idrubro"
            )

            nombre = row.get(
                "nombre"
            )

            # ------------------------------------------------
            # VALIDAR VACIOS
            # ------------------------------------------------

            if (
                pd.isna(idsubrubro)
                or pd.isna(idrubro)
                or pd.isna(nombre)
            ):
                omitidos += 1
                continue

            # ------------------------------------------------
            # NORMALIZAR IDS
            # ------------------------------------------------

            try:

                idsubrubro = int(
                    float(
                        str(
                            idsubrubro
                        ).strip()
                    )
                )

                idrubro = int(
                    float(
                        str(
                            idrubro
                        ).strip()
                    )
                )

            except (
                TypeError,
                ValueError,
            ):
                omitidos += 1
                continue

            # ------------------------------------------------
            # NORMALIZAR NOMBRE
            # ------------------------------------------------

            nombre = str(
                nombre
            ).strip()

            if not nombre:
                omitidos += 1
                continue

            # ------------------------------------------------
            # INSERT / UPDATE
            # ------------------------------------------------

            cursor.execute(
                """
                INSERT INTO subrubros (
                    idsubrubro,
                    idrubro,
                    nombre
                )
                VALUES (%s, %s, %s)

                ON CONFLICT (idsubrubro)

                DO UPDATE SET
                    idrubro = EXCLUDED.idrubro,
                    nombre = EXCLUDED.nombre

                RETURNING
                    (xmax = 0) AS insertado
                """,
                (
                    idsubrubro,
                    idrubro,
                    nombre,
                ),
            )

            resultado = cursor.fetchone()

            fue_insertado = False

            if resultado:
                fue_insertado = bool(
                    resultado.get(
                        "insertado",
                        False,
                    )
                )

            if fue_insertado:
                insertados += 1
            else:
                actualizados += 1

        # ----------------------------------------------------
        # CONFIRMAR CAMBIOS
        # ----------------------------------------------------

        conn.commit()

        # ----------------------------------------------------
        # ACTUALIZAR SECUENCIA
        # ----------------------------------------------------

        cursor.execute(
            """
            SELECT setval(
                pg_get_serial_sequence(
                    'subrubros',
                    'idsubrubro'
                ),
                COALESCE(
                    (
                        SELECT MAX(idsubrubro)
                        FROM subrubros
                    ),
                    1
                ),
                true
            )
            """
        )

        conn.commit()

        return {
            "insertados": insertados,
            "actualizados": actualizados,
            "omitidos": omitidos,
        }

    except Exception as error:

        conn.rollback()

        print(
            "ERROR GUARDANDO SUBRUBROS:",
            repr(error),
            flush=True,
        )

        raise

    finally:

        cursor.close()
        conn.close()


# ============================================================
# VISTA SUBRUBROS
# ============================================================

@subrubros_bp.route(
    "/",
    methods=[
        "GET",
        "POST",
    ],
)
def subrubros_view():

    # ========================================================
    # POST - CARGAR EXCEL
    # ========================================================

    if request.method == "POST":

        archivo = request.files.get(
            "archivo"
        )

        if (
            not archivo
            or archivo.filename == ""
        ):

            flash(
                "Debe seleccionar un archivo Excel.",
                "danger",
            )

            return redirect(
                url_for(
                    "subrubros.subrubros_view"
                )
            )

        try:

            # ------------------------------------------------
            # LEER EXCEL
            # ------------------------------------------------

            df = pd.read_excel(
                archivo,
                dtype=object,
            )

            if df.empty:

                flash(
                    "El archivo Excel no contiene registros.",
                    "danger",
                )

                return redirect(
                    url_for(
                        "subrubros.subrubros_view"
                    )
                )

            # ------------------------------------------------
            # NORMALIZAR ENCABEZADOS
            # ------------------------------------------------

            df.columns = (
                df.columns
                .astype(str)
                .str.strip()
                .str.lower()
                .str.replace(
                    " ",
                    "_",
                    regex=False,
                )
            )

            # ------------------------------------------------
            # VALIDAR COLUMNAS
            # ------------------------------------------------

            columnas_requeridas = {
                "idsubrubro",
                "idrubro",
                "nombre",
            }

            if not columnas_requeridas.issubset(
                df.columns
            ):

                print(
                    "COLUMNAS RECIBIDAS SUBRUBROS:",
                    df.columns.tolist(),
                    flush=True,
                )

                flash(
                    (
                        "El Excel debe contener "
                        "las columnas "
                        "'idsubrubro', "
                        "'idrubro' y "
                        "'nombre'."
                    ),
                    "danger",
                )

                return redirect(
                    url_for(
                        "subrubros.subrubros_view"
                    )
                )

            # ------------------------------------------------
            # DEBUG TEMPORAL
            # ------------------------------------------------

            print(
                "================================",
                flush=True,
            )

            print(
                "=== CARGA SUBRUBROS ===",
                flush=True,
            )

            print(
                "ARCHIVO:",
                archivo.filename,
                flush=True,
            )

            print(
                "COLUMNAS:",
                df.columns.tolist(),
                flush=True,
            )

            print(
                "FILAS:",
                len(df),
                flush=True,
            )

            print(
                (
                    df[
                        [
                            "idsubrubro",
                            "idrubro",
                            "nombre",
                        ]
                    ]
                    .head(20)
                    .to_dict(
                        orient="records"
                    )
                ),
                flush=True,
            )

            # ------------------------------------------------
            # GUARDAR
            # ------------------------------------------------

            resultado = (
                guardar_tabla_subrubros_en_db(
                    df
                )
            )

            print(
                "RESULTADO GUARDADO SUBRUBROS:",
                resultado,
                flush=True,
            )

            print(
                "================================",
                flush=True,
            )

            # ------------------------------------------------
            # MENSAJE
            # ------------------------------------------------

            flash(
                (
                    "Tabla subrubros actualizada "
                    "correctamente. "
                    f"Insertados: "
                    f"{resultado['insertados']}. "
                    f"Actualizados: "
                    f"{resultado['actualizados']}. "
                    f"Omitidos: "
                    f"{resultado['omitidos']}."
                ),
                "success",
            )

            return redirect(
                url_for(
                    "subrubros.subrubros_view"
                )
            )

        except ValueError as error:

            print(
                "ERROR VALIDANDO EXCEL SUBRUBROS:",
                repr(error),
                flush=True,
            )

            flash(
                (
                    "El archivo Excel "
                    f"no es válido: {error}"
                ),
                "danger",
            )

            return redirect(
                url_for(
                    "subrubros.subrubros_view"
                )
            )

        except Exception as error:

            print(
                "ERROR PROCESANDO SUBRUBROS:",
                repr(error),
                flush=True,
            )

            flash(
                (
                    "Error al procesar "
                    f"el archivo: {error}"
                ),
                "danger",
            )

            return redirect(
                url_for(
                    "subrubros.subrubros_view"
                )
            )

    # ========================================================
    # GET - CONSULTAR SUBRUBROS
    # ========================================================

    conn = get_db_connection()

    cursor = conn.cursor(
        cursor_factory=RealDictCursor
    )

    try:

        cursor.execute(
            """
            SELECT
                s.idsubrubro,
                s.idrubro,
                s.nombre,
                r.nombre AS rubro
            FROM subrubros s

            LEFT JOIN rubros r
                ON r.idrubro = s.idrubro

            ORDER BY
                s.idsubrubro
            """
        )

        subrubros = cursor.fetchall()

        print(
            "TOTAL SUBRUBROS:",
            len(subrubros),
            flush=True,
        )

        print(
            "PRIMER SUBRUBRO:",
            (
                subrubros[0]
                if subrubros
                else None
            ),
            flush=True,
        )

    except Exception as error:

        conn.rollback()

        print(
            "ERROR CONSULTANDO SUBRUBROS:",
            repr(error),
            flush=True,
        )

        flash(
            (
                "No se pudo consultar "
                "la tabla de subrubros."
            ),
            "danger",
        )

        subrubros = []

    finally:

        cursor.close()
        conn.close()

    # ========================================================
    # RENDER
    # ========================================================

    return render_template(
        "farmacia/subrubros.html",
        subrubros=subrubros,
    )