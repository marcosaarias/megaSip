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


subrubros_bp = Blueprint("subrubros", __name__)


def guardar_tabla_subrubros_en_db(df):
    conn = get_db_connection()
    cursor = conn.cursor()

    insertados = 0
    actualizados = 0
    omitidos = 0

    try:
        for _, row in df.iterrows():
            idsubrubro = row.get("idsubrubro")
            idrubro = row.get("idrubro")
            nombre = row.get("nombre")

            if (
                pd.isna(idsubrubro)
                or pd.isna(idrubro)
                or pd.isna(nombre)
            ):
                omitidos += 1
                continue

            nombre = str(nombre).strip()

            if not nombre:
                omitidos += 1
                continue

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
                RETURNING (xmax = 0) AS insertado
                """,
                (
                    int(idsubrubro),
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

        # Actualiza la secuencia porque los IDs llegan desde Excel.
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

    except Exception:
        conn.rollback()
        raise

    finally:
        cursor.close()
        conn.close()


@subrubros_bp.route("/", methods=["GET", "POST"])
def subrubros_view():
    if request.method == "POST":
        archivo = request.files.get("archivo")

        if not archivo or archivo.filename == "":
            flash(
                "Debe seleccionar un archivo Excel.",
                "danger",
            )
            return redirect(
                url_for("subrubros.subrubros_view")
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
                "idsubrubro",
                "idrubro",
                "nombre",
            }

            if not columnas_requeridas.issubset(df.columns):
                flash(
                    (
                        "El Excel debe contener las columnas "
                        "'idsubrubro', 'idrubro' y 'nombre'."
                    ),
                    "danger",
                )
                return redirect(
                    url_for("subrubros.subrubros_view")
                )

            resultado = guardar_tabla_subrubros_en_db(df)

            flash(
                (
                    "Tabla subrubros actualizada correctamente. "
                    f"Insertados: {resultado['insertados']}. "
                    f"Actualizados: {resultado['actualizados']}. "
                    f"Omitidos: {resultado['omitidos']}."
                ),
                "success",
            )

            return redirect(
                url_for("subrubros.subrubros_view")
            )

        except ValueError as error:
            flash(
                f"El archivo Excel no es válido: {error}",
                "danger",
            )
            return redirect(
                url_for("subrubros.subrubros_view")
            )

        except Exception as error:
            print(
                "ERROR PROCESANDO SUBRUBROS:",
                repr(error),
                flush=True,
            )

            flash(
                f"Error al procesar el archivo: {error}",
                "danger",
            )

            return redirect(
                url_for("subrubros.subrubros_view")
            )

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
            ORDER BY s.idsubrubro
            """
        )

        subrubros = cursor.fetchall()

    except Exception as error:
        conn.rollback()

        print(
            "ERROR CONSULTANDO SUBRUBROS:",
            repr(error),
            flush=True,
        )

        flash(
            "No se pudo consultar la tabla de subrubros.",
            "danger",
        )

        subrubros = []

    finally:
        cursor.close()
        conn.close()

    return render_template(
        "farmacia/subrubros.html",
        subrubros=subrubros,
    )