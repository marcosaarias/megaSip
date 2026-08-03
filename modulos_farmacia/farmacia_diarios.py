import json
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

from farmacia_folder import (
    borrar_folder_farmacia_vigente,
    guardar_farmacia_folder_en_db,
)


farmacia_diarios_bp = Blueprint(
    "farmacia_diarios",
    __name__,
    url_prefix="/farmacia/cenefas/diarios",
)


CACHE_PREFIX = "farmacia_diarios"
CACHE_TTL = 3600


COLUMNAS_SALIDA = [
    "troquel",
    "cod_barra",
    "descripcion",
    "normal",
    "oferta",
    "promo",
]


def normalizar_nombre_columna(valor):
    return (
        str(valor)
        .strip()
        .lower()
        .replace(".", "")
        .replace("/", "_")
        .replace("-", "_")
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

    # Corrige códigos leídos por Excel como 12345.0.
    if texto.endswith(".0"):
        entero = texto[:-2]

        if entero.isdigit():
            return entero

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

    # Formato decimal con coma: 12345,67
    elif "," in texto:
        texto = texto.replace(",", ".")

    try:
        return float(texto)

    except (TypeError, ValueError):
        raise ValueError(
            f"No se pudo interpretar el precio: {valor}"
        )


def normalizar_columnas(df):
    df = df.copy()

    df.columns = [
        normalizar_nombre_columna(columna)
        for columna in df.columns
    ]

    aliases = {
        "troquel": [
            "troquel",
            "codigo",
            "cod",
            "cod_scan",
            "codscan",
            "material",
        ],
        "cod_barra": [
            "cod_barra",
            "codbarra",
            "codigo_barra",
            "codigo_de_barra",
            "codebar",
            "ean",
        ],
        "descripcion": [
            "descripcion",
            "descrip",
            "producto",
            "nombre",
            "detalle",
        ],
        "normal": [
            "normal",
            "precio_normal",
            "pvp",
            "precio_lista",
        ],
        "oferta": [
            "oferta",
            "precio_oferta",
            "promo_precio",
        ],
        "promo": [
            "promo",
            "promocion",
            "cenefa",
            "tipo_promocion",
        ],
    }

    columnas_encontradas = {}

    for destino, opciones in aliases.items():
        for opcion in opciones:
            opcion_normalizada = normalizar_nombre_columna(
                opcion
            )

            if opcion_normalizada in df.columns:
                columnas_encontradas[destino] = (
                    opcion_normalizada
                )
                break

    faltantes = [
        columna
        for columna in COLUMNAS_SALIDA
        if columna not in columnas_encontradas
    ]

    if faltantes:
        raise ValueError(
            "No se encontraron las columnas requeridas: "
            + ", ".join(faltantes)
        )

    resultado = pd.DataFrame()

    for destino in COLUMNAS_SALIDA:
        origen = columnas_encontradas[destino]
        resultado[destino] = df[origen]

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

    resultado["normal"] = resultado[
        "normal"
    ].apply(limpiar_precio)

    resultado["oferta"] = resultado[
        "oferta"
    ].apply(limpiar_precio)

    # Columnas opcionales que utiliza la tabla compartida.
    resultado["reconocido"] = None
    resultado["observacion"] = None

    resultado = resultado[
        resultado["troquel"].ne("")
        & resultado["descripcion"].ne("")
    ].copy()

    resultado.reset_index(
        drop=True,
        inplace=True,
    )

    return resultado


def generar_preview(df):
    df_preview = df[
        [
            "troquel",
            "cod_barra",
            "descripcion",
            "normal",
            "oferta",
            "promo",
        ]
    ].copy()

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
    )


def eliminar_cache_diarios(cache_id):
    if cache_id:
        redis_client.delete(
            f"{CACHE_PREFIX}:{cache_id}"
        )

    session.pop(
        "farmacia_diarios_cache_id",
        None,
    )


