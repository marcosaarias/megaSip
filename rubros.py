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


rubros_bp = Blueprint(
    "rubros",
    __name__,
)


# ============================================================
# GUARDAR / ACTUALIZAR RUBROS
# ============================================================

def guardar_tabla_rubros_en_db(df):

    conn = get_db_connection()

    # Usamos RealDictCursor explícitamente para que
    # RETURNING pueda leerse por nombre.
    cursor = conn.cursor(
        cursor_factory=RealDictCursor
    )

    insertados = 0
    actualizados = 0
    omitidos = 0

    try:

        for _, row in df.iterrows():

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
                pd.isna(idrubro)
                or pd.isna(nombre)
            ):
                omitidos += 1
                continue

            # ------------------------------------------------
            # NORMALIZAR ID
            # ------------------------------------------------

            try:

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
                INSERT INTO rubros (
                    idrubro,
                    nombre
                )
                VALUES (%s, %s)

                ON CONFLICT (idrubro)
                DO UPDATE SET
                    nombre = EXCLUDED.nombre

                RETURNING
                    (xmax = 0) AS insertado
                """,
                (
                    idrubro,
                    nombre,
                ),
            )

            resultado = (
                cursor.fetchone()
            )

            # ------------------------------------------------
            # IMPORTANTE:
            # resultado es un diccionario RealDictRow.
            # ------------------------------------------------

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
        # CONFIRMAR INSERT / UPDATE
        # ----------------------------------------------------

        conn.commit()

        # ----------------------------------------------------
        # ACTUALIZAR SECUENCIA
        # ----------------------------------------------------

        cursor.execute(
            """
            SELECT setval(
                pg_get_serial_sequence(
                    'rubros',
                    'idrubro'
                ),
                COALESCE(
                    (
                        SELECT MAX(idrubro)
                        FROM rubros
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
            "ERROR GUARDANDO RUBROS:",
            repr(error),
            flush=True,
        )

        raise

    finally:

        cursor.close()
        conn.close()


# ============================================================
# RUTA RUBROS
# ============================================================

@rubros_bp.route(
    "/",
    methods=[
        "GET",
        "POST",
    ],
)
def rubros_view():

    # ========================================================
    # POST - CARGAR EXCEL
    # ========================================================

    if request.method == "POST":

        archivo = request.files.get(
            "archivo"
        )

        # ----------------------------------------------------
        # VALIDAR ARCHIVO
        # ----------------------------------------------------

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
                    "rubros.rubros_view"
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

            # ------------------------------------------------
            # VALIDAR QUE TENGA FILAS
            # ------------------------------------------------

            if df.empty:

                flash(
                    "El archivo Excel no contiene registros.",
                    "danger",
                )

                return redirect(
                    url_for(
                        "rubros.rubros_view"
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
            # COLUMNAS REQUERIDAS
            # ------------------------------------------------

            columnas_requeridas = {
                "idrubro",
                "nombre",
            }

            if not columnas_requeridas.issubset(
                df.columns
            ):

                print(
                    "COLUMNAS RECIBIDAS:",
                    df.columns.tolist(),
                    flush=True,
                )

                flash(
                    (
                        "El Excel debe contener "
                        "las columnas "
                        "'idrubro' y 'nombre'."
                    ),
                    "danger",
                )

                return redirect(
                    url_for(
                        "rubros.rubros_view"
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
                "=== CARGA RUBROS ===",
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
                "DATOS:",
                (
                    df[
                        [
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
            # GUARDAR EN POSTGRESQL
            # ------------------------------------------------

            resultado = (
                guardar_tabla_rubros_en_db(
                    df
                )
            )

            print(
                "RESULTADO GUARDADO:",
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
                    "Tabla rubros actualizada "
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

            # ------------------------------------------------
            # POST / REDIRECT / GET
            # ------------------------------------------------

            return redirect(
                url_for(
                    "rubros.rubros_view"
                )
            )

        except ValueError as error:

            print(
                "ERROR VALIDANDO EXCEL RUBROS:",
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
                    "rubros.rubros_view"
                )
            )

        except Exception as error:

            print(
                "ERROR PROCESANDO RUBROS:",
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
                    "rubros.rubros_view"
                )
            )

    # ========================================================
    # GET - CONSULTAR RUBROS ACTUALES
    # ========================================================

    conn = get_db_connection()

    cursor = conn.cursor(
        cursor_factory=RealDictCursor
    )

    try:

        cursor.execute(
            """
            SELECT
                idrubro,
                nombre
            FROM rubros
            ORDER BY idrubro
            """
        )

        rubros = (
            cursor.fetchall()
        )

        print(
            "TOTAL RUBROS:",
            len(rubros),
            flush=True,
        )

        print(
            "PRIMER RUBRO:",
            (
                rubros[0]
                if rubros
                else None
            ),
            flush=True,
        )

    except Exception as error:

        conn.rollback()

        print(
            "ERROR CONSULTANDO RUBROS:",
            repr(error),
            flush=True,
        )

        flash(
            (
                "No se pudo consultar "
                "la tabla de rubros."
            ),
            "danger",
        )

        rubros = []

    finally:

        cursor.close()
        conn.close()

    # ========================================================
    # RENDERIZAR
    # ========================================================

    return render_template(
        "farmacia/rubros.html",
        rubros=rubros,
    )