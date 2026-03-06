from flask import Blueprint, render_template, request, redirect, url_for, flash
from database.db import get_db_connection

usuarios_bp = Blueprint("usuarios", __name__, url_prefix="/usuarios")


@usuarios_bp.route("/")
def index():
    conn = get_db_connection()
    usuarios = conn.execute("SELECT * FROM usuarios").fetchall()
    conn.close()
    return render_template("usuarios.html", usuarios=usuarios)


@usuarios_bp.route("/agregar", methods=["POST"])
def agregar_usuario():
    usuario = request.form.get("usuario")
    password = request.form.get("password")
    rol = request.form.get("rol")

    if not usuario or not password or not rol:
        flash("Todos los campos son obligatorios", "danger")
        return redirect(url_for("usuarios.index"))

    conn = get_db_connection()
    conn.execute(
        "INSERT INTO usuarios (usuario, password, rol) VALUES (?, ?, ?)",
        (usuario, password, rol)
    )
    conn.commit()
    conn.close()

    flash("Usuario agregado correctamente", "success")
    return redirect(url_for("usuarios.index"))


@usuarios_bp.route("/eliminar/<int:id>")
def eliminar_usuario(id):
    conn = get_db_connection()
    conn.execute("DELETE FROM usuarios WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    flash("Usuario eliminado correctamente", "warning")
    return redirect(url_for("usuarios.index"))


@usuarios_bp.route("/editar/<int:id>", methods=["POST"])
def editar_usuario(id):
    usuario = request.form.get("usuario")
    password = request.form.get("password")
    rol = request.form.get("rol")

    conn = get_db_connection()
    conn.execute(
        "UPDATE usuarios SET usuario=?, password=?, rol=? WHERE id=?",
        (usuario, password, rol, id)
    )
    conn.commit()
    conn.close()

    flash("Usuario actualizado correctamente", "info")
    return redirect(url_for("usuarios.index"))