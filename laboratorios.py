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


def guardar_tabla_laboratorios_en_db(df):
    conn = get_db_connection()
    cursor = conn.cursor()

    insertados = 0
    actualizados = 0
    omitidos = 0

    try:
        for _, row in df.iterrows():
            codigo = row.get("codigo")
            nombre = row.get("nombre")

            if pd.isna(codigo) or pd.isna(nombre):
                omitidos += 1
                continue

            nombre = str(nombre).strip()

            if not nombre:
                omitidos += 1
                continue

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
                RETURNING (xmax = 0) AS insertado
                """,
                (
                    int(codigo),
                    nombre,
                ),
            )

            resultado = cursor.fetchone()

            if resultado and resultado[0]:
                insertados += 1
            else:
                actualizados += 1

        conn.commit()

        return {
            "insertados": insertados,
            "actualizados": actualizados,
            "omitidos": omitidos,
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        cursor.close()
        conn.close()


@laboratorios_bp.route("/", methods=["GET", "POST"])
def laboratorios_view():
    if request.method == "POST":
        archivo = request.files.get("archivo")

        if not archivo or archivo.filename == "":
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
            df = pd.read_excel(
                archivo,
                dtype=object,
            )

            df.columns = (
                df.columns
                .astype(str)
                .str.strip()
                .str.lower()
                .str.replace(" ", "_", regex=False)
            )

            columnas_requeridas = {
                "codigo",
                "nombre",
            }

            if not columnas_requeridas.issubset(
                df.columns
            ):
                flash(
                    (
                        "El Excel debe contener las columnas "
                        "'codigo' y 'nombre'."
                    ),
                    "danger",
                )

                return redirect(
                    url_for(
                        "laboratorios.laboratorios_view"
                    )
                )

            resultado = (
                guardar_tabla_laboratorios_en_db(df)
            )

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

    except Exception as error:
        conn.rollback()

        print(
            "ERROR CONSULTANDO LABORATORIOS:",
            repr(error),
            flush=True,
        )

        flash(
            (
                "No se pudo consultar la tabla "
                "de laboratorios."
            ),
            "danger",
        )

        laboratorios = []

    finally:
        cursor.close()
        conn.close()

    return render_template(
        "farmacia/laboratorios.html",
        laboratorios=laboratorios,
    )