import json
import re
import uuid

import pandas as pd

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from compras import redis_client
from database.db import get_db_connection


cupones_bp = Blueprint(
    "cupones",
    __name__,
    url_prefix="/cupones",
)


CACHE_PREFIX = "cupones_sorteo"
CACHE_TTL = 3600


# ============================================================
# SUCURSALES RESPONSABLES POR PROVINCIA
# ============================================================

SUCURSALES_SORTEO_POR_PROVINCIA = {
    "CO05": {
        "provincia": "Jujuy",
        "sucursales": [
            "CO01",
            "CO02",
            "CO04",
            "CO05",
            "CO06",
            "CO07",
            "CO08",
            "CO10",
            "CO11",
            "CO12",
            "CO14",
            "CO15",
            "CO16",
            "CO17",
            "CO19",
            "CO20",
            "CO22",
            "CO28",
            "MA02",
        ],
    },
    "CO24": {
        "provincia": "Tucumán",
        "sucursales": [
            "CO24",
            "CO25",
            "CO26",
            "CO27",
        ],
    },
    "CO29": {
        "provincia": "Salta",
        "sucursales": [
            "CO09",
            "CO18",
            "CO21",
            "CO23",
            "CO29",
        ],
    },
}


SUCURSALES_VALIDAS_SORTEO = {
    sucursal
    for configuracion in SUCURSALES_SORTEO_POR_PROVINCIA.values()
    for sucursal in configuracion["sucursales"]
}


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def limpiar_valor(valor, defecto=""):
    if valor is None:
        return defecto

    try:
        if pd.isna(valor):
            return defecto
    except (TypeError, ValueError):
        pass

    return valor


def limpiar_texto(valor):
    valor = limpiar_valor(valor, "")
    return str(valor).strip()


def normalizar_texto(valor):
    """
    Normaliza texto para comparaciones:
    - minúsculas;
    - sin acentos;
    - espacios internos normalizados.
    """
    texto = limpiar_texto(valor).lower()

    texto = (
        texto
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )

    return re.sub(r"\s+", " ", texto).strip()


def obtener_valor_fila(fila, *columnas):
    """
    Devuelve el primer valor válido encontrado entre varios nombres
    posibles de columna.
    """
    for columna in columnas:
        if columna not in fila.index:
            continue

        valor = fila.get(columna)

        try:
            if pd.isna(valor):
                continue
        except (TypeError, ValueError):
            pass

        return valor

    return ""


def normalizar_sucursal_sorteo(valor):
    """
    Convierte diferentes denominaciones de sucursal al formato COxx o MAxx.
    """
    if valor is None:
        return ""

    valor = str(valor).strip().upper()

    if not valor:
        return ""

    valor = (
        valor
        .replace("Í", "I")
        .replace("Ó", "O")
        .replace("Á", "A")
        .replace("É", "E")
        .replace("Ú", "U")
    )

    valor = re.sub(r"\s+", " ", valor).strip()

    mapa = {
        "ALBERDISA01": "CO01",
        "ALBERDISA02": "CO02",
        "ALBERDISA04": "CO04",
        "ALBERDISA05": "CO05",
        "ALBERDISA06": "CO06",
        "ALBERDISA07": "CO07",
        "ALBERDISA08": "CO08",
        "ALBERDISA09": "CO09",
        "ALBERDISA10": "CO10",
        "ALBERDISA11": "CO11",
        "ALBERDISA12": "CO12",
        "ALBERDISA14": "CO14",
        "ALBERDISA15": "CO15",
        "ALBERDISA16": "CO16",
        "ALBERDISA17": "CO17",
        "ALBERDISA18": "CO18",
        "ALBERDISA19": "CO19",
        "ALBERDISA20": "CO20",
        "ALBERDISA21": "CO21",
        "ALBERDISA22": "CO22",
        "ALBERDISA23": "CO23",
        "ALBERDISA24": "CO24",
        "ALBERDISA25": "CO25",
        "ALBERDISA26": "CO26",
        "ALBERDISA27": "CO27",
        "ALBERDISA28": "CO28",
        "ALBERDISA29": "CO29",

        "MAYORISTA02": "MA02",
        "MAYORISTA 02": "MA02",
        "MAYORISTA 2": "MA02",
        "MA02": "MA02",
    }

    if valor in mapa:
        return mapa[valor]

    patrones = [
        (r"ALBERDISA\s*0*(\d{1,2})", "CO"),
        (r"COMODIN\s*0*(\d{1,2})", "CO"),
        (r"SUCURSAL\s*0*(\d{1,2})", "CO"),
        (r"CO\s*0*(\d{1,2})", "CO"),
        (r"MAYORISTA\s*0*(\d{1,2})", "MA"),
        (r"MA\s*0*(\d{1,2})", "MA"),
    ]

    for patron, prefijo in patrones:
        coincidencia = re.fullmatch(
            patron,
            valor,
        )

        if coincidencia:
            numero = int(coincidencia.group(1))
            return f"{prefijo}{numero:02d}"

    return valor


