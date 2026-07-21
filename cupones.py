from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import pandas as pd
import uuid
import math
import json
import re
from datetime import datetime

from database.db import get_db_connection
from compras import redis_client

cupones_bp = Blueprint("cupones", __name__, url_prefix="/cupones")


def normalizar_sucursal_sorteo(valor):
    if valor is None:
        return ""

    valor = str(valor).strip().upper()

    if not valor:
        return ""

    # Normalizar acentos y espacios
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

    # ALBERDISA 16 / ALBERDISA16
    coincidencia = re.fullmatch(r"ALBERDISA\s*0*(\d{1,2})", valor)

    if coincidencia:
        numero = int(coincidencia.group(1))
        return f"CO{numero:02d}"

    # COMODIN 16 / COMODÍN 16
    coincidencia = re.fullmatch(r"COMODIN\s*0*(\d{1,2})", valor)

    if coincidencia:
        numero = int(coincidencia.group(1))
        return f"CO{numero:02d}"

    # SUCURSAL 16
    coincidencia = re.fullmatch(r"SUCURSAL\s*0*(\d{1,2})", valor)

    if coincidencia:
        numero = int(coincidencia.group(1))
        return f"CO{numero:02d}"

    # CO16 / CO 16 / CO016
    coincidencia = re.fullmatch(r"CO\s*0*(\d{1,2})", valor)

    if coincidencia:
        numero = int(coincidencia.group(1))
        return f"CO{numero:02d}"

    # MAYORISTA 2 / MAYORISTA02
    coincidencia = re.fullmatch(r"MAYORISTA\s*0*(\d{1,2})", valor)

    if coincidencia:
        numero = int(coincidencia.group(1))
        return f"MA{numero:02d}"

    # MA2 / MA 02
    coincidencia = re.fullmatch(r"MA\s*0*(\d{1,2})", valor)

    if coincidencia:
        numero = int(coincidencia.group(1))
        return f"MA{numero:02d}"

    return valor

#Funciones Auxiliares

def limpiar_valor(valor, defecto=""):
    if valor is None:
        return defecto

    try:
        if pd.isna(valor):
            return defecto
    except Exception:
        pass

    return valor


def limpiar_texto(valor):
    valor = limpiar_valor(valor, "")
    return str(valor).strip()


def limpiar_entero(valor):
    valor = limpiar_valor(valor, 0)

    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return 0


def limpiar_decimal(valor):
    valor = limpiar_valor(valor, 0)

    if isinstance(valor, str):
        valor = valor.strip()

        if not valor:
            return 0

        # Soporta valores como 1.234,56
        if "," in valor:
            valor = valor.replace(".", "").replace(",", ".")

    try:
        numero = float(valor)

        if math.isnan(numero):
            return 0

        return numero
    except (TypeError, ValueError):
        return 0


def limpiar_fecha(valor):
    valor = limpiar_valor(valor, None)

    if valor in (None, ""):
        return None

    try:
        if isinstance(valor, pd.Timestamp):
            return valor.to_pydatetime()

        if isinstance(valor, datetime):
            return valor

        valor_texto = str(valor).strip()

        if not valor_texto:
            return None

        formatos = [
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y",
        ]

        for formato in formatos:
            try:
                return datetime.strptime(
                    valor_texto,
                    formato,
                )
            except ValueError:
                continue

        fecha = pd.to_datetime(
            valor_texto,
            errors="coerce",
            dayfirst=True,
        )

        if pd.isna(fecha):
            return None

        return fecha.to_pydatetime()

    except Exception as error:
        print(
            "ERROR CONVIRTIENDO FECHA:",
            repr(valor),
            repr(error),
            flush=True,
        )
        return None


def obtener_valor_fila(fila, *columnas):
    """
    Devuelve el primer valor encontrado entre varios nombres posibles
    de columna.
    """

    for columna in columnas:
        if columna in fila.index:
            valor = fila.get(columna)

            if not pd.isna(valor):
                return valor

    return ""

