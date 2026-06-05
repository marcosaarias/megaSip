import re
import uuid
import traceback
import pandas as pd
from io import StringIO
import io

from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file

from compras import (
    redis_client,
    ALIAS,
    completar_ean,
    completar_departamento,
    completar_dep,
    normalizar_texto,
    guardar_cenefas_en_db,
    existen_cenefas_repetidas,
    limpiar_precio
)


diarios_bp = Blueprint("diarios", __name__, url_prefix="/compras/diario")


def formatear_moneda(valor):
    try:
        if valor == "" or pd.isna(valor):
            return ""

        valor_str = str(valor).replace(",", "").strip()

        num = float(valor_str)

        num_formateado = "{:,.2f}".format(num)
        return num_formateado.replace(",", "X").replace(".", ",").replace("X", ".")

    except (ValueError, TypeError):
        return valor

def detectar_sucursales(nombre_hoja):
    hoja = normalizar_texto(nombre_hoja)

    if "jujuy" in hoja and "salta" in hoja:
        return "CO01,CO02,CO04,CO05,CO06,CO07,CO08,CO09,CO10,CO11,CO12,CO14,CO15,CO16,CO17,CO18,CO19,CO20,CO21,CO22,CO23,CO28,CO29,MA02"

    if "jujuy" in hoja:
        if "mayorista" in hoja:
            return "CO05,CO12,CO15,MA02"
        return "CO01,CO02,CO04,CO05,CO06,CO07,CO08,CO10,CO11,CO12,CO14,CO15,CO16,CO17,CO19,CO20,CO22,CO28,MA02"

    if "salta" in hoja:
        if "mayorista" in hoja:
            return "CO09,CO29,CO21"
        return "CO18,CO23,CO09,CO29,CO21"

    if "tucuman" in hoja:
        return "CO24,CO25,CO26,CO27"

    return ""


def normalizar_sucursales(valor, nombre_hoja):
    if not valor or str(valor).strip() == "":
        return detectar_sucursales(nombre_hoja)

    valor_str = str(valor).strip()

    if re.search(r"\b(CO\d+|MA\d+)\b", valor_str):
        return valor_str

    texto = normalizar_texto(valor_str)

    es_mayorista = "mayorista" in texto
    es_minorista = "minorista" in texto

    regiones = []
    if "jujuy" in texto:
        regiones.append("jujuy")
    if "salta" in texto:
        regiones.append("salta")
    if "oran" in texto:
        regiones.append("oran")
    if "tucuman" in texto:
        regiones.append("tucuman")

    if set(regiones) == {"jujuy", "salta"} and not es_mayorista and not es_minorista:
        return "CO01,CO02,CO04,CO05,CO06,CO07,CO08,CO09,CO10,CO11,CO12,CO14,CO15,CO16,CO17,CO18,CO19,CO20,CO21,CO22,CO23,CO28,CO29,MA02"

    if set(regiones) == {"jujuy", "salta", "tucuman"}:
        return "CO01,CO02,CO04,CO05,CO06,CO07,CO08,CO09,CO10,CO11,CO12,CO14,CO15,CO16,CO17,CO18,CO19,CO20,CO21,CO22,CO23,CO24,CO25,CO26,CO27,CO28,CO29,MA02"

    resultado = []

    for region in regiones:
        if region == "tucuman":
            resultado.append("CO24,CO25,CO26,CO27")
            continue

        if region == "oran":
            resultado.append("CO21")
            continue

        if es_mayorista and not es_minorista:
            if region == "jujuy":
                resultado.append("CO05,CO12,CO15,MA02")
            elif region == "salta":
                resultado.append("CO09,CO29,CO21")

        elif es_minorista and not es_mayorista:
            if region == "jujuy":
                resultado.append("CO01,CO02,CO04,CO06,CO07,CO08,CO10,CO11,CO14,CO16,CO17,CO19,CO20,CO22,CO28")
            elif region == "salta":
                resultado.append("CO18,CO23")

        else:
            if region == "jujuy":
                resultado.append("CO01,CO02,CO04,CO05,CO06,CO07,CO08,CO10,CO11,CO12,CO14,CO15,CO16,CO17,CO19,CO20,CO22,CO28,MA02")
            elif region == "salta":
                resultado.append("CO18,CO23,CO09,CO29,CO21")

    if resultado:
        codigos = ",".join(resultado).split(",")
        codigos_unicos = sorted(set(c.strip() for c in codigos if c.strip()))
        return ",".join(codigos_unicos)

    return detectar_sucursales(nombre_hoja)


