# compras/sucursales/folder_mayorista_tucuman.py

import json
import os
import re
import uuid

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2

from flask import (
    render_template,
    request,
    session,
)

from psycopg2.extras import RealDictCursor
from werkzeug.utils import secure_filename

from logs import guardar_log_compras
from sistemas import login_requerido


# ============================================================
# CONFIGURACIÓN
# ============================================================

SUCURSALES_MAYORISTA_TUCUMAN = "CO25"

TIPO_CENEFA_MAYORISTA_TUCUMAN = "mayorista"

COLUMNAS_EDITABLES_FOLDER_TUCUMAN = {
    "DESCRIPCION",
    "Normal",
    "Oferta",
    "cenefa",
}

EXTENSIONES_PERMITIDAS = {
    ".xlsx",
    ".xls",
}

MAX_CAMBIOS_PERMITIDOS = 10000

RUTA_TEMP_FOLDER_TUCUMAN = Path(
    os.getenv(
        "RUTA_TEMP_FOLDER_TUCUMAN",
        "/mnt/temp/folder-mayorista-tucuman",
    )
)

RUTA_TEMP_FOLDER_TUCUMAN.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# FUNCIONES PARA ARCHIVOS TEMPORALES
# ============================================================

def token_folder_tucuman_valido(token):
    """
    Valida que el token sea un UUID hexadecimal sin guiones.
    """
    return bool(
        re.fullmatch(
            r"[a-f0-9]{32}",
            token or "",
        )
    )


def ruta_parquet_folder_tucuman(token):
    return (
        RUTA_TEMP_FOLDER_TUCUMAN
        / f"{token}.parquet"
    )


def ruta_metadata_folder_tucuman(token):
    return (
        RUTA_TEMP_FOLDER_TUCUMAN
        / f"{token}.json"
    )


def guardar_folder_tucuman_temporal(
    df,
    usuario,
    archivo_nombre,
    fecha_desde,
    fecha_hasta,
):
    """
    Guarda el DataFrame como Parquet y los datos pequeños
    como JSON. No guarda el archivo pesado en session.
    """
    token = uuid.uuid4().hex

    ruta_df = ruta_parquet_folder_tucuman(token)
    ruta_metadata = ruta_metadata_folder_tucuman(token)

    metadata = {
        "token": token,
        "usuario": usuario,
        "archivo": secure_filename(
            archivo_nombre or ""
        ),
        "tipo_cenefa": (
            TIPO_CENEFA_MAYORISTA_TUCUMAN
        ),
        "region": "tucuman",
        "sucursales": (
            SUCURSALES_MAYORISTA_TUCUMAN
        ),
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "creado": datetime.now().isoformat(),
        "total_registros": len(df),
    }

    try:
        df.to_parquet(
            ruta_df,
            index=False,
        )

        with open(
            ruta_metadata,
            "w",
            encoding="utf-8",
        ) as archivo_metadata:
            json.dump(
                metadata,
                archivo_metadata,
                ensure_ascii=False,
                indent=2,
            )

        return token

    except Exception:
        ruta_df.unlink(missing_ok=True)
        ruta_metadata.unlink(missing_ok=True)
        raise


def recuperar_folder_tucuman_temporal(token):
    """
    Recupera el DataFrame y su metadata.
    """
    if not token_folder_tucuman_valido(token):
        return None, None

    ruta_df = ruta_parquet_folder_tucuman(token)
    ruta_metadata = ruta_metadata_folder_tucuman(
        token
    )

    if (
        not ruta_df.exists()
        or not ruta_metadata.exists()
    ):
        return None, None

    try:
        with open(
            ruta_metadata,
            "r",
            encoding="utf-8",
        ) as archivo_metadata:
            metadata = json.load(
                archivo_metadata
            )

        if metadata.get("token") != token:
            return None, None

        df = pd.read_parquet(ruta_df)

        return df, metadata

    except Exception as error:
        print(
            "Error recuperando temporal de "
            f"Folder Mayorista Tucumán: {error}"
        )
        return None, None