def crear_tabla_cupones_sorteo():
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
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
        """)
        conn.commit()
    finally:
        cur.close()
        conn.close()


@cupones_bp.route("/", methods=["GET", "POST"])
def index():
    if session.get("usuario_rol") != "publicidad":
        return redirect(url_for("sistemas.login"))

    cupones = []
    total_filas = 0
    total_cupones = 0
    cache_id = ""

    if request.method == "POST":
        archivo = request.files.get("archivo")

        if not archivo or archivo.filename == "":
            flash("Debe seleccionar un archivo Excel", "warning")
            return redirect(url_for("cupones.index"))

        try:
            df = pd.read_excel(archivo)
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
            return redirect(url_for("cupones.index"))

        print(
            "COLUMNAS DEL EXCEL:",
            [repr(columna) for columna in df.columns],
            flush=True,
        )

        total_filas = len(df)
        lote_carga = str(uuid.uuid4())

        filas_sin_id = 0
        filas_sin_fecha = 0

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

            if estado not in ["Facturado", "Entregado"]:
                continue

            sucursal_origen = limpiar_texto(
                obtener_valor_fila(
                    fila,
                    "Tienda",
                    "Sucursal",
                    "Sucursal origen",
                )
            )

            sucursal_codigo = normalizar_sucursal_sorteo(
                sucursal_origen
            )

            id_secuencia = limpiar_texto(
                obtener_valor_fila(
                    fila,
                    "ID de secuencia",
                    "Id de secuencia",
                    "ID Secuencia",
                    "Id secuencia",
                    "Secuencia",
                )
            )

            id_pedido = limpiar_texto(
                obtener_valor_fila(
                    fila,
                    "ID de pedido",
                    "Id de pedido",
                    "ID Pedido",
                    "Id pedido",
                    "Pedido",
                    "Nro Pedido",
                    "Número pedido",
                    "Numero pedido",
                    "Order ID",
                    "Order Id",
                )
            )

            ecommerce_prod_id = limpiar_texto(
                obtener_valor_fila(
                    fila,
                    "Ecommerce Prod ID",
                    "Ecommerce Prod Id",
                    "Ecommerce prod id",
                    "ID Ecommerce",
                )
            )

            fecha_excel = obtener_valor_fila(
                fila,
                "Fecha de creación",
                "Fecha de creacion",
                "Fecha creación",
                "Fecha Creacion",
            )

            fecha_creacion = limpiar_fecha(fecha_excel)

            fecha_entrega = limpiar_fecha(
                obtener_valor_fila(
                    fila,
                    "Fecha de entrega",
                    "Fecha entrega",
                    "Fecha Entrega",
                )
            )

            fecha_pickeo = limpiar_fecha(
                obtener_valor_fila(
                    fila,
                    "Fecha de pickeo",
                    "Fecha pickeo",
                    "Fecha Pickeo",
                )
            )

            limite_entrega = limpiar_fecha(
                obtener_valor_fila(
                    fila,
                    "Límite de entrega",
                    "Limite de entrega",
                    "Límite entrega",
                    "Limite entrega",
                    "Fecha límite entrega",
                    "Fecha limite entrega",
                )
            )

            if numero_fila <= 7:
                print(
                    "DEBUG FILA:",
                    numero_fila,
                    "| ID PEDIDO:",
                    repr(id_pedido),
                    "| FECHA ORIGINAL:",
                    repr(fecha_excel),
                    "| TIPO:",
                    type(fecha_excel).__name__,
                    "| FECHA CONVERTIDA:",
                    fecha_creacion,
                    flush=True,
                )

            if not id_pedido:
                filas_sin_id += 1

                if filas_sin_id <= 10:
                    print(
                        "FILA OMITIDA POR FALTA DE ID:",
                        numero_fila,
                        flush=True,
                    )

                continue

            if fecha_creacion is None:
                filas_sin_fecha += 1

                if filas_sin_fecha <= 10:
                    print(
                        "FECHA DE CREACION NO RECONOCIDA:",
                        "FILA:",
                        numero_fila,
                        "VALOR:",
                        repr(fecha_excel),
                        flush=True,
                    )

            registro = {
                "nombre": limpiar_texto(
                    obtener_valor_fila(
                        fila,
                        "Cliente",
                    )
                ),

                "dni": limpiar_texto(
                    obtener_valor_fila(
                        fila,
                        "Documento cliente",
                        "Documento Cliente",
                        "DNI",
                    )
                ),

                "telefono": limpiar_texto(
                    obtener_valor_fila(
                        fila,
                        "Teléfono",
                        "Telefono",
                    )
                ),

                "sucursal": sucursal_origen,
                "sucursal_codigo": sucursal_codigo,
                "estado": estado,

                "id_secuencia": id_secuencia,
                "id_pedido": id_pedido,
                "ecommerce_prod_id": ecommerce_prod_id,

                "fecha_creacion": fecha_creacion,
                "fecha_entrega": fecha_entrega,
                "fecha_pickeo": fecha_pickeo,
                "limite_entrega": limite_entrega,

                "email_cliente": limpiar_texto(
                    obtener_valor_fila(
                        fila,
                        "Email de cliente",
                        "Email cliente",
                        "Email Cliente",
                        "Email",
                    )
                ),

                "transportadora": limpiar_texto(
                    obtener_valor_fila(
                        fila,
                        "Transportadora",
                        "Método de entrega",
                        "Metodo de entrega",
                        "Modalidad entrega",
                    )
                ),

                "ruta": limpiar_texto(
                    obtener_valor_fila(
                        fila,
                        "Ruta",
                    )
                ),

                "persona_recibe": limpiar_texto(
                    obtener_valor_fila(
                        fila,
                        "Persona que recibe",
                        "Persona recibe",
                    )
                ),

                "direccion_entrega": limpiar_texto(
                    obtener_valor_fila(
                        fila,
                        "Dirección de entrega",
                        "Direccion de entrega",
                        "Dirección entrega",
                        "Direccion entrega",
                        "Dirección",
                        "Direccion",
                    )
                ),

                "medio_pago": limpiar_texto(
                    obtener_valor_fila(
                        fila,
                        "Medio de pago",
                        "Medio pago",
                        "Modalidad pago",
                    )
                ),

                "banco": limpiar_texto(
                    obtener_valor_fila(
                        fila,
                        "Banco",
                    )
                ),

                "estado_transaccion": limpiar_texto(
                    obtener_valor_fila(
                        fila,
                        "Estado de la transacción",
                        "Estado de la transaccion",
                        "Estado transacción",
                        "Estado transaccion",
                    )
                ),

                "cantidad_productos": limpiar_entero(
                    obtener_valor_fila(
                        fila,
                        "Cantidad de productos",
                        "Cantidad productos",
                        "Qty",
                    )
                ),

                "productos_faltantes": limpiar_entero(
                    obtener_valor_fila(
                        fila,
                        "Cantidad de productos faltantes",
                        "Cantidad productos faltantes",
                        "Productos faltantes",
                        "Cantidad faltantes",
                    )
                ),

                "lote_carga": lote_carga,
            }

            cupones.append(registro)

        total_cupones = len(cupones)

        print(
            "RESUMEN PROCESAMIENTO:",
            "TOTAL EXCEL:",
            total_filas,
            "| PROCESADOS:",
            total_cupones,
            "| SIN ID:",
            filas_sin_id,
            "| SIN FECHA:",
            filas_sin_fecha,
            flush=True,
        )

        if cupones:
            cache_id = str(uuid.uuid4())

            try:
                redis_client.setex(
                    f"cupones_sorteo:{cache_id}",
                    3600,
                    json.dumps(
                        cupones,
                        ensure_ascii=False,
                        default=str,
                    ),
                )

                print(
                    "CUPONES GUARDADOS EN REDIS:",
                    total_cupones,
                    "CACHE ID:",
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

                return redirect(url_for("cupones.index"))

        else:
            flash(
                "No se encontraron pedidos Facturados o Entregados con ID válido.",
                "warning",
            )

    return render_template(
        "publicidad/cupones.html",
        cupones=cupones,
        cache_id=cache_id,
        total_filas=total_filas,
        total_cupones=total_cupones,
    )


@cupones_bp.route("/transmitir_sucursales", methods=["POST"])
def transmitir_sucursales():
    if session.get("usuario_rol") != "publicidad":
        return redirect(url_for("sistemas.login"))

    cache_id = request.form.get("cache_id", "").strip()

    if not cache_id:
        flash(
            "No se recibió el identificador de los datos procesados.",
            "warning",
        )
        return redirect(url_for("cupones.index"))

    clave_redis = f"cupones_sorteo:{cache_id}"

    try:
        datos_redis = redis_client.get(clave_redis)

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
        return redirect(url_for("cupones.index"))

    if not datos_redis:
        flash(
            "Los datos procesados expiraron o ya fueron transmitidos.",
            "warning",
        )
        return redirect(url_for("cupones.index"))

    try:
        if isinstance(datos_redis, bytes):
            datos_redis = datos_redis.decode("utf-8")

        registros = json.loads(datos_redis)

    except Exception as error:
        print(
            "ERROR DECODIFICANDO DATOS DE REDIS:",
            repr(error),
            flush=True,
        )

        flash(
            "Los datos temporales no tienen un formato válido.",
            "danger",
        )
        return redirect(url_for("cupones.index"))

    if not registros:
        flash(
            "No hay pedidos procesados para transmitir.",
            "warning",
        )
        return redirect(url_for("cupones.index"))

    conn = None
    cur = None

    insertados = 0
    actualizados = 0
    omitidos = 0

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        for registro in registros:
            id_pedido = limpiar_texto(
                registro.get("id_pedido")
            )

            if not id_pedido:
                omitidos += 1
                continue

            sucursal_codigo = normalizar_sucursal_sorteo(
                registro.get("sucursal_codigo")
                or registro.get("sucursal")
            )

            fecha_creacion = limpiar_fecha(
                registro.get("fecha_creacion")
            )

            fecha_entrega = limpiar_fecha(
                registro.get("fecha_entrega")
            )

            fecha_pickeo = limpiar_fecha(
                registro.get("fecha_pickeo")
            )

            limite_entrega = limpiar_fecha(
                registro.get("limite_entrega")
            )

            cur.execute(
                """
                SELECT 1
                FROM informes
                WHERE id_pedido = %s
                LIMIT 1
                """,
                (id_pedido,),
            )

            pedido_existente = cur.fetchone() is not None

            if pedido_existente:
                cur.execute(
                    """
                    UPDATE informes
                    SET
                        id_secuencia = %s,
                        ecommerce_prod_id = %s,
                        fecha_creacion = %s,
                        fecha_entrega = %s,
                        fecha_pickeo = %s,
                        limite_entrega = %s,
                        documento_cliente = %s,
                        cliente = %s,
                        email_cliente = %s,
                        telefono = %s,
                        sucursal_codigo = %s,
                        estado = %s,
                        transportadora = %s,
                        ruta = %s,
                        persona_recibe = %s,
                        direccion_entrega = %s,
                        medio_pago = %s,
                        banco = %s,
                        estado_transaccion = %s,
                        cantidad_productos = %s,
                        productos_faltantes = %s,
                        lote_carga = %s
                    WHERE id_pedido = %s
                    """,
                    (
                        limpiar_texto(
                            registro.get("id_secuencia")
                        ),
                        limpiar_texto(
                            registro.get("ecommerce_prod_id")
                        ),
                        fecha_creacion,
                        fecha_entrega,
                        fecha_pickeo,
                        limite_entrega,
                        limpiar_texto(
                            registro.get("dni")
                        ),
                        limpiar_texto(
                            registro.get("nombre")
                        ),
                        limpiar_texto(
                            registro.get("email_cliente")
                        ),
                        limpiar_texto(
                            registro.get("telefono")
                        ),
                        sucursal_codigo,
                        limpiar_texto(
                            registro.get("estado")
                        ),
                        limpiar_texto(
                            registro.get("transportadora")
                        ),
                        limpiar_texto(
                            registro.get("ruta")
                        ),
                        limpiar_texto(
                            registro.get("persona_recibe")
                        ),
                        limpiar_texto(
                            registro.get("direccion_entrega")
                        ),
                        limpiar_texto(
                            registro.get("medio_pago")
                        ),
                        limpiar_texto(
                            registro.get("banco")
                        ),
                        limpiar_texto(
                            registro.get("estado_transaccion")
                        ),
                        limpiar_entero(
                            registro.get("cantidad_productos")
                        ),
                        limpiar_entero(
                            registro.get("productos_faltantes")
                        ),
                        limpiar_texto(
                            registro.get("lote_carga")
                        ),
                        id_pedido,
                    ),
                )

                actualizados += 1

            else:
                cur.execute(
                    """
                    INSERT INTO informes (
                        id_secuencia,
                        id_pedido,
                        ecommerce_prod_id,
                        fecha_creacion,
                        fecha_entrega,
                        fecha_pickeo,
                        limite_entrega,
                        documento_cliente,
                        cliente,
                        email_cliente,
                        telefono,
                        sucursal_codigo,
                        estado,
                        transportadora,
                        ruta,
                        persona_recibe,
                        direccion_entrega,
                        medio_pago,
                        banco,
                        estado_transaccion,
                        cantidad_productos,
                        productos_faltantes,
                        lote_carga
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        limpiar_texto(
                            registro.get("id_secuencia")
                        ),
                        id_pedido,
                        limpiar_texto(
                            registro.get("ecommerce_prod_id")
                        ),
                        fecha_creacion,
                        fecha_entrega,
                        fecha_pickeo,
                        limite_entrega,
                        limpiar_texto(
                            registro.get("dni")
                        ),
                        limpiar_texto(
                            registro.get("nombre")
                        ),
                        limpiar_texto(
                            registro.get("email_cliente")
                        ),
                        limpiar_texto(
                            registro.get("telefono")
                        ),
                        sucursal_codigo,
                        limpiar_texto(
                            registro.get("estado")
                        ),
                        limpiar_texto(
                            registro.get("transportadora")
                        ),
                        limpiar_texto(
                            registro.get("ruta")
                        ),
                        limpiar_texto(
                            registro.get("persona_recibe")
                        ),
                        limpiar_texto(
                            registro.get("direccion_entrega")
                        ),
                        limpiar_texto(
                            registro.get("medio_pago")
                        ),
                        limpiar_texto(
                            registro.get("banco")
                        ),
                        limpiar_texto(
                            registro.get("estado_transaccion")
                        ),
                        limpiar_entero(
                            registro.get("cantidad_productos")
                        ),
                        limpiar_entero(
                            registro.get("productos_faltantes")
                        ),
                        limpiar_texto(
                            registro.get("lote_carga")
                        ),
                    ),
                )

                insertados += 1

        conn.commit()

        redis_client.delete(clave_redis)

        print(
            "TRANSMISION FINALIZADA:",
            "INSERTADOS:",
            insertados,
            "| ACTUALIZADOS:",
            actualizados,
            "| OMITIDOS:",
            omitidos,
            flush=True,
        )

        flash(
            (
                f"Transmisión finalizada. "
                f"Insertados: {insertados}. "
                f"Actualizados: {actualizados}. "
                f"Omitidos: {omitidos}."
            ),
            "success",
        )

    except Exception as error:
        if conn:
            conn.rollback()

        print(
            "ERROR TRANSMITIENDO PEDIDOS:",
            repr(error),
            flush=True,
        )

        flash(
            f"No se pudieron transmitir los pedidos: {error}",
            "danger",
        )

    finally:
        if cur:
            cur.close()

        if conn:
            conn.close()

    return redirect(url_for("cupones.index"))

@cupones_bp.route("/sucursales_sorteo")
def sucursales_sorteo():
    if session.get("usuario_rol") != "sucursal":
        return redirect(url_for("sistemas.login"))

    crear_tabla_cupones_sorteo()

    sucursal_codigo = session.get("usuario_nombre", "").strip().upper()

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT
                nombre,
                dni,
                telefono,
                sucursal_origen,
                sucursal_codigo,
                estado,
                fecha_transmision
            FROM cupones_sorteo
            WHERE sucursal_codigo = %s
            ORDER BY fecha_transmision DESC, id DESC
        """, (sucursal_codigo,))

        cupones = cur.fetchall()

    finally:
        cur.close()
        conn.close()

    return render_template(
        "publicidad/sucursales_sorteo.html",
        cupones=cupones,
        sucursal=sucursal_codigo
    )