@farmacia_diarios_bp.route(
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
        # PROCESAR EXCEL
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

                if not fecha_desde or not fecha_hasta:
                    raise ValueError(
                        "Debe indicar las fechas de vigencia."
                    )

                if fecha_desde > fecha_hasta:
                    raise ValueError(
                        "La fecha Desde no puede ser mayor "
                        "que la fecha Hasta."
                    )

                df = pd.read_excel(
                    archivo,
                    dtype=object,
                )

                print(
                    "COLUMNAS DIARIOS:",
                    [str(columna) for columna in df.columns],
                    flush=True,
                )

                df_procesado = normalizar_columnas(df)

                if df_procesado.empty:
                    raise ValueError(
                        "El archivo no contiene registros válidos."
                    )

                registros = df_procesado.to_dict(
                    orient="records"
                )

                cache_anterior = session.get(
                    "farmacia_diarios_cache_id"
                )

                if cache_anterior:
                    eliminar_cache_diarios(
                        cache_anterior
                    )

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
                    "farmacia_diarios_cache_id"
                ] = cache_id

                total_registros = len(registros)
                preview = generar_preview(df_procesado)

                mensaje_ok = (
                    f"Se procesaron correctamente "
                    f"{total_registros} registros de Diarios."
                )

                print(
                    "DIARIOS GUARDADOS EN REDIS:",
                    total_registros,
                    "CACHE ID:",
                    cache_id,
                    flush=True,
                )

            except Exception as error:
                print(
                    "ERROR PROCESANDO DIARIOS:",
                    repr(error),
                    flush=True,
                )

                mensaje_error = str(error)

        # ==================================================
        # TRANSMITIR A POSTGRESQL
        # ==================================================
        elif accion == "transmitir":
            cache_id = session.get(
                "farmacia_diarios_cache_id"
            )

            if not cache_id:
                flash(
                    "No existen datos procesados "
                    "para transmitir.",
                    "danger",
                )

                return redirect(
                    url_for("farmacia_diarios.index")
                )

            datos_cache = redis_client.get(
                f"{CACHE_PREFIX}:{cache_id}"
            )

            if not datos_cache:
                eliminar_cache_diarios(cache_id)

                flash(
                    "La previsualización expiró. "
                    "Vuelva a procesar el archivo.",
                    "danger",
                )

                return redirect(
                    url_for("farmacia_diarios.index")
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

                if not registros:
                    raise ValueError(
                        "La caché no contiene registros."
                    )

                if not fecha_desde or not fecha_hasta:
                    raise ValueError(
                        "No se encontraron las fechas "
                        "de vigencia en la caché."
                    )

                df = pd.DataFrame(registros)

                lote_carga = str(uuid.uuid4())

                usuario_carga = limpiar_texto(
                    session.get(
                        "usuario_nombre",
                        "sistema",
                    )
                )

                # Solo elimina registros del tipo Diarios.
                borrar_folder_farmacia_vigente(
                    "diarios"
                )

                guardar_farmacia_folder_en_db(
                    df,
                    usuario=usuario_carga,
                    lote_carga=lote_carga,
                    fecha_desde=fecha_desde,
                    fecha_hasta=fecha_hasta,
                    tipo_cenefa="diarios",
                )

                eliminar_cache_diarios(cache_id)

                flash(
                    (
                        f"Se transmitieron correctamente "
                        f"{len(registros)} registros de Diarios."
                    ),
                    "success",
                )

                print(
                    "DIARIOS TRANSMITIDOS:",
                    len(registros),
                    "LOTE:",
                    lote_carga,
                    flush=True,
                )

            except Exception as error:
                print(
                    "ERROR TRANSMITIENDO DIARIOS:",
                    repr(error),
                    flush=True,
                )

                flash(
                    f"Error al transmitir Diarios: {error}",
                    "danger",
                )

            return redirect(
                url_for("farmacia_diarios.index")
            )

        else:
            mensaje_error = (
                "La acción solicitada no es válida."
            )

    return render_template(
        "farmacia/diarios.html",
        preview=preview,
        total_registros=total_registros,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        mensaje_error=mensaje_error,
        mensaje_ok=mensaje_ok,
    )