@diarios_bp.route("/", methods=["GET", "POST"])
def diario():
    preview = {}
    total_registros = {}
    hojas_orden = []
    cache_id = None
    mensaje_error = None

    HEADERS_DIARIO = [
        "CODIGO", "DESCRIPCION", "EAN",
        "departamento", "dep",
        "Normal", "Oferta",
        "desde", "hasta",
        "sucursales", "cenefa"
    ]

    if request.method == "POST":

        accion = request.form.get("accion")

        # ================= TRANSMITIR =================
        if accion == "transmitir":

            cache_id = request.form.get("cache_id")
            hoja = request.form.get("hoja")

            if not cache_id or not hoja:
                mensaje_error = "Cache u hoja inválida."
                return render_template(
                    "diario.html",
                    preview=preview,
                    total_registros=total_registros,
                    hojas_orden=hojas_orden,
                    cache_id=None,
                    mensaje_error=mensaje_error
                )

            data = redis_client.get(f"diario:{cache_id}:{hoja}")

            if not data:
                mensaje_error = "No hay datos para transmitir. Volvé a procesar el archivo."
                return render_template(
                    "diario.html",
                    preview=preview,
                    total_registros=total_registros,
                    hojas_orden=hojas_orden,
                    cache_id=None,
                    mensaje_error=mensaje_error
                )

            try:
                df = pd.read_json(StringIO(data), orient="records")
                
                df = completar_departamento(df)
                df = completar_dep(df)

                if "dep" not in df.columns:
                    df["dep"] = ""

                if "departamento" not in df.columns:
                    df["departamento"] = ""

                repetidos = existen_cenefas_repetidas(df, "diario")

                if repetidos:
                    mensaje_error = f"Ya existen {len(repetidos)} registros de Diario para este período."

                    preview = {
                        hoja: df.to_html(
                            classes="table table-sm table-striped",
                            index=False
                        )
                    }

                    return render_template(
                        "diario.html",
                        preview=preview,
                        total_registros={hoja: len(df)},
                        hojas_orden=[hoja],
                        cache_id=cache_id,
                        mensaje_error=mensaje_error
                    )

                guardar_cenefas_en_db(
                    df,
                    "diario",
                    usuario=session.get("usuario_nombre", "desconocido")
                )

                redis_client.delete(f"diario:{cache_id}:{hoja}")

                preview = {
                    hoja: "<div class='alert alert-success'>Diario transmitido correctamente a sucursales.</div>"
                }

                return render_template(
                    "diario.html",
                    preview=preview,
                    total_registros={},
                    hojas_orden=[hoja],
                    cache_id=None,
                    mensaje_error=None
                )

            except Exception as e:
                traceback.print_exc()
                mensaje_error = f"Error transmitiendo Diario: {repr(e)}"
                return render_template(
                    "diario.html",
                    preview=preview,
                    total_registros=total_registros,
                    hojas_orden=hojas_orden,
                    cache_id=cache_id,
                    mensaje_error=mensaje_error
                )

        # ================= PROCESAR ARCHIVO =================
        archivo = request.files.get("archivo")
        fecha_desde_raw = request.form.get("fecha_desde")
        fecha_hasta_raw = request.form.get("fecha_hasta")

        if archivo:
            try:
                cache_id = str(uuid.uuid4())

                f_desde = pd.to_datetime(fecha_desde_raw).strftime("%d/%m/%Y") if fecha_desde_raw else ""
                f_hasta = pd.to_datetime(fecha_hasta_raw).strftime("%d/%m/%Y") if fecha_hasta_raw else ""

                xls = pd.read_excel(archivo, sheet_name=None, header=None)

                for nombre_hoja, df in xls.items():

                    fila_header = None
                    for i, row in df.iterrows():
                        valores = [normalizar_texto(x) for x in row.values]
                        if "codigo" in valores:
                            fila_header = i
                            break

                    if fila_header is None:
                        continue

                    df = pd.read_excel(archivo, sheet_name=nombre_hoja, header=fila_header)

                    df_check = df.replace(r"^\s*$", pd.NA, regex=True)
                    if df_check.dropna(how="all").empty:
                        continue

                    df.columns = [normalizar_texto(col).strip() for col in df.columns]

                    column_mapping = {}

                    for header in HEADERS_DIARIO:
                        header_norm = normalizar_texto(header)
                        posibles = ALIAS.get(header, [])
                        posibles_norm = [normalizar_texto(p) for p in posibles]

                        for col in df.columns:
                            if col == header_norm or col in posibles_norm:
                                column_mapping[col] = header
                                break

                    df = df.rename(columns=column_mapping)

                    if "CODIGO" in df.columns:
                        df["CODIGO"] = (
                            df["CODIGO"]
                            .astype(str)
                            .str.strip()
                            .str.replace(".0", "", regex=False)
                            .str.lstrip("0")
                        )
                    
                    df = completar_ean(df)
                    df = completar_departamento(df)
                    df = completar_dep(df)

                    for col in ["departamento", "dep"]:
                        if col in df.columns:
                            df[col] = df[col].replace(["None", "none", "nan", "NaN", None], "")

                    df = completar_departamento(df)
                    df = completar_dep(df)

                    
                     
                    df["desde"] = f_desde
                    df["hasta"] = f_hasta

                    if "sucursales" not in df.columns:
                        df["sucursales"] = detectar_sucursales(nombre_hoja)
                    else:
                        df["sucursales"] = (
                            df["sucursales"]
                            .replace(r"^\s*$", pd.NA, regex=True)
                            .replace("nan", pd.NA)
                            .ffill()
                        )

                        df["sucursales"] = df["sucursales"].apply(
                            lambda x: normalizar_sucursales(x, nombre_hoja)
                        )

                    df = df.replace(r"^\s*$", pd.NA, regex=True).dropna(how="all")

                    if "cenefa" in df.columns:
                        df["cenefa"] = (
                            df["cenefa"]
                            .replace(r"^\s*$", pd.NA, regex=True)
                            .replace("nan", pd.NA)
                        )

                        df = df[
                            df["cenefa"].notna()
                            & (~df["cenefa"].astype(str).str.lower().str.contains("ya esta activo", na=False))
                        ]

                    if df.empty:
                        continue

                    columnas_validas = [col for col in HEADERS_DIARIO if col in df.columns]
                    df = df[columnas_validas]

                    if "CODIGO" in df.columns:
                        df["CODIGO"] = pd.to_numeric(df["CODIGO"], errors="coerce")
                        df = df.dropna(subset=["CODIGO"])
                        df["CODIGO"] = df["CODIGO"].astype(int)

                    df = df.fillna("")

                    redis_client.set(
                        f"diario:{cache_id}:{nombre_hoja}",
                        df.to_json(orient="records"),
                        ex=3600
                    )

                    preview[nombre_hoja] = df.to_html(
                        classes="table table-sm table-striped",
                        index=False
                    )

                    total_registros[nombre_hoja] = len(df)

                hojas_orden = list(preview.keys())

                if not preview:
                    mensaje_error = "No se encontraron hojas válidas para Diario."

            except Exception as e:
                mensaje_error = f"Error procesando diario: {repr(e)}"
                traceback.print_exc()

    return render_template(
        "diario.html",
        preview=preview,
        total_registros=total_registros,
        hojas_orden=hojas_orden,
        cache_id=cache_id,
        mensaje_error=mensaje_error
    )


