import json
import uuid
from datetime import datetime

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

from farmacia_folder import (
    borrar_folder_farmacia_vigente,
    guardar_farmacia_folder_en_db,
)


farmacia_nutricia_bp = Blueprint(
    "farmacia_nutricia",
    __name__,
    url_prefix="/farmacia/cenefas/nutricia",
)


CACHE_PREFIX = "farmacia_nutricia"
CACHE_TTL = 3600


ALIAS_NUTRICIA = {
    "troquel": [
        "troquel",
        "codigo",
        "código",
        "cod",
        "cod_scan",
        "cod/scan",
        "material",
    ],
    "cod_barra": [
        "cod_barra",
        "cod barra",
        "codbarra",
        "codigo_barra",
        "código barra",
        "codigo de barra",
        "código de barra",
        "codebar",
        "ean",
    ],
    "descripcion": [
        "descripcion",
        "descripción",
        "descrip",
        "producto",
        "nombre",
        "detalle",
    ],
    "normal": [
        "normal",
        "precio_normal",
        "precio normal",
        "pvp",
        "precio lista",
    ],
    "oferta": [
        "oferta",
        "precio_oferta",
        "precio oferta",
        "promo_precio",
    ],
    "promo": [
        "promo",
        "promocion",
        "promoción",
        "cenefa",
        "tipo promocion",
        "tipo promoción",
    ],
    "reconocido": [
        "reconocido",
        "reconoc",
    ],
    "observacion": [
        "observacion",
        "observación",
        "observ",
    ],
}


COLUMNAS_OBLIGATORIAS = [
    "troquel",
    "descripcion",
    "normal",
    "oferta",
    "promo",
]


COLUMNAS_SALIDA = [
    "troquel",
    "cod_barra",
    "descripcion",
    "normal",
    "oferta",
    "promo",
    "reconocido",
    "observacion",
]


def limpiar_nombre_columna(valor):
    return (
        str(valor)
        .strip()
        .lower()
        .replace(".", "")
        .replace("-", "_")
        .replace("/", "_")
        .replace(" ", "_")
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )


def limpiar_texto(valor):
    if valor is None:
        return ""

    try:
        if pd.isna(valor):
            return ""
    except (TypeError, ValueError):
        pass

    texto = str(valor).strip()

    if texto.lower() in {
        "nan",
        "none",
        "null",
        "<na>",
    }:
        return ""

    return texto


def limpiar_codigo(valor):
    texto = limpiar_texto(valor)

    if not texto:
        return ""

    # Corrige valores que Excel interpreta como 12345.0
    if texto.endswith(".0"):
        parte_entera = texto[:-2]

        if parte_entera.replace("-", "").isdigit():
            return parte_entera

    return texto


def limpiar_precio(valor):
    if valor is None:
        return None

    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):
        pass

    texto = str(valor).strip()

    if not texto:
        return None

    errores_excel = {
        "#REF!",
        "#¡REF!",
        "#VALUE!",
        "#¡VALOR!",
        "#DIV/0!",
        "#N/A",
        "#NAME?",
        "#¿NOMBRE?",
    }

    if texto.upper() in errores_excel:
        raise ValueError(
            f"Se encontró una celda defectuosa de Excel: {texto}"
        )

    texto = (
        texto
        .replace("$", "")
        .replace(" ", "")
    )

    # Formato argentino: 12.345,67
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")

    # Formato con coma decimal: 12345,67
    elif "," in texto:
        texto = texto.replace(",", ".")

    try:
        return float(texto)

    except (TypeError, ValueError):
        raise ValueError(
            f"No se pudo interpretar el precio: {valor}"
        )


def buscar_columna(df, aliases):
    columnas_normalizadas = {
        limpiar_nombre_columna(columna): columna
        for columna in df.columns
    }

    for alias in aliases:
        alias_normalizado = limpiar_nombre_columna(alias)

        if alias_normalizado in columnas_normalizadas:
            return columnas_normalizadas[alias_normalizado]

    return None