def eliminar_folder_tucuman_temporal(token):
    """
    Elimina Parquet y metadata.
    """
    if not token_folder_tucuman_valido(token):
        return

    archivos = [
        ruta_parquet_folder_tucuman(token),
        ruta_metadata_folder_tucuman(token),
    ]

    for ruta in archivos:
        try:
            ruta.unlink(missing_ok=True)
        except OSError as error:
            print(
                f"No se pudo eliminar {ruta}: {error}"
            )


def limpiar_temporales_folder_tucuman(
    horas_expiracion=2,
):
    """
    Elimina temporales con más de dos horas.
    """
    limite = (
        datetime.now()
        - timedelta(hours=horas_expiracion)
    )

    for ruta_metadata in (
        RUTA_TEMP_FOLDER_TUCUMAN.glob("*.json")
    ):
        token = ruta_metadata.stem

        try:
            with open(
                ruta_metadata,
                "r",
                encoding="utf-8",
            ) as archivo_metadata:
                metadata = json.load(
                    archivo_metadata
                )

            fecha_creacion = datetime.fromisoformat(
                metadata["creado"]
            )

            if fecha_creacion < limite:
                eliminar_folder_tucuman_temporal(
                    token
                )

        except Exception:
            eliminar_folder_tucuman_temporal(
                token
            )


# ============================================================
# VALIDACIONES
# ============================================================

def validar_fechas_folder_tucuman(
    fecha_desde,
    fecha_hasta,
):
    if not fecha_desde or not fecha_hasta:
        raise ValueError(
            "Debe seleccionar fecha Desde "
            "y fecha Hasta."
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
            "El formato de las fechas "
            "no es válido."
        ) from error

    if desde > hasta:
        raise ValueError(
            "La fecha Desde no puede ser "
            "posterior a la fecha Hasta."
        )

    return desde, hasta


def validar_archivo_excel(archivo):
    if not archivo or archivo.filename == "":
        raise ValueError(
            "Debe seleccionar un archivo Excel."
        )

    nombre_seguro = secure_filename(
        archivo.filename
    )

    extension = Path(
        nombre_seguro
    ).suffix.lower()

    if extension not in EXTENSIONES_PERMITIDAS:
        raise ValueError(
            "El archivo debe tener extensión "
            ".xlsx o .xls."
        )

    return nombre_seguro


def normalizar_cambios_json(cambios_json):
    try:
        cambios = json.loads(
            cambios_json or "[]"
        )
    except json.JSONDecodeError as error:
        raise ValueError(
            "No se pudieron interpretar "
            "las modificaciones realizadas."
        ) from error

    if not isinstance(cambios, list):
        raise ValueError(
            "El formato de las modificaciones "
            "no es válido."
        )

    if len(cambios) > MAX_CAMBIOS_PERMITIDOS:
        raise ValueError(
            "La cantidad de modificaciones "
            "supera el límite permitido."
        )

    return cambios


def aplicar_cambios_folder_tucuman(
    df,
    cambios,
    limpiar_precio,
):
    """
    Solo permite editar las columnas definidas
    en COLUMNAS_EDITABLES_FOLDER_TUCUMAN.
    """
    if not isinstance(cambios, list):
        raise ValueError(
            "El formato de las modificaciones "
            "no es válido."
        )

    df = df.copy().reset_index(drop=True)

    for cambio in cambios:
        if not isinstance(cambio, dict):
            raise ValueError(
                "Se recibió una modificación "
                "inválida."
            )

        fila = cambio.get("fila")
        columna = cambio.get("columna")
        valor = cambio.get("valor")

        if not isinstance(fila, int):
            raise ValueError(
                "Se recibió un número de fila "
                "inválido."
            )

        if fila < 0 or fila >= len(df):
            raise ValueError(
                f"La fila {fila + 1} no existe."
            )

        if (
            columna
            not in COLUMNAS_EDITABLES_FOLDER_TUCUMAN
        ):
            raise ValueError(
                f"No está permitido editar "
                f"la columna {columna}."
            )

        if columna not in df.columns:
            raise ValueError(
                f"La columna {columna} "
                "no existe en el lote."
            )

        if columna in {"Normal", "Oferta"}:
            precio = limpiar_precio(valor)

            if pd.isna(precio):
                raise ValueError(
                    f"El precio en la fila "
                    f"{fila + 1}, columna "
                    f"{columna}, no es válido."
                )

            if precio < 0:
                raise ValueError(
                    "Los precios no pueden "
                    "ser negativos."
                )

            valor = (
                np.floor(precio * 100)
                / 100
            )

        elif columna in {
            "DESCRIPCION",
            "cenefa",
        }:
            valor = str(
                valor or ""
            ).strip()

            if len(valor) > 250:
                raise ValueError(
                    f"El contenido de {columna} "
                    f"en la fila {fila + 1} "
                    "supera los 250 caracteres."
                )

            if (
                columna == "cenefa"
                and not valor
            ):
                valor = "OFERTA"

        df.at[
            fila,
            columna,
        ] = valor

    return df