@diarios_bp.route("/descargar/<hoja>")
def descargar_diario(hoja):
    cache_id = request.args.get("cache_id")

    if not cache_id:
        return "Cache inválido", 400

    data = redis_client.get(f"diario:{cache_id}:{hoja}")

    if not data:
        return "No hay datos", 404

    df = pd.read_json(StringIO(data), orient="records")

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Hoja1")

    output.seek(0)

    return send_file(
        output,
        download_name=f"{hoja}.xlsx",
        as_attachment=True
    )


@diarios_bp.route("/transmitir/<hoja>", methods=["POST"])
def transmitir_diario(hoja):
    from flask import session
    from compras import guardar_cenefas_en_db, existen_cenefas_repetidas

    cache_id = request.form.get("cache_id")

    if not cache_id:
        flash("Cache inválido", "danger")
        return redirect(url_for("diarios.diario"))

    data = redis_client.get(f"diario:{cache_id}:{hoja}")

    if not data:
        flash("No hay datos para transmitir", "danger")
        return redirect(url_for("diarios.diario"))

    df = pd.read_json(StringIO(data), orient="records")

    print("===== DEBUG DIARIO TRANSMITIR =====", flush=True)
    print("CACHE_ID:", cache_id, flush=True)
    print("HOJA:", hoja, flush=True)
    print("REGISTROS EN CACHE:", len(df), flush=True)
    print("COLUMNAS:", df.columns.tolist(), flush=True)
    print(df.head(5).to_string(), flush=True)

    def limpiar_precio(valor):
        if valor in ["", None]:
            return None

        valor = str(valor).strip()

        # Convierte formato argentino: 1.234,56 -> 1234.56
        valor = valor.replace(".", "").replace(",", ".")

        try:
            return float(valor)
        except:
            return None

    for col in ["Normal", "Oferta"]:
        if col in df.columns:
            df[col] = df[col].apply(limpiar_precio)

    usuario = session.get("usuario_nombre", "desconocido")
    tipo_cenefa = "diario"

    sobrescribir = request.form.get("sobrescribir") == "1"

    repetidos = existen_cenefas_repetidas(df, tipo_cenefa)

    if repetidos and not sobrescribir:
        preview = {
            hoja: df.to_html(
                classes="table table-sm table-striped",
                index=False
            )
        }

        return render_template(
            "diario.html",
            preview=preview,
            total_registros={hoja: len(df)},
            hojas_orden=[hoja],
            cache_id=cache_id,
            mensaje_error=(
                f"Ya existen {len(repetidos)} registros para este período. "
                "Si desea sobrescribirlos, confirme nuevamente."
            ),
            requiere_sobrescribir=True
        )

    guardar_cenefas_en_db(
        df,
        tipo_cenefa,
        usuario=usuario,
        sobrescribir=sobrescribir
    )

    from compras import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM cenefas
        WHERE tipo_cenefa = %s
    """, ("diario",))

    cantidad_diario = cursor.fetchone()[0]

    cursor.execute("""
        SELECT Codigo, descripcion, desde, hasta, sucursales, tipo_cenefa, fecha_carga
        FROM cenefas
        WHERE tipo_cenefa = %s
        ORDER BY fecha_carga DESC
        LIMIT 5
    """, ("diario",))

    ultimos = cursor.fetchall()

    conn.close()

    print("TOTAL EN DB tipo_cenefa=diario:", cantidad_diario, flush=True)
    print("ULTIMOS DIARIO EN DB:", ultimos, flush=True)

    print("DIARIO GUARDADO:", len(df), "registros", flush=True)

    redis_client.delete(f"diario:{cache_id}:{hoja}")

    flash(f"{hoja} transmitido correctamente", "success")
    return redirect(url_for("diarios.diario"))