def normalizar_dataframe(df):
    columnas_encontradas = {}

    for destino, aliases in ALIAS_NUTRICIA.items():
        columna = buscar_columna(df, aliases)

        if columna is not None:
            columnas_encontradas[destino] = columna

    faltantes = [
        columna
        for columna in COLUMNAS_OBLIGATORIAS
        if columna not in columnas_encontradas
    ]

    if faltantes:
        raise ValueError(
            "No se encontraron las columnas obligatorias: "
            + ", ".join(faltantes)
        )

    resultado = pd.DataFrame(index=df.index)

    for columna_salida in COLUMNAS_SALIDA:
        columna_origen = columnas_encontradas.get(
            columna_salida
        )

        if columna_origen is None:
            resultado[columna_salida] = None
        else:
            resultado[columna_salida] = df[
                columna_origen
            ]

    resultado["troquel"] = resultado[
        "troquel"
    ].apply(limpiar_codigo)

    resultado["cod_barra"] = resultado[
        "cod_barra"
    ].apply(limpiar_codigo)

    resultado["descripcion"] = resultado[
        "descripcion"
    ].apply(limpiar_texto)

    resultado["promo"] = resultado[
        "promo"
    ].apply(limpiar_texto)

    resultado["reconocido"] = resultado[
        "reconocido"
    ].apply(limpiar_texto)

    resultado["observacion"] = resultado[
        "observacion"
    ].apply(limpiar_texto)

    resultado["normal"] = resultado[
        "normal"
    ].apply(limpiar_precio)

    resultado["oferta"] = resultado[
        "oferta"
    ].apply(limpiar_precio)

    resultado = resultado[
        resultado["troquel"].ne("")
        & resultado["descripcion"].ne("")
    ].copy()

    resultado.reset_index(
        drop=True,
        inplace=True,
    )

    return resultado


def validar_fechas(fecha_desde, fecha_hasta):
    if not fecha_desde or not fecha_hasta:
        raise ValueError(
            "Debe indicar las fechas Desde y Hasta."
        )

    try:
        desde = datetime.strptime(
            fecha_desde,
            "%Y-%m-%d",
        ).date()

        hasta = datetime.strptime(
            fecha_hasta,
            "%Y-%m-%d",
        ).date()

    except ValueError as error:
        raise ValueError(
            "Las fechas recibidas no tienen un formato válido."
        ) from error

    if desde > hasta:
        raise ValueError(
            "La fecha Desde no puede ser posterior "
            "a la fecha Hasta."
        )

    return desde, hasta


def generar_preview(df):
    columnas_preview = [
        "troquel",
        "cod_barra",
        "descripcion",
        "normal",
        "oferta",
        "promo",
    ]

    df_preview = df[columnas_preview].copy()

    df_preview.rename(
        columns={
            "troquel": "Troquel",
            "cod_barra": "Código de barra",
            "descripcion": "Descripción",
            "normal": "Normal",
            "oferta": "Oferta",
            "promo": "Promoción",
        },
        inplace=True,
    )

    return df_preview.to_html(
        index=False,
        classes=(
            "table table-bordered table-striped "
            "table-hover table-sm align-middle"
        ),
        border=0,
        justify="center",
    )

def obtener_cache_id():
    return session.get(
        "farmacia_nutricia_cache_id"
    )


def eliminar_cache(cache_id):
    if cache_id:
        redis_client.delete(
            f"{CACHE_PREFIX}:{cache_id}"
        )

    session.pop(
        "farmacia_nutricia_cache_id",
        None,
    )


