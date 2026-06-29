from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from functools import wraps
import pandas as pd
from database.db import get_db_connection

sistemas_bp = Blueprint("sistemas", __name__)


def login_requerido(rol=None):
    def decorador(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "usuario_id" not in session:
                flash("Debe iniciar sesión para acceder.", "warning")
                return redirect(url_for("sistemas.login"))

            if rol and str(session.get("usuario_rol", "")).strip().lower() != str(rol).strip().lower():
                flash("No tiene permiso para acceder a esta página.", "danger")
                return redirect(url_for("sistemas.login"))

            return f(*args, **kwargs)
        return wrapper
    return decorador


def limpiar_numero(x):
    if x is None:
        return ""

    s = str(x).strip()

    if s == "":
        return ""

    s = s.replace(".", "").replace(",", ".")

    try:
        return float(s)
    except Exception:
        return ""


@sistemas_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        nombre = request.form.get("usuario", "").strip()
        password = request.form.get("password", "")

        print("DEBUG => Usuario recibido:", nombre)
        print("DEBUG => Password recibido:", password)

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, rol
            FROM usuarios
            WHERE usuario = %s
              AND password = %s
            """,
            (nombre, password)
        )

        user = cur.fetchone()

        print("DEBUG => Resultado de la consulta:", user)

        cur.close()
        conn.close()

        if user:
            user_id = user["id"]
            user_rol = user["rol"]

            rol_lower = str(user_rol).strip().lower()

            session["usuario_id"] = user_id
            session["usuario_nombre"] = nombre
            session["usuario_rol"] = rol_lower

            flash("Inicio de sesión exitoso.", "success")

            print("DEBUG => Rol del usuario:", user_rol)

            if rol_lower == "sistemas":
                return redirect(url_for("sistemas.sistemas_dashboard"))

            elif rol_lower == "gerencia":
                return redirect(url_for("compras.lista_pedidos"))

            elif rol_lower == "gerencia-cm":
                return redirect(url_for("operadores.monitoreo"))

            elif rol_lower == "sucursal":
                return redirect(url_for("compras.sucursal", tipo="minorista"))

            elif rol_lower == "compras":
                return redirect(url_for("compras.folder_mayorista"))

            elif rol_lower == "farmacia":
                return redirect(url_for("farmacia.cenefas_farmacia"))

            elif rol_lower == "adm-farmacia":
                return redirect(url_for("farmacia.index"))

            elif rol_lower == "cm":
                return redirect(url_for("operadores.index"))
                
            elif rol_lower == "publicidad":
                return redirect(url_for("cupones.index"))

            else:
                flash("Rol no reconocido", "danger")
                return redirect(url_for("sistemas.login"))

        else:
            flash("Usuario o contraseña incorrectos.", "danger")
            print("DEBUG => No se encontró usuario con esas credenciales.")

    return render_template("login.html")


@sistemas_bp.route("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for("sistemas.login"))


@sistemas_bp.route("/")
@login_requerido()
def index():
    return render_template(
        "index.html",
        preview=None,
        table_data=None,
        sucursal=session.get("usuario_nombre")
    )


@sistemas_bp.route("/dashboard")
@login_requerido("sistemas")
def sistemas_dashboard():
    return render_template("sistemas.html")


@sistemas_bp.route("/logs")
@login_requerido("sistemas")
def sistemas_logs():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, sucursal, fecha, estado, usuario_accion
        FROM pedidos
        ORDER BY fecha DESC
        """
    )

    pedidos = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("sistemas_logs.html", pedidos=pedidos)


@sistemas_bp.route("/preview", methods=["POST"])
@login_requerido("sucursal")
def preview():
    try:
        file = request.files["file"]
        sucursal = session.get("usuario_nombre")

        df = pd.read_excel(file)
        df.columns = df.columns.str.strip().str.lower()

        columnas_salida = ["codigo", "descripcion", "precio", "cantidad"]
        aliases_descripcion = ["descripción", "descripcion", "descripcion material"]
        aliases_precio = ["puntual", "precio", "costo", "valor"]
        aliases_codigo = ["codigo", "material"]

        codigo_col = next(
            (col for col in df.columns if any(alias in col for alias in aliases_codigo)),
            None
        )

        if codigo_col:
            df["codigo"] = df[codigo_col]

        if "codigo" not in df.columns:
            df = pd.DataFrame(columns=columnas_salida)
        else:
            df = df[
                df["codigo"].notna()
                & (df["codigo"].astype(str).str.strip() != "")
            ]

        descripcion_col = next(
            (col for col in df.columns if any(alias in col for alias in aliases_descripcion)),
            None
        )

        if descripcion_col:
            df["descripcion"] = df[descripcion_col]

        precio_col = next(
            (col for col in df.columns if any(alias in col for alias in aliases_precio)),
            None
        )

        if precio_col:
            df["precio"] = df[precio_col]

        for col in columnas_salida:
            if col not in df.columns:
                df[col] = ""

        df["cantidad"] = df["cantidad"].astype(str)
        df.loc[df["cantidad"].str.strip() == "", "cantidad"] = 1000

        df_filtrado = df[columnas_salida].copy()

        def _fmt(x):
            val = limpiar_numero(x)

            if val == "":
                return ""

            return f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        df_filtrado["precio"] = df_filtrado["precio"].apply(_fmt)

        preview_html = df_filtrado.to_html(
            classes="table table-striped table-bordered",
            index=False
        )

        table_data = df_filtrado.to_json(
            orient="records",
            force_ascii=False
        )

        return render_template(
            "index.html",
            preview=preview_html,
            table_data=table_data,
            sucursal=sucursal
        )

    except Exception as e:
        return f"Error al procesar archivo: {e}"