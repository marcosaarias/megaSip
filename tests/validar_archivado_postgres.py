"""Valida las rutas con PostgreSQL real y revierte todos los datos de prueba.

Usar DB_HOST, DB_PORT, DB_NAME, DB_USER y DB_PASSWORD del entorno.
Aplicar previamente database/migrations/20261020_cenefas_archivadas.sql.
"""
import importlib
import os
from pathlib import Path
import secrets
import sys
import tempfile
from unittest.mock import MagicMock, patch
import uuid

from flask import Flask
from jinja2 import ChoiceLoader, DictLoader
import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class ConexionPrueba:
    """Deja el commit en manos del validador; cada ruta usa un savepoint."""
    def __init__(self, conexion):
        self.conexion = conexion

    def cursor(self, *args, **kwargs):
        return self.conexion.cursor(*args, **kwargs)

    def __enter__(self):
        with self.cursor() as cursor:
            cursor.execute("SAVEPOINT validar_ruta")
        return self

    def __exit__(self, tipo, valor, traceback):
        with self.cursor() as cursor:
            if tipo is not None:
                cursor.execute("ROLLBACK TO SAVEPOINT validar_ruta")
            cursor.execute("RELEASE SAVEPOINT validar_ruta")
        return False

    def close(self):
        pass


def validar():
    conn = psycopg2.connect(
        host=os.environ["DB_HOST"], port=os.getenv("DB_PORT", "5432"),
        dbname=os.environ["DB_NAME"], user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"], connect_timeout=5,
    )
    lote = "validacion-" + uuid.uuid4().hex
    ids = [-secrets.randbelow(1_000_000_000) - 1 for _ in range(4)]
    try:
        with tempfile.TemporaryDirectory() as temporal:
            with patch.dict(os.environ, {"RUTA_TEMP_FOLDER_TUCUMAN": temporal}), \
                    patch.dict(sys.modules, {"logs": MagicMock()}):
                compras = importlib.import_module("compras")
            app = Flask(__name__, template_folder="../templates")
            app.config.update(SECRET_KEY=uuid.uuid4().hex, TESTING=True)
            app.register_blueprint(compras.compras_bp, url_prefix="/compras")
            app.jinja_loader = ChoiceLoader([
                DictLoader({"base.html": "{% block content %}{% endblock %}"}),
                app.jinja_loader,
            ])
            client = app.test_client()
            destinos = ["CO05,CO09", "co24, CO25, co27", "CO01,CO02", "CO05,CO09"]
            with conn.cursor() as cur:
                for indice, ident in enumerate(ids):
                    cur.execute("""
                        INSERT INTO public.cenefas (
                            id, codigo, ean, descripcion, normal, oferta, cenefa,
                            desde, hasta, sucursales, tipo_cenefa, fecha_carga,
                            lote_carga, usuario_carga
                        ) VALUES (%s, 123, '779123', 'Producto de validacion',
                                  1250.50, 1100.25, 'OFERTA', %s, %s, %s, %s,
                                  CURRENT_TIMESTAMP, %s, 'validacion')
                    """, (ident, "2099-02-01" if indice == 3 else "2099-01-01",
                          "2099-02-07" if indice == 3 else "2099-01-07",
                          destinos[indice], "minorista" if indice == 2 else "mayorista", lote))

            with patch.object(compras, "get_db_connection", return_value=ConexionPrueba(conn)), \
                    patch.object(compras, "guardar_log_compras"):
                with client.session_transaction() as sesion:
                    sesion.update(usuario_id=1, usuario_rol="compras", usuario_nombre="validacion")
                for indice, folder in enumerate(("mayorista", "mayorista/tucuman", "minorista")):
                    respuesta = client.post(f"/compras/folder/{folder}/archivar", data={
                        "fecha_desde": "2099-01-01", "fecha_hasta": "2099-01-07",
                    })
                    assert respuesta.status_code == 303
                    with conn.cursor() as cur:
                        cur.execute("SELECT id FROM public.cenefas_archivadas WHERE lote_carga=%s ORDER BY id", (lote,))
                        assert {fila[0] for fila in cur.fetchall()} == set(ids[:indice + 1])
                        cur.execute("SELECT count(*) FROM public.cenefas WHERE id=%s", (ids[3],))
                        assert cur.fetchone()[0] == 1, "El folder siguiente debe permanecer operativo"
                    print(f"OK: archivado {folder}, con separacion de destinos y vigencias")

                for sucursal, ident in zip(("CO05", "CO24", "CO01"), ids):
                    with client.session_transaction() as sesion:
                        sesion.update(usuario_rol="sucursal", usuario_nombre=sucursal)
                    respuesta = client.get("/compras/historico", query_string={"estado": "archivadas", "vigencia": "proximas", "lote": lote})
                    assert respuesta.status_code == 200
                    html = respuesta.get_data(as_text=True)
                    assert f'value="archivadas-{ident}"' in html
                    assert all(f'value="archivadas-{otro}"' not in html for otro in ids if otro != ident)
                    assert all(texto in html for texto in ("1.250,50", "1.100,25", "01/01/2099", "imprimirSeleccionadas()"))
                    print(f"OK: historico e impresion para {sucursal}, con precios y vigencia originales")

                with conn.cursor() as cur:
                    cur.execute("SELECT count(*) FROM public.cenefas_archivadas WHERE lote_carga=%s AND usuario_archivado='validacion' AND fecha_archivado IS NOT NULL", (lote,))
                    assert cur.fetchone()[0] == 3
                    # Provocar un conflicto real en el INSERT para verificar rollback.
                    cur.execute("INSERT INTO public.cenefas (id, tipo_cenefa, desde, hasta, sucursales, lote_carga) VALUES (%s, 'mayorista', '2099-01-01', '2099-01-07', 'CO05', %s)", (ids[0], lote))
                with client.session_transaction() as sesion:
                    sesion.update(usuario_rol="compras", usuario_nombre="validacion")
                with patch.object(app.logger, "exception"):
                    client.post("/compras/folder/mayorista/archivar", data={
                        "fecha_desde": "2099-01-01", "fecha_hasta": "2099-01-07",
                    })
                with conn.cursor() as cur:
                    cur.execute("SELECT count(*) FROM public.cenefas WHERE id=%s", (ids[0],))
                    assert cur.fetchone()[0] == 1, "Un fallo de INSERT debe restaurar el original"
                with client.session_transaction() as sesion:
                    assert sesion["_flashes"][-1][0] == "archivo_error"
                print("OK: auditoria y rollback ante un fallo real de insercion")

                # Un mismo ID puede existir en ambas tablas. La selección debe
                # distinguirlos y la consulta inicial debe excluir otras fechas.
                with conn.cursor() as cur:
                    cur.execute("SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'America/Argentina/Buenos_Aires')::date")
                    hoy = cur.fetchone()[0].isoformat()
                    cur.execute("UPDATE public.cenefas SET desde=%s, hasta=%s WHERE id=%s", (hoy, hoy, ids[0]))
                    cur.execute("UPDATE public.cenefas_archivadas SET desde=%s, hasta=%s WHERE id=%s", (hoy, hoy, ids[0]))
                with client.session_transaction() as sesion:
                    sesion.update(usuario_rol="sucursal", usuario_nombre="CO05")
                respuesta = client.get("/compras/historico", query_string={"lote": lote})
                html = respuesta.get_data(as_text=True)
                assert respuesta.status_code == 200
                assert f'value="operativas-{ids[0]}"' in html and f'value="archivadas-{ids[0]}"' in html
                assert f'value="operativas-{ids[3]}"' not in html
                assert "Mostrando 1–2 de 2" in html
                print("OK: inicio con vigentes de ambas tablas, inclusive hoy y sin confundir IDs iguales")

                # Comprobar paginación real con más registros que una página.
                lote_paginas = lote + "-paginas"
                with conn.cursor() as cur:
                    cur.execute("""INSERT INTO public.cenefas
                        (id, descripcion, desde, hasta, sucursales, tipo_cenefa, lote_carga)
                        SELECT %s - n, 'Producto paginado', %s, %s, 'CO05', 'mayorista', %s
                        FROM generate_series(1, 205) AS n""", (-1_500_000_000 - secrets.randbelow(100_000_000), hoy, hoy, lote_paginas))
                for pagina, cantidad in ((1, 100), (2, 100), (3, 5)):
                    respuesta = client.get("/compras/historico", query_string={"lote": lote_paginas, "pagina": pagina})
                    html = respuesta.get_data(as_text=True)
                    assert respuesta.status_code == 200
                    assert html.count('class="check-cenefa"') == cantidad
                    assert f"Página {pagina} de 3" in html
                print("OK: 205 registros distribuidos en paginas de 100, 100 y 5")
    finally:
        conn.rollback()
        with conn.cursor() as cur:
            for tabla in ("cenefas", "cenefas_archivadas"):
                cur.execute(f"SELECT count(*) FROM public.{tabla} WHERE lote_carga LIKE %s", (lote + "%",))
                assert cur.fetchone()[0] == 0, "Quedaron datos de prueba"
        conn.close()
        print("ROLLBACK verificado: no quedaron registros de prueba")


if __name__ == "__main__":
    validar()
