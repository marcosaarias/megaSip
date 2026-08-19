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


laboratorios_bp = Blueprint(
    "laboratorios",
    __name__,
)


# ============================================================
# GUARDAR / ACTUALIZAR LABORATORIOS
# ============================================================

def guardar_tabla_laboratorios_en_db(df):

    conn = get_db_connection()

    cursor = conn.cursor(
        cursor_factory=RealDictCursor
    )

    insertados = 0
    actualizados = 0
    omitidos = 0

    try:

        for _, row in df.iterrows():

            codigo = row.get("codigo")
            nombre = row.get("nombre")

            # ------------------------------------------------
            # VALIDAR VACIOS
            # ------------------------------------------------

            if (
                pd.isna(codigo)
                or pd.isna(nombre)
            ):
                omitidos += 1
                continue

            # ------------------------------------------------
            # NORMALIZAR CODIGO
            # ------------------------------------------------

            try:

                codigo = int(
                    float(
                        str(codigo).strip()
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
                INSERT INTO laboratorios (
                    codigo,
                    nombre
                )
                VALUES (%s, %s)

                ON CONFLICT (codigo)

                DO UPDATE SET
                    nombre = EXCLUDED.nombre

                RETURNING
                    (xmax = 0) AS insertado
                """,
                (
                    codigo,
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

        conn.commit()

        return {
            "insertados": insertados,
            "actualizados": actualizados,
            "omitidos": omitidos,
        }

    except Exception as error:

        conn.rollback()

        print(
            "ERROR GUARDANDO LABORATORIOS:",
            repr(error),
            flush=True,
        )

        raise

    finally:

        cursor.close()
        conn.close()


# ============================================================
# VISTA LABORATORIOS
# ============================================================

@laboratorios_bp.route(
    "/",
    methods=[
        "GET",
        "POST",
    ],
)
def laboratorios_view():

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
                    "laboratorios.laboratorios_view"
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
                        "laboratorios.laboratorios_view"
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
                "codigo",
                "nombre",
            }

            if not columnas_requeridas.issubset(
                df.columns
            ):

                print(
                    "COLUMNAS RECIBIDAS LABORATORIOS:",
                    df.columns.tolist(),
                    flush=True,
                )

                flash(
                    (
                        "El Excel debe contener "
                        "las columnas "
                        "'codigo' y 'nombre'."
                    ),
                    "danger",
                )

                return redirect(
                    url_for(
                        "laboratorios.laboratorios_view"
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
                "=== CARGA LABORATORIOS ===",
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
                            "codigo",
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
                guardar_tabla_laboratorios_en_db(
                    df
                )
            )

            print(
                "RESULTADO GUARDADO LABORATORIOS:",
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
                    "Tabla laboratorios actualizada "
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
                    "laboratorios.laboratorios_view"
                )
            )

        except ValueError as error:

            print(
                "ERROR VALIDANDO EXCEL LABORATORIOS:",
                repr(error),
                flush=True,
            )

            flash(
                (
                    "El archivo Excel no es válido: "
                    f"{error}"
                ),
                "danger",
            )

            return redirect(
                url_for(
                    "laboratorios.laboratorios_view"
                )
            )

        except Exception as error:

            print(
                "ERROR PROCESANDO LABORATORIOS:",
                repr(error),
                flush=True,
            )

            flash(
                (
                    "Error al procesar el archivo: "
                    f"{error}"
                ),
                "danger",
            )

            return redirect(
                url_for(
                    "laboratorios.laboratorios_view"
                )
            )

    # ========================================================
    # GET - CONSULTAR LABORATORIOS
    # ========================================================

    conn = get_db_connection()

    cursor = conn.cursor(
        cursor_factory=RealDictCursor
    )

    try:

        cursor.execute(
            """
            SELECT
                codigo,
                nombre
            FROM laboratorios
            ORDER BY codigo
            """
        )

        laboratorios = cursor.fetchall()

        print(
            "TOTAL LABORATORIOS:",
            len(laboratorios),
            flush=True,
        )

        print(
            "PRIMER LABORATORIO:",
            (
                laboratorios[0]
                if laboratorios
                else None
            ),
            flush=True,
        )

    except Exception as error:

        conn.rollback()

        print(
            "ERROR CONSULTANDO LABORATORIOS:",
            repr(error),
            flush=True,
        )

        flash(
            (
                "No se pudo consultar "
                "la tabla de laboratorios."
            ),
            "danger",
        )

        laboratorios = []

    finally:

        cursor.close()
        conn.close()

    # ========================================================
    # RENDER
    # ========================================================

    return render_template(
        "farmacia/laboratorios.html",
        laboratorios=laboratorios,
    )