def validar_dataframe_antes_transmitir(df):
    columnas_obligatorias = {
        "CODIGO",
        "desde",
        "hasta",
        "sucursales",
    }

    faltantes = (
        columnas_obligatorias
        - set(df.columns)
    )

    if faltantes:
        raise ValueError(
            "Faltan columnas obligatorias: "
            + ", ".join(
                sorted(faltantes)
            )
        )

    if df.empty:
        raise ValueError(
            "No existen registros "
            "para transmitir."
        )

    if df["CODIGO"].isna().any():
        raise ValueError(
            "Existen registros sin código."
        )

    if (
        df["desde"].isna().any()
        or df["hasta"].isna().any()
    ):
        raise ValueError(
            "Existen registros sin vigencia."
        )

    sucursales_incorrectas = df[
        df["sucursales"].astype(str)
        != SUCURSALES_MAYORISTA_TUCUMAN
    ]

    if not sucursales_incorrectas.empty:
        raise ValueError(
            "El lote contiene destinos "
            "distintos a CO25."
        )


# ============================================================
# CONSULTAS
# ============================================================

def obtener_lote_folder_tucuman(
    lote_carga,
    get_db_connection,
    formatear_precio_arg,
):
    conn = get_db_connection()

    cursor = conn.cursor(
        cursor_factory=RealDictCursor
    )

    try:
        cursor.execute(
            """
            SELECT
                id,
                codigo,
                ean,
                dep,
                departamento,
                descripcion,
                normal,
                oferta,
                cenefa,
                desde,
                hasta,
                sucursales,
                tipo_cenefa,
                fecha_carga,
                lote_carga,
                usuario_carga
            FROM cenefas
            WHERE lote_carga = %s
              AND tipo_cenefa = %s
              AND sucursales = %s
            ORDER BY id
            """,
            (
                lote_carga,
                TIPO_CENEFA_MAYORISTA_TUCUMAN,
                SUCURSALES_MAYORISTA_TUCUMAN,
            ),
        )

        registros = cursor.fetchall()

        for fila in registros:
            fila["normal"] = (
                formatear_precio_arg(
                    fila.get("normal")
                )
            )

            fila["oferta"] = (
                formatear_precio_arg(
                    fila.get("oferta")
                )
            )

        return registros

    finally:
        cursor.close()
        conn.close()


def existen_repetidos_folder_tucuman(
    df,
    get_db_connection,
):
    """
    Control específico para Tucumán.
    Incluye sucursal para no confundir
    registros de otras zonas mayoristas.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    repetidos = []

    try:
        for _, row in df.iterrows():
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM cenefas
                WHERE codigo = %s
                  AND tipo_cenefa = %s
                  AND desde = %s
                  AND hasta = %s
                  AND sucursales = %s
                """,
                (
                    row.get("CODIGO"),
                    (
                        TIPO_CENEFA_MAYORISTA_TUCUMAN
                    ),
                    row.get("desde"),
                    row.get("hasta"),
                    (
                        SUCURSALES_MAYORISTA_TUCUMAN
                    ),
                ),
            )

            cantidad = cursor.fetchone()[0]

            if cantidad > 0:
                repetidos.append(
                    row.get("CODIGO")
                )

        return repetidos

    finally:
        cursor.close()
        conn.close()