# ============================================================
# BASE DE DATOS
# ============================================================

def crear_tabla_cupones_sorteo():
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS cupones_sorteo (
                id SERIAL PRIMARY KEY,
                nombre TEXT,
                dni TEXT,
                telefono TEXT,
                sucursal_origen TEXT,
                sucursal_codigo TEXT,
                estado TEXT,
                fecha_transmision TIMESTAMP DEFAULT NOW()
            )
            """
        )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        cur.close()
        conn.close()


# ============================================================
# CARGA Y PREVISUALIZACIÓN
# ============================================================

@cupones_bp.route("/", methods=["GET", "POST"])
def index():
    if session.get("usuario_rol") != "publicidad":
        return redirect(
            url_for("sistemas.login")
        )

    cupones = []
    total_filas = 0
    total_cupones = 0
    total_anulados = 0
    total_sucursal_invalida = 0
    cache_id = ""

    if request.method == "POST":
        archivo = request.files.get("archivo")

        if not archivo or archivo.filename == "":
            flash(
                "Debe seleccionar un archivo Excel.",
                "warning",
            )
            return redirect(
                url_for("cupones.index")
            )

        try:
            df = pd.read_excel(
                archivo,
                dtype=object,
            )

        except Exception as error:
            print(
                "ERROR LEYENDO ARCHIVO EXCEL:",
                repr(error),
                flush=True,
            )

            flash(
                f"No se pudo leer el archivo Excel: {error}",
                "danger",
            )

            return redirect(
                url_for("cupones.index")
            )

        print(
            "COLUMNAS DEL EXCEL:",
            [str(columna) for columna in df.columns],
            flush=True,
        )

        total_filas = len(df)

        for numero_fila, (_, fila) in enumerate(
            df.iterrows(),
            start=2,
        ):
            estado = limpiar_texto(
                obtener_valor_fila(
                    fila,
                    "Estado",
                    "estado",
                )
            )

            estado_normalizado = normalizar_texto(
                estado
            )

            # El único estado que no genera cupón.
            if estado_normalizado == "anulacion confirmada":
                total_anulados += 1
                continue

            sucursal_origen = limpiar_texto(
                obtener_valor_fila(
                    fila,
                    "Tienda",
                    "Sucursal",
                    "Sucursal origen",
                    "Sucursal Origen",
                )
            )

            sucursal_codigo = normalizar_sucursal_sorteo(
                sucursal_origen
            )

            # Solo se admiten sucursales pertenecientes al sorteo.
            if sucursal_codigo not in SUCURSALES_VALIDAS_SORTEO:
                total_sucursal_invalida += 1

                if total_sucursal_invalida <= 10:
                    print(
                        "FILA OMITIDA POR SUCURSAL NO VÁLIDA:",
                        numero_fila,
                        "| ORIGEN:",
                        repr(sucursal_origen),
                        "| CÓDIGO:",
                        repr(sucursal_codigo),
                        flush=True,
                    )

                continue

            nombre = limpiar_texto(
                obtener_valor_fila(
                    fila,
                    "Cliente",
                    "Nombre",
                    "Nombre cliente",
                    "Nombre Cliente",
                )
            )

            dni = limpiar_texto(
                obtener_valor_fila(
                    fila,
                    "Documento cliente",
                    "Documento Cliente",
                    "Documento",
                    "DNI",
                )
            )

            telefono = limpiar_texto(
                obtener_valor_fila(
                    fila,
                    "Teléfono",
                    "Telefono",
                    "Teléfono cliente",
                    "Telefono cliente",
                )
            )

            registro = {
                "nombre": nombre,
                "dni": dni,
                "telefono": telefono,
                "sucursal_origen": sucursal_origen,
                "sucursal_codigo": sucursal_codigo,
                "estado": estado,
            }

            cupones.append(registro)

        total_cupones = len(cupones)

        print(
            "RESUMEN CUPONES:",
            "TOTAL EXCEL:",
            total_filas,
            "| CUPONES:",
            total_cupones,
            "| ANULADOS:",
            total_anulados,
            "| SUCURSAL INVÁLIDA:",
            total_sucursal_invalida,
            flush=True,
        )

        if cupones:
            cache_id = str(uuid.uuid4())
            clave_redis = f"{CACHE_PREFIX}:{cache_id}"

            try:
                redis_client.setex(
                    clave_redis,
                    CACHE_TTL,
                    json.dumps(
                        cupones,
                        ensure_ascii=False,
                        default=str,
                    ),
                )

                print(
                    "CUPONES GUARDADOS EN REDIS:",
                    total_cupones,
                    "| CACHE ID:",
                    cache_id,
                    flush=True,
                )

            except Exception as error:
                print(
                    "ERROR GUARDANDO CUPONES EN REDIS:",
                    repr(error),
                    flush=True,
                )

                flash(
                    "No se pudieron almacenar temporalmente los cupones.",
                    "danger",
                )

                return redirect(
                    url_for("cupones.index")
                )

        else:
            flash(
                "No se encontraron registros válidos para generar cupones.",
                "warning",
            )

    return render_template(
        "publicidad/cupones.html",
        cupones=cupones,
        cache_id=cache_id,
        total_filas=total_filas,
        total_cupones=total_cupones,
        total_anulados=total_anulados,
        total_sucursal_invalida=total_sucursal_invalida,
    )


# ============================================================
# TRANSMISIÓN A SUCURSALES
# ============================================================

@cupones_bp.route(
    "/transmitir_sucursales",
    methods=["POST"],
)
def transmitir_sucursales():
    if session.get("usuario_rol") != "publicidad":
        return redirect(
            url_for("sistemas.login")
        )

    cache_id = request.form.get(
        "cache_id",
        "",
    ).strip()

    if not cache_id:
        flash(
            "No se recibió el identificador de los datos procesados.",
            "warning",
        )
        return redirect(
            url_for("cupones.index")
        )

    clave_redis = f"{CACHE_PREFIX}:{cache_id}"

    try:
        datos_redis = redis_client.get(
            clave_redis
        )

    except Exception as error:
        print(
            "ERROR CONSULTANDO REDIS:",
            repr(error),
            flush=True,
        )

        flash(
            "No se pudieron recuperar los datos procesados.",
            "danger",
        )

        return redirect(
            url_for("cupones.index")
        )

    if not datos_redis:
        flash(
            "Los datos procesados expiraron o ya fueron transmitidos.",
            "warning",
        )

        return redirect(
            url_for("cupones.index")
        )

    try:
        if isinstance(datos_redis, bytes):
            datos_redis = datos_redis.decode(
                "utf-8"
            )

        registros = json.loads(
            datos_redis
        )

    except Exception as error:
        print(
            "ERROR DECODIFICANDO REDIS:",
            repr(error),
            flush=True,
        )

        flash(
            "Los datos temporales no tienen un formato válido.",
            "danger",
        )

        return redirect(
            url_for("cupones.index")
        )

    if not registros:
        flash(
            "No hay cupones procesados para transmitir.",
            "warning",
        )

        return redirect(
            url_for("cupones.index")
        )

    conn = None
    cur = None

    insertados = 0
    omitidos = 0

    try:
        crear_tabla_cupones_sorteo()

        conn = get_db_connection()
        cur = conn.cursor()

        # Cada transmisión reemplaza el listado vigente.
        cur.execute(
            "DELETE FROM cupones_sorteo"
        )

        for registro in registros:
            estado = limpiar_texto(
                registro.get("estado")
            )

            if normalizar_texto(estado) == "anulacion confirmada":
                omitidos += 1
                continue

            sucursal_origen = limpiar_texto(
                registro.get("sucursal_origen")
                or registro.get("sucursal")
            )

            sucursal_codigo = normalizar_sucursal_sorteo(
                registro.get("sucursal_codigo")
                or sucursal_origen
            )

            if sucursal_codigo not in SUCURSALES_VALIDAS_SORTEO:
                omitidos += 1
                continue

            cur.execute(
                """
                INSERT INTO cupones_sorteo (
                    nombre,
                    dni,
                    telefono,
                    sucursal_origen,
                    sucursal_codigo,
                    estado,
                    fecha_transmision
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    NOW()
                )
                """,
                (
                    limpiar_texto(
                        registro.get("nombre")
                    ),
                    limpiar_texto(
                        registro.get("dni")
                    ),
                    limpiar_texto(
                        registro.get("telefono")
                    ),
                    sucursal_origen,
                    sucursal_codigo,
                    estado,
                ),
            )

            insertados += 1

        conn.commit()

        # La caché se elimina solo después del commit exitoso.
        redis_client.delete(
            clave_redis
        )

        print(
            "TRANSMISIÓN DE CUPONES FINALIZADA:",
            "INSERTADOS:",
            insertados,
            "| OMITIDOS:",
            omitidos,
            flush=True,
        )

        flash(
            (
                "Transmisión finalizada. "
                f"Cupones insertados: {insertados}. "
                f"Omitidos: {omitidos}."
            ),
            "success",
        )

    except Exception as error:
        if conn:
            conn.rollback()

        print(
            "ERROR TRANSMITIENDO CUPONES:",
            repr(error),
            flush=True,
        )

        flash(
            f"No se pudieron transmitir los cupones: {error}",
            "danger",
        )

    finally:
        if cur:
            cur.close()

        if conn:
            conn.close()

    return redirect(
        url_for("cupones.index")
    )


# ============================================================
# VISUALIZACIÓN PROVINCIAL
# ============================================================

@cupones_bp.route("/sucursales_sorteo")
def sucursales_sorteo():
    if session.get("usuario_rol") != "sucursal":
        return redirect(
            url_for("sistemas.login")
        )

    sucursal_usuario = normalizar_sucursal_sorteo(
        session.get(
            "usuario_nombre",
            "",
        )
    )

    configuracion = SUCURSALES_SORTEO_POR_PROVINCIA.get(
        sucursal_usuario
    )

    if not configuracion:
        flash(
            "La sucursal no está habilitada para administrar este sorteo.",
            "warning",
        )

        return redirect(
            url_for(
                "compras.sucursal",
                tipo="minorista",
            )
        )

    provincia = configuracion["provincia"]
    sucursales_provincia = configuracion["sucursales"]

    crear_tabla_cupones_sorteo()

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute(
            """
            SELECT
                nombre,
                dni,
                telefono,
                sucursal_origen,
                sucursal_codigo,
                estado,
                fecha_transmision
            FROM cupones_sorteo
            WHERE sucursal_codigo = ANY(%s)
            ORDER BY
                sucursal_codigo ASC,
                fecha_transmision DESC,
                id DESC
            """,
            (sucursales_provincia,),
        )

        cupones = cur.fetchall()

    except Exception:
        conn.rollback()
        raise

    finally:
        cur.close()
        conn.close()

    return render_template(
        "publicidad/sucursales_sorteo.html",
        cupones=cupones,
        sucursal=sucursal_usuario,
        provincia=provincia,
        sucursales_provincia=sucursales_provincia,
        total_cupones=len(cupones),
    )