import os
from flask import Blueprint, render_template, request, send_file
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle

from sistemas import login_requerido


operadores_bp = Blueprint(
    "operadores",
    __name__,
    url_prefix="/operadores"
)


def generar_pdf_operador(datos):
    os.makedirs("reports", exist_ok=True)

    filename = f"Informe_{datos['nro']}.pdf"
    path = os.path.join("reports", filename)

    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4

    amarillo = "#f2b400"
    margen = 12 * mm

    c.setStrokeColor(amarillo)
    c.setLineWidth(2)
    c.rect(margen, margen, width - 2 * margen, height - 2 * margen)

    logo_path = os.path.join("static", "logo.png")

    if os.path.exists(logo_path):
        c.drawImage(
            logo_path,
            margen + 4 * mm,
            height - margen - 18 * mm,
            width=35 * mm,
            height=15 * mm,
            preserveAspectRatio=True,
            mask="auto"
        )

    c.setStrokeColor(amarillo)
    c.setLineWidth(1.5)
    c.roundRect(margen + 42 * mm, height - margen - 20 * mm, 82 * mm, 18 * mm, 3)

    c.setFillColor("#000000")
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(margen + 83 * mm, height - margen - 8 * mm, "INFORME")
    c.drawCentredString(margen + 83 * mm, height - margen - 13 * mm, "CENTRAL DE MONITOREO")

    c.roundRect(margen + 128 * mm, height - margen - 20 * mm, 45 * mm, 18 * mm, 3)

    c.setFont("Helvetica-Bold", 7)
    c.drawString(margen + 132 * mm, height - margen - 6 * mm, f"Nº: {datos['nro']}")
    c.drawString(margen + 132 * mm, height - margen - 12 * mm, f"FECHA: {datos['fecha']}")
    c.drawString(margen + 132 * mm, height - margen - 18 * mm, f"HORA: {datos['hora']}")

    y_sucursal = height - margen - 28 * mm
    c.roundRect(margen + 3 * mm, y_sucursal, 121 * mm, 8 * mm, 2)

    c.setFont("Helvetica-Bold", 7)
    c.drawString(margen + 5 * mm, y_sucursal + 2.5 * mm, f"SUCURSAL: {datos['sucursal']}")

    c.setFillColor("#000000")
    c.setFont("Helvetica-Bold", 7)
    c.drawString(margen + 23 * mm, height - margen - 43 * mm, "Por la presente se informa que:")

    style = ParagraphStyle(
        "mensaje",
        fontName="Helvetica",
        fontSize=9,
        leading=13
    )

    texto = datos["mensaje"].replace("\n", "<br/>")
    p = Paragraph(texto, style)

    x_texto = margen + 20 * mm
    y_texto = margen + 30 * mm
    ancho_texto = width - 2 * margen - 40 * mm
    alto_texto = height - 2 * margen - 85 * mm

    p.wrapOn(c, ancho_texto, alto_texto)
    p.drawOn(c, x_texto, y_texto + alto_texto - p.height)

    y_pie = margen + 5 * mm
    c.setStrokeColor(amarillo)
    c.roundRect(margen + 3 * mm, y_pie, width - 2 * margen - 6 * mm, 8 * mm, 1)

    c.setFillColor("#000000")
    c.setFont("Helvetica-Bold", 7)
    c.drawString(margen + 5 * mm, y_pie + 2.5 * mm, f"Operador: {datos['operador']}")
    c.drawString(width / 2 + 5 * mm, y_pie + 2.5 * mm, f"Para: {datos['para']}")

    c.save()

    return path


@operadores_bp.route("/", methods=["GET"])
@login_requerido("cm")
def index():
    return render_template("operadores/formulario.html")


@operadores_bp.route("/generar", methods=["POST"])
@login_requerido("cm")
def generar():
    datos = {
        "sucursal": request.form["sucursal"],
        "operador": request.form["operador"],
        "para": request.form["para"],
        "nro": request.form["nro"],
        "fecha": request.form["fecha"],
        "hora": request.form["hora"],
        "mensaje": request.form["mensaje"]
    }

    ruta_pdf = generar_pdf_operador(datos)

    return send_file(ruta_pdf, as_attachment=True)