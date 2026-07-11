import os
import sqlite3

from flask import Blueprint, render_template, request


balanza_bp = Blueprint(
    "balanza",
    __name__,
    url_prefix="/balanza"
)


SUCURSALES_BALANZA = {
     "CO01": os.getenv("IP_BALANZAS_CO01"),
     "CO02": os.getenv("IP_BALANZAS_CO02"),
     "CO04": os.getenv("IP_BALANZAS_CO04"),
     "CO05": os.getenv("IP_BALANZAS_CO05"),
     "CO06": os.getenv("IP_BALANZAS_CO06"),
     "CO07": os.getenv("IP_BALANZAS_CO07"),
     "CO08": os.getenv("IP_BALANZAS_CO08"),
     "CO09": os.getenv("IP_BALANZAS_CO09"),
     "CO10": os.getenv("IP_BALANZAS_CO10"),
     "CO11": os.getenv("IP_BALANZAS_CO11"),
     "CO12": os.getenv("IP_BALANZAS_CO12"),
     "CO13": os.getenv("IP_BALANZAS_CO13"),
     "CO14": os.getenv("IP_BALANZAS_CO14"),
     "CO15": os.getenv("IP_BALANZAS_CO15"),
     "CO16": os.getenv("IP_BALANZAS_CO16"),
     "CO17": os.getenv("IP_BALANZAS_CO17"),
     "CO18": os.getenv("IP_BALANZAS_CO18"),
     "CO19": os.getenv("IP_BALANZAS_CO19"),
     "CO20": os.getenv("IP_BALANZAS_CO20"),
     "CO21": os.getenv("IP_BALANZAS_CO21"),
     "CO22": os.getenv("IP_BALANZAS_CO22"),
     "CO23": os.getenv("IP_BALANZAS_CO23"),
     "CO24": os.getenv("IP_BALANZAS_CO24"),
     "CO25": os.getenv("IP_BALANZAS_CO25"),
     "CO26": os.getenv("IP_BALANZAS_CO26"),
     "CO27": os.getenv("IP_BALANZAS_CO27"),
     "CO28": os.getenv("IP_BALANZAS_CO28"),
     "CO29": os.getenv("IP_BALANZAS_CO29"),
     "MA02": os.getenv("IP_BALANZAS_MA02")

}


@balanza_bp.route("/", methods=["GET", "POST"])
def index():
    resultado = None
    error = None

    sucursal_seleccionada = request.form.get("sucursal", "")
    nroplu = request.form.get("nroplu", "").strip()

    if request.method == "POST":

        if sucursal_seleccionada not in SUCURSALES_BALANZA:
            error = "Debe seleccionar una sucursal válida."

        elif not nroplu:
            error = "Debe ingresar un número PLU."

        else:
            ruta_db = SUCURSALES_BALANZA[sucursal_seleccionada]

            try:
                if not os.path.exists(ruta_db):
                    raise FileNotFoundError(
                        f"No se encontró la base de datos de {sucursal_seleccionada}."
                    )

                conexion = sqlite3.connect(
                    f"file:{ruta_db}?mode=ro",
                    uri=True,
                    timeout=5
                )

                cursor = conexion.cursor()

                cursor.execute(
                    """
                    SELECT plu, nroplu
                    FROM numplu
                    WHERE nroplu = ?
                    LIMIT 1
                    """,
                    (nroplu,)
                )

                fila = cursor.fetchone()

                cursor.close()
                conexion.close()

                if fila:
                    resultado = {
                        "plu": fila[0],
                        "nroplu": fila[1]
                    }
                else:
                    error = (
                        f"No se encontró el Nro. PLU {nroplu} "
                        f"en la sucursal {sucursal_seleccionada}."
                    )

            except sqlite3.Error as e:
                error = f"Error al consultar la base SQLite: {e}"

            except OSError as e:
                error = f"No se pudo acceder a la base de la sucursal: {e}"

    return render_template(
        "balanza.html",
        sucursales=SUCURSALES_BALANZA.keys(),
        sucursal_seleccionada=sucursal_seleccionada,
        nroplu=nroplu,
        resultado=resultado,
        error=error
    )