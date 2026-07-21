from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import pandas as pd
import uuid
import math
import json

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
        fecha = pd.to_datetime(valor, errors="coerce")

        if pd.isna(fecha):
            return None

        return fecha.to_pydatetime()
    except Exception:
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
            flash("Debe seleccionar un archivo Excel")
            return redirect(url_for("cupones.index"))

        df = pd.read_excel(archivo)
        total_filas = len(df)

        lote_carga = str(uuid.uuid4())

        for _, fila in df.iterrows():
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

            id_pedido = limpiar_texto(
                obtener_valor_fila(
                    fila,
                    "Id pedido",
                    "ID Pedido",
                    "Pedido",
                    "Nro Pedido",
                    "Número pedido",
                    "Numero pedido",
                    "Order Id",
                )
            )

            if not id_pedido:
                id_pedido = str(uuid.uuid4())

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

                "id_secuencia": limpiar_texto(
                    obtener_valor_fila(
                        fila,
                        "Id secuencia",
                        "ID Secuencia",
                        "Secuencia",
                    )
                ),
                "id_pedido": id_pedido,
                "ecommerce_prod_id": limpiar_texto(
                    obtener_valor_fila(
                        fila,
                        "Ecommerce prod id",
                        "Ecommerce Prod Id",
                        "ID Ecommerce",
                    )
                ),

                "fecha_creacion": limpiar_texto(
                    obtener_valor_fila(
                        fila,
                        "Fecha creación",
                        "Fecha Creacion",
                        "Fecha pedido",
                        "Fecha Pedido",
                    )
                ),
                "fecha_entrega": limpiar_texto(
                    obtener_valor_fila(
                        fila,
                        "Fecha entrega",
                        "Fecha Entrega",
                    )
                ),
                "fecha_pickeo": limpiar_texto(
                    obtener_valor_fila(
                        fila,
                        "Fecha pickeo",
                        "Fecha Pickeo",
                    )
                ),
                "limite_entrega": limpiar_texto(
                    obtener_valor_fila(
                        fila,
                        "Límite entrega",
                        "Limite entrega",
                        "Fecha límite entrega",
                    )
                ),

                "email_cliente": limpiar_texto(
                    obtener_valor_fila(
                        fila,
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
                        "Persona recibe",
                        "Persona que recibe",
                    )
                ),
                "direccion_entrega": limpiar_texto(
                    obtener_valor_fila(
                        fila,
                        "Dirección entrega",
                        "Direccion entrega",
                        "Dirección",
                        "Direccion",
                    )
                ),

                "medio_pago": limpiar_texto(
                    obtener_valor_fila(
                        fila,
                        "Medio pago",
                        "Medio de pago",
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
                        "Estado transacción",
                        "Estado transaccion",
                    )
                ),

                "cantidad_productos": limpiar_entero(
                    obtener_valor_fila(
                        fila,
                        "Cantidad productos",
                        "Cantidad de productos",
                    )
                ),
                "productos_faltantes": limpiar_entero(
                    obtener_valor_fila(
                        fila,
                        "Productos faltantes",
                        "Cantidad faltantes",
                    )
                ),

                "lote_carga": lote_carga,
            }

            cupones.append(registro)

        total_cupones = len(cupones)
    
        if cupones:
                cache_id = str(uuid.uuid4())

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

    # ======================================================
    # RECUPERAR DATOS DESDE REDIS
    # ======================================================

    cache_id = request.form.get("cache_id", "").strip()

    print("DEBUG TRANSMITIR CUPONES:", flush=True)
    print("CACHE ID RECIBIDO:", cache_id, flush=True)
    print("ROL:", session.get("usuario_rol"), flush=True)

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
            "Los datos procesados vencieron o no fueron encontrados. "
            "Procesá nuevamente el archivo.",
            "warning",
        )
        return redirect(url_for("cupones.index"))

    try:
        if isinstance(datos_redis, bytes):
            datos_redis = datos_redis.decode("utf-8")

        cupones = json.loads(datos_redis)

    except Exception as error:
        print(
            "ERROR DECODIFICANDO DATOS DE REDIS:",
            repr(error),
            flush=True,
        )

        flash(
            "Los datos almacenados no tienen un formato válido.",
            "danger",
        )
        return redirect(url_for("cupones.index"))

    print(
        "CUPONES RECUPERADOS DESDE REDIS:",
        len(cupones),
        flush=True,
    )

    if not cupones:
        flash(
            "No hay cupones para transmitir.",
            "warning",
        )
        return redirect(url_for("cupones.index"))

    # ======================================================
    # PREPARAR BASE DE DATOS
    # ======================================================

    crear_tabla_cupones_sorteo()

    conn = get_db_connection()
    cur = conn.cursor()

    cupones_insertados = 0
    informes_insertados = 0

    try:
        for cupon in cupones:
            sucursal_origen = limpiar_texto(
                cupon.get("sucursal", "")
            )

            sucursal_codigo = normalizar_sucursal_sorteo(
                sucursal_origen
            )

            # ==================================================
            # CUPONES PARA SUCURSALES
            # ==================================================

            cur.execute("""
                INSERT INTO cupones_sorteo (
                    nombre,
                    dni,
                    telefono,
                    sucursal_origen,
                    sucursal_codigo,
                    estado
                )
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                limpiar_texto(cupon.get("nombre")),
                limpiar_texto(cupon.get("dni")),
                limpiar_texto(cupon.get("telefono")),
                sucursal_origen,
                sucursal_codigo,
                limpiar_texto(cupon.get("estado")),
            ))

            cupones_insertados += 1

            # ==================================================
            # INFORMES ECOMMERCE
            # ==================================================

            id_pedido = limpiar_texto(
                cupon.get("id_pedido")
            )

            if not id_pedido:
                id_pedido = str(uuid.uuid4())

            cur.execute("""
                INSERT INTO informes (
                    id_secuencia,
                    id_pedido,
                    ecommerce_prod_id,

                    fecha_creacion,
                    fecha_entrega,
                    fecha_pickeo,
                    limite_entrega,

                    sucursal_codigo,

                    documento_cliente,
                    cliente,
                    email_cliente,
                    telefono,

                    transportadora,
                    ruta,
                    persona_recibe,
                    direccion_entrega,

                    medio_pago,
                    banco,

                    estado,
                    estado_transaccion,

                    cantidad_productos,
                    productos_faltantes,

                    usuario_carga,
                    lote_carga
                )
                VALUES (
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s
                )

                ON CONFLICT (id_pedido)
                DO UPDATE SET
                    id_secuencia = EXCLUDED.id_secuencia,
                    ecommerce_prod_id = EXCLUDED.ecommerce_prod_id,

                    fecha_creacion = EXCLUDED.fecha_creacion,
                    fecha_entrega = EXCLUDED.fecha_entrega,
                    fecha_pickeo = EXCLUDED.fecha_pickeo,
                    limite_entrega = EXCLUDED.limite_entrega,

                    sucursal_codigo = EXCLUDED.sucursal_codigo,

                    documento_cliente = EXCLUDED.documento_cliente,
                    cliente = EXCLUDED.cliente,
                    email_cliente = EXCLUDED.email_cliente,
                    telefono = EXCLUDED.telefono,

                    transportadora = EXCLUDED.transportadora,
                    ruta = EXCLUDED.ruta,
                    persona_recibe = EXCLUDED.persona_recibe,
                    direccion_entrega = EXCLUDED.direccion_entrega,

                    medio_pago = EXCLUDED.medio_pago,
                    banco = EXCLUDED.banco,

                    estado = EXCLUDED.estado,
                    estado_transaccion = EXCLUDED.estado_transaccion,

                    cantidad_productos = EXCLUDED.cantidad_productos,
                    productos_faltantes = EXCLUDED.productos_faltantes,

                    usuario_carga = EXCLUDED.usuario_carga,
                    lote_carga = EXCLUDED.lote_carga
            """, (
                limpiar_texto(cupon.get("id_secuencia")),
                id_pedido,
                limpiar_texto(cupon.get("ecommerce_prod_id")),

                limpiar_fecha(cupon.get("fecha_creacion")),
                limpiar_fecha(cupon.get("fecha_entrega")),
                limpiar_fecha(cupon.get("fecha_pickeo")),
                limpiar_fecha(cupon.get("limite_entrega")),

                sucursal_codigo or None,

                limpiar_texto(cupon.get("dni")),
                limpiar_texto(cupon.get("nombre")),
                limpiar_texto(cupon.get("email_cliente")),
                limpiar_texto(cupon.get("telefono")),

                limpiar_texto(cupon.get("transportadora")),
                limpiar_texto(cupon.get("ruta")),
                limpiar_texto(cupon.get("persona_recibe")),
                limpiar_texto(cupon.get("direccion_entrega")),

                limpiar_texto(cupon.get("medio_pago")),
                limpiar_texto(cupon.get("banco")),

                limpiar_texto(cupon.get("estado")),
                limpiar_texto(cupon.get("estado_transaccion")),

                limpiar_entero(
                    cupon.get("cantidad_productos")
                ),
                limpiar_entero(
                    cupon.get("productos_faltantes")
                ),

                limpiar_texto(
                    session.get("usuario_nombre")
                ),
                limpiar_texto(
                    cupon.get("lote_carga")
                ),
            ))

            informes_insertados += 1

        # Confirmar ambas inserciones en una sola transacción
        conn.commit()

        # El caché se elimina solamente cuando PostgreSQL terminó bien
        try:
            redis_client.delete(clave_redis)

            print(
                "CACHE REDIS ELIMINADO:",
                clave_redis,
                flush=True,
            )

        except Exception as error:
            print(
                "ADVERTENCIA: NO SE PUDO ELIMINAR EL CACHE REDIS:",
                repr(error),
                flush=True,
            )

        print(
            "CUPONES INSERTADOS:",
            cupones_insertados,
            flush=True,
        )

        print(
            "INFORMES INSERTADOS/ACTUALIZADOS:",
            informes_insertados,
            flush=True,
        )

        flash(
            f"Proceso completado: "
            f"{cupones_insertados} cupones transmitidos y "
            f"{informes_insertados} pedidos enviados a informes.",
            "success",
        )

    except Exception as error:
        conn.rollback()

        import traceback

        print(
            "ERROR TRANSMITIENDO CUPONES E INFORMES:",
            repr(error),
            flush=True,
        )

        traceback.print_exc()

        flash(
            f"Error transmitiendo cupones e informes: {error}",
            "danger",
        )

    finally:
        cur.close()
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