# ============================================================
# RENDER
# ============================================================

def render_folder_mayorista_tucuman(
    datos_preview=None,
    datos_transmitidos=None,
    token=None,
    mensaje_error=None,
    mensaje_exito=None,
    fecha_desde="",
    fecha_hasta="",
    total_registros=0,
    requiere_sobrescribir=False,
    lote_carga=None,
    fecha_carga=None,
    status_code=200,
):
    respuesta = render_template(
        "sucursales/folder-mayorista-tucuman.html",

        datos_preview=datos_preview,
        datos_transmitidos=(
            datos_transmitidos
        ),

        token=token,

        mensaje_error=mensaje_error,
        mensaje_exito=mensaje_exito,

        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,

        total_registros=total_registros,

        requiere_sobrescribir=(
            requiere_sobrescribir
        ),

        columnas_editables=(
            COLUMNAS_EDITABLES_FOLDER_TUCUMAN
        ),

        lote_carga=lote_carga,
        fecha_carga=fecha_carga,

        sucursales_destino=(
            SUCURSALES_MAYORISTA_TUCUMAN
        ),
    )

    return respuesta, status_code


# ============================================================
# REGISTRO DE RUTAS
# ============================================================

def registrar_rutas_folder_mayorista_tucuman(
    compras_bp,
    procesar_archivo_cenefas,
    guardar_cenefas_en_db,
    get_db_connection,
    limpiar_precio,
    formatear_precio_arg,
):
    """
    Registra las rutas sobre el blueprint compras_bp.

    Las funciones comunes se reciben como argumentos
    para evitar importaciones circulares.
    """

    @compras_bp.route(
        "/folder/mayorista/tucuman",
        methods=["GET", "POST"],
        endpoint="folder_mayorista_tucuman",
    )
    @login_requerido("compras")
    def folder_mayorista_tucuman():
        if request.method == "GET":
            limpiar_temporales_folder_tucuman()

            return render_folder_mayorista_tucuman()

        archivo = request.files.get("archivo")

        fecha_desde = request.form.get(
            "fecha_desde",
            "",
        ).strip()

        fecha_hasta = request.form.get(
            "fecha_hasta",
            "",
        ).strip()

        usuario = session.get(
            "usuario_nombre",
            "desconocido",
        )

        nombre_archivo = None

        try:
            validar_fechas_folder_tucuman(
                fecha_desde,
                fecha_hasta,
            )

            nombre_archivo = validar_archivo_excel(
                archivo
            )

            (
                df,
                _,
                mensaje_error,
                _,
            ) = procesar_archivo_cenefas(
                archivo=archivo,
                tipo="mayorista",
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
            )

            if df is None:
                raise ValueError(
                    mensaje_error
                    or (
                        "No se pudo procesar "
                        "el archivo."
                    )
                )

            if df.empty:
                raise ValueError(
                    "El archivo no contiene "
                    "registros válidos."
                )

            # Datos protegidos.
            df["sucursales"] = (
                SUCURSALES_MAYORISTA_TUCUMAN
            )

            df["desde"] = fecha_desde
            df["hasta"] = fecha_hasta

            df = df.reset_index(drop=True)

            validar_dataframe_antes_transmitir(
                df
            )

            token = guardar_folder_tucuman_temporal(
                df=df,
                usuario=usuario,
                archivo_nombre=nombre_archivo,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
            )

            datos_preview = (
                df.fillna("")
                .to_dict(orient="records")
            )

            guardar_log_compras(
                usuario=usuario,
                nivel="INFO",
                origen="backend",
                modulo=(
                    "folder_mayorista_tucuman"
                ),
                accion=(
                    "Previsualizar folder"
                ),
                archivo=nombre_archivo,
                detalle=(
                    "Archivo procesado y "
                    "almacenado temporalmente. "
                    "Pendiente de transmisión."
                ),
                estado="exitoso",
                total_registros=len(df),
            )

            return render_folder_mayorista_tucuman(
                datos_preview=datos_preview,
                token=token,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                total_registros=len(df),
            )

        except Exception as error:
            guardar_log_compras(
                usuario=usuario,
                nivel="ERROR",
                origen="validacion",
                modulo=(
                    "folder_mayorista_tucuman"
                ),
                accion=(
                    "Error previsualizando folder"
                ),
                archivo=(
                    nombre_archivo
                    or (
                        archivo.filename
                        if archivo
                        else None
                    )
                ),
                detalle=str(error),
                estado="fallido",
                total_registros=0,
            )

            return render_folder_mayorista_tucuman(
                mensaje_error=str(error),
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                status_code=400,
            )


    @compras_bp.route(
        "/folder/mayorista/tucuman/transmitir",
        methods=["POST"],
        endpoint=(
            "transmitir_folder_mayorista_tucuman"
        ),
    )
    @login_requerido("compras")
    def transmitir_folder_mayorista_tucuman():
        token = request.form.get(
            "token",
            "",
        ).strip()

        cambios_json = request.form.get(
            "cambios",
            "[]",
        )

        sobrescribir = (
            request.form.get("sobrescribir")
            == "1"
        )

        usuario = session.get(
            "usuario_nombre",
            "desconocido",
        )

        df, metadata = (
            recuperar_folder_tucuman_temporal(
                token
            )
        )

        if df is None or metadata is None:
            return render_folder_mayorista_tucuman(
                mensaje_error=(
                    "La previsualización venció, "
                    "fue eliminada o no existe. "
                    "Debe volver a cargar el archivo."
                ),
                status_code=400,
            )

        try:
            if (
                metadata.get("usuario")
                != usuario
            ):
                raise PermissionError(
                    "El lote temporal pertenece "
                    "a otro usuario."
                )

            if (
                metadata.get("region")
                != "tucuman"
            ):
                raise ValueError(
                    "El lote no corresponde "
                    "a Tucumán."
                )

            if (
                metadata.get("tipo_cenefa")
                != TIPO_CENEFA_MAYORISTA_TUCUMAN
            ):
                raise ValueError(
                    "El tipo de folder temporal "
                    "no es válido."
                )

            cambios = normalizar_cambios_json(
                cambios_json
            )

            df = aplicar_cambios_folder_tucuman(
                df=df,
                cambios=cambios,
                limpiar_precio=limpiar_precio,
            )

            # Datos críticos protegidos.
            df["desde"] = metadata[
                "fecha_desde"
            ]

            df["hasta"] = metadata[
                "fecha_hasta"
            ]

            df["sucursales"] = (
                SUCURSALES_MAYORISTA_TUCUMAN
            )

            validar_dataframe_antes_transmitir(
                df
            )

            repetidos = (
                existen_repetidos_folder_tucuman(
                    df=df,
                    get_db_connection=(
                        get_db_connection
                    ),
                )
            )

            if repetidos and not sobrescribir:
                datos_preview = (
                    df.fillna("")
                    .to_dict(
                        orient="records"
                    )
                )

                return render_folder_mayorista_tucuman(
                    datos_preview=datos_preview,
                    token=token,
                    mensaje_error=(
                        f"Se encontraron "
                        f"{len(repetidos)} registros "
                        "existentes para el mismo "
                        "código, período y sucursal. "
                        "Confirme el reemplazo."
                    ),
                    fecha_desde=metadata[
                        "fecha_desde"
                    ],
                    fecha_hasta=metadata[
                        "fecha_hasta"
                    ],
                    total_registros=len(df),
                    requiere_sobrescribir=True,
                )

            lote_carga, fecha_carga = (
                guardar_cenefas_en_db(
                    df=df,
                    tipo_cenefa=(
                        TIPO_CENEFA_MAYORISTA_TUCUMAN
                    ),
                    usuario=usuario,
                    sobrescribir=sobrescribir,
                )
            )

            datos_transmitidos = (
                obtener_lote_folder_tucuman(
                    lote_carga=lote_carga,
                    get_db_connection=(
                        get_db_connection
                    ),
                    formatear_precio_arg=(
                        formatear_precio_arg
                    ),
                )
            )

            if (
                len(datos_transmitidos)
                != len(df)
            ):
                raise RuntimeError(
                    "La cantidad de registros "
                    "consultados después de la "
                    "transmisión no coincide con "
                    "la cantidad procesada."
                )

            eliminar_folder_tucuman_temporal(
                token
            )

            guardar_log_compras(
                usuario=usuario,
                nivel="INFO",
                origen="backend",
                modulo=(
                    "folder_mayorista_tucuman"
                ),
                accion="Transmitir folder",
                archivo=metadata.get(
                    "archivo"
                ),
                detalle=(
                    "Folder Mayorista Tucumán "
                    "transmitido correctamente "
                    f"a {SUCURSALES_MAYORISTA_TUCUMAN}. "
                    f"Lote: {lote_carga}."
                ),
                estado="exitoso",
                total_registros=len(
                    datos_transmitidos
                ),
            )

            return render_folder_mayorista_tucuman(
                datos_transmitidos=(
                    datos_transmitidos
                ),
                mensaje_exito=(
                    "Folder transmitido "
                    "correctamente a "
                    f"{SUCURSALES_MAYORISTA_TUCUMAN}."
                ),
                fecha_desde=metadata[
                    "fecha_desde"
                ],
                fecha_hasta=metadata[
                    "fecha_hasta"
                ],
                total_registros=len(
                    datos_transmitidos
                ),
                lote_carga=lote_carga,
                fecha_carga=fecha_carga,
            )

        except PermissionError as error:
            guardar_log_compras(
                usuario=usuario,
                nivel="ERROR",
                origen="seguridad",
                modulo=(
                    "folder_mayorista_tucuman"
                ),
                accion=(
                    "Transmisión rechazada"
                ),
                archivo=metadata.get(
                    "archivo"
                ),
                detalle=str(error),
                estado="fallido",
                total_registros=0,
            )

            return render_folder_mayorista_tucuman(
                mensaje_error=str(error),
                status_code=403,
            )

        except psycopg2.Error as error:
            guardar_log_compras(
                usuario=usuario,
                nivel="CRITICAL",
                origen="base_datos",
                modulo=(
                    "folder_mayorista_tucuman"
                ),
                accion=(
                    "Error transmitiendo folder"
                ),
                archivo=metadata.get(
                    "archivo"
                ),
                detalle=str(error),
                estado="fallido",
                total_registros=len(df),
            )

            return render_folder_mayorista_tucuman(
                datos_preview=(
                    df.fillna("")
                    .to_dict(
                        orient="records"
                    )
                ),
                token=token,
                mensaje_error=(
                    "Error de base de datos: "
                    f"{error}"
                ),
                fecha_desde=metadata[
                    "fecha_desde"
                ],
                fecha_hasta=metadata[
                    "fecha_hasta"
                ],
                total_registros=len(df),
                status_code=500,
            )

        except Exception as error:
            guardar_log_compras(
                usuario=usuario,
                nivel="ERROR",
                origen="backend",
                modulo=(
                    "folder_mayorista_tucuman"
                ),
                accion=(
                    "Excepción transmitiendo folder"
                ),
                archivo=metadata.get(
                    "archivo"
                ),
                detalle=str(error),
                estado="fallido",
                total_registros=(
                    len(df)
                    if df is not None
                    else 0
                ),
            )

            return render_folder_mayorista_tucuman(
                datos_preview=(
                    df.fillna("")
                    .to_dict(
                        orient="records"
                    )
                ),
                token=token,
                mensaje_error=(
                    "Error transmitiendo "
                    f"el folder: {error}"
                ),
                fecha_desde=metadata.get(
                    "fecha_desde",
                    "",
                ),
                fecha_hasta=metadata.get(
                    "fecha_hasta",
                    "",
                ),
                total_registros=len(df),
                status_code=500,
            )