@farmacia_nutricia_bp.route(
    "/",
    methods=["GET", "POST"],
)
def index():
    if session.get("usuario_rol") != "adm-farmacia":
        return redirect(
            url_for("sistemas.login")
        )

    preview = None
    total_registros = 0
    fecha_desde = ""
    fecha_hasta = ""
    mensaje_error = None
    mensaje_ok = None

    if request.method == "POST":
        accion = request.form.get(
            "accion",
            "",
        ).strip().lower()

        # ==================================================
        # PROCESAR ARCHIVO
        # ==================================================
        if accion == "procesar":
            archivo = request.files.get("archivo")

            fecha_desde = request.form.get(
                "fecha_desde",
                "",
            ).strip()

            fecha_hasta = request.form.get(
                "fecha_hasta",
                "",
            ).strip()

            try:
                if not archivo or archivo.filename == "":
                    raise ValueError(
                        "Debe seleccionar un archivo Excel."
                    )

                validar_fechas(
                    fecha_desde,
                    fecha_hasta,
                )

                df = pd.read_excel(
                    archivo,
                    dtype=object,
                )

                print(
                    "COLUMNAS NUTRICIA:",
                    [str(columna) for columna in df.columns],
                    flush=True,
                )

                df_procesado = normalizar_dataframe(df)

                if df_procesado.empty:
                    raise ValueError(
                        "El archivo no contiene registros válidos."
                    )

                registros = df_procesado.to_dict(
                    orient="records"
                )

                cache_anterior = obtener_cache_id()

                if cache_anterior:
                    eliminar_cache(cache_anterior)

                cache_id = str(uuid.uuid4())

                contenido_cache = {
                    "registros": registros,
                    "fecha_desde": fecha_desde,
                    "fecha_hasta": fecha_hasta,
                    "archivo": archivo.filename,
                }

                redis_client.setex(
                    f"{CACHE_PREFIX}:{cache_id}",
                    CACHE_TTL,
                    json.dumps(
                        contenido_cache,
                        ensure_ascii=False,
                        default=str,
                    ),
                )

                session[
                    "farmacia_nutricia_cache_id"
                ] = cache_id

                total_registros = len(registros)
                preview = generar_preview(df_procesado)

                mensaje_ok = (
                    f"Se procesaron correctamente "
                    f"{total_registros} registros de Nutricia."
                )

                print(
                    "NUTRICIA GUARDADA EN REDIS:",
                    total_registros,
                    "CACHE ID:",
                    cache_id,
                    flush=True,
                )

            except Exception as error:
                print(
                    "ERROR PROCESANDO NUTRICIA:",
                    repr(error),
                    flush=True,
                )

                mensaje_error = str(error)

        # ==================================================
        # TRANSMITIR A POSTGRESQL
        # ==================================================
        elif accion == "transmitir":
            cache_id = obtener_cache_id()

            if not cache_id:
                flash(
                    "No existen datos procesados "
                    "para transmitir.",
                    "danger",
                )

                return redirect(
                    url_for("farmacia_nutricia.index")
                )

            datos_cache = redis_client.get(
                f"{CACHE_PREFIX}:{cache_id}"
            )

            if not datos_cache:
                eliminar_cache(cache_id)

                flash(
                    "La previsualización expiró. "
                    "Vuelva a procesar el archivo.",
                    "danger",
                )

                return redirect(
                    url_for("farmacia_nutricia.index")
                )

            try:
                contenido_cache = json.loads(
                    datos_cache
                )

                registros = contenido_cache.get(
                    "registros",
                    [],
                )

                fecha_desde = contenido_cache.get(
                    "fecha_desde",
                    "",
                )

                fecha_hasta = contenido_cache.get(
                    "fecha_hasta",
                    "",
                )

                validar_fechas(
                    fecha_desde,
                    fecha_hasta,
                )

                if not registros:
                    raise ValueError(
                        "La caché no contiene registros."
                    )

                df = pd.DataFrame(registros)

                lote_carga = str(uuid.uuid4())

                usuario_carga = limpiar_texto(
                    session.get(
                        "usuario_nombre",
                        "sistema",
                    )
                )

                # Solo elimina registros de Nutricia.
                borrar_folder_farmacia_vigente(
                    "nutricia"
                )

                guardar_farmacia_folder_en_db(
                    df,
                    usuario=usuario_carga,
                    lote_carga=lote_carga,
                    fecha_desde=fecha_desde,
                    fecha_hasta=fecha_hasta,
                    tipo_cenefa="nutricia",
                )

                eliminar_cache(cache_id)

                flash(
                    (
                        f"Se transmitieron correctamente "
                        f"{len(registros)} registros de Nutricia."
                    ),
                    "success",
                )

                print(
                    "NUTRICIA TRANSMITIDA:",
                    len(registros),
                    "LOTE:",
                    lote_carga,
                    flush=True,
                )

            except Exception as error:
                print(
                    "ERROR TRANSMITIENDO NUTRICIA:",
                    repr(error),
                    flush=True,
                )

                flash(
                    f"Error al transmitir Nutricia: {error}",
                    "danger",
                )

            return redirect(
                url_for("farmacia_nutricia.index")
            )

        else:
            mensaje_error = (
                "La acción solicitada no es válida."
            )

    return render_template(
        "farmacia/nutricia.html",
        preview=preview,
        total_registros=total_registros,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        mensaje_error=mensaje_error,
        mensaje_ok=mensaje_ok,
    )