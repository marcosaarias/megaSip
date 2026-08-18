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


rubros_bp = Blueprint("rubros", __name__)


def guardar_tabla_rubros_en_db(df):
    conn = get_db_connection()
    cursor = conn.cursor()

    insertados = 0
    actualizados = 0
    omitidos = 0

    try:
        for _, row in df.iterrows():
            idrubro = row.get("idrubro")
            nombre = row.get("nombre")

            if pd.isna(idrubro) or pd.isna(nombre):
                omitidos += 1
                continue

            nombre = str(nombre).strip()

            if not nombre:
                omitidos += 1
                continue

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
                RETURNING (xmax = 0) AS insertado
                """,
                (
                    int(idrubro),
                    nombre,
                ),
            )

            resultado = cursor.fetchone()

            if resultado and resultado[0]:
                insertados += 1
            else:
                actualizados += 1

        conn.commit()

        # Como se insertan IDs manualmente, se actualiza la secuencia.
        cursor.execute(
            """
            SELECT setval(
                pg_get_serial_sequence('rubros', 'idrubro'),
                COALESCE(
                    (SELECT MAX(idrubro) FROM rubros),
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

    except Exception:
        conn.rollback()
        raise

    finally:
        cursor.close()
        conn.close()


@rubros_bp.route("/", methods=["GET", "POST"])
def rubros_view():
    if request.method == "POST":
        archivo = request.files.get("archivo")

        if not archivo or archivo.filename == "":
            flash(
                "Debe seleccionar un archivo Excel.",
                "danger",
            )
            return redirect(
                url_for("rubros.rubros_view")
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
                "idrubro",
                "nombre",
            }

            if not columnas_requeridas.issubset(df.columns):
                flash(
                    (
                        "El Excel debe contener las columnas "
                        "'idrubro' y 'nombre'."
                    ),
                    "danger",
                )
                return redirect(
                    url_for("rubros.rubros_view")
                )

            resultado = guardar_tabla_rubros_en_db(df)

            flash(
                (
                    "Tabla rubros actualizada correctamente. "
                    f"Insertados: {resultado['insertados']}. "
                    f"Actualizados: {resultado['actualizados']}. "
                    f"Omitidos: {resultado['omitidos']}."
                ),
                "success",
            )

            return redirect(
                url_for("rubros.rubros_view")
            )

        except ValueError as error:
            flash(
                f"El archivo Excel no es válido: {error}",
                "danger",
            )

            return redirect(
                url_for("rubros.rubros_view")
            )

        except Exception as error:
            print(
                "ERROR PROCESANDO RUBROS:",
                repr(error),
                flush=True,
            )

            flash(
                f"Error al procesar el archivo: {error}",
                "danger",
            )

            return redirect(
                url_for("rubros.rubros_view")
            )

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

        rubros = cursor.fetchall()

        print(
            "TOTAL RUBROS:",
            len(rubros),
            flush=True,
        )

        print(
            "PRIMER RUBRO:",
            rubros[0] if rubros else None,
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
            "No se pudo consultar la tabla de rubros.",
            "danger",
        )

        rubros = []

    finally:
        cursor.close()
        conn.close()

    return render_template(
        "farmacia/rubros.html",
        rubros=rubros,
    )