"""Pruebas de rutas sin conexiones a servicios ni cambios en datos reales."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from flask import Flask
from jinja2 import ChoiceLoader, DictLoader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class ArchivadoFoldersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporal = tempfile.TemporaryDirectory()
        # logs inicializa tablas al importarse; estas pruebas nunca usan la BD real.
        with patch.dict(os.environ, {"RUTA_TEMP_FOLDER_TUCUMAN": cls.temporal.name}), \
                patch.dict(sys.modules, {"logs": MagicMock()}):
            cls.compras = importlib.import_module("compras")
        cls.app = Flask(__name__, template_folder="../templates")
        cls.app.config.update(SECRET_KEY="test", TESTING=True)
        cls.app.register_blueprint(cls.compras.compras_bp, url_prefix="/compras")
        cls.app.add_url_rule("/login", endpoint="sistemas.login", view_func=lambda: "Login")
        cls.app.jinja_loader = ChoiceLoader([
            DictLoader({"base.html": "{% block content %}{% endblock %}"}),
            cls.app.jinja_loader,
        ])

    @classmethod
    def tearDownClass(cls):
        cls.temporal.cleanup()

    def setUp(self):
        self.client = self.app.test_client()
        self.login("compras", "comprador")
        self.conn = MagicMock()
        self.cursor = self.conn.cursor.return_value.__enter__.return_value
        self.cursor.rowcount = 12
        self.cursor.fetchone.return_value = {"total": 1}
        self.db = patch.object(self.compras, "get_db_connection", return_value=self.conn)
        self.db_mock = self.db.start()
        self.addCleanup(self.db.stop)
        self.log = patch.object(self.compras, "guardar_log_compras")
        self.log_mock = self.log.start()
        self.addCleanup(self.log.stop)

    def login(self, rol, usuario):
        with self.client.session_transaction() as sesion:
            sesion.clear()
            sesion.update(usuario_id=1, usuario_rol=rol, usuario_nombre=usuario)

    def archivar(self, folder="mayorista", **fechas):
        return self.client.post(f"/compras/folder/{folder}/archivar", data={
            "fecha_desde": "2026-10-15", "fecha_hasta": "2026-10-25", **fechas,
        })

    def mensajes(self):
        with self.client.session_transaction() as sesion:
            return sesion.get("_flashes", [])

    def test_tres_folders_con_vigencia_exacta_y_destinos_separados(self):
        for folder, tipo, tucuman in [
            ("mayorista", "mayorista", False),
            ("mayorista/tucuman", "mayorista", True),
            ("minorista", "minorista", None),
        ]:
            with self.subTest(folder=folder):
                respuesta = self.archivar(folder)
                self.assertEqual(respuesta.status_code, 303)
                sql, params = self.cursor.execute.call_args.args
                self.assertIn("WITH registros_movidos", sql)
                self.assertIn("desde = %s AND hasta = %s", sql)
                self.assertEqual(params[:3], [tipo, "2026-10-15", "2026-10-25"])
                if tucuman is not None:
                    self.assertEqual(params[3], ["CO24", "CO25", "CO27"])
                    self.assertEqual("AND NOT " in sql, not tucuman)
                else:
                    self.assertEqual(len(params), 4)
                self.assertEqual(params[-1], "comprador")
                self.assertEqual(self.conn.__exit__.call_args.args, (None, None, None))
                self.assertEqual(self.mensajes()[-1][0], "archivo_success")
                self.conn.close.assert_called()

    def test_fechas_invalidas_no_abren_conexion(self):
        for fechas in [
            {"fecha_desde": ""}, {"fecha_hasta": "2026-02-30"},
            {"fecha_desde": "2026-10-26"},
        ]:
            with self.subTest(fechas=fechas):
                self.assertEqual(self.archivar(**fechas).status_code, 303)
                self.db_mock.assert_not_called()
                self.assertEqual(self.mensajes()[-1][0], "archivo_error")

    def test_sin_coincidencias_no_informa_exito(self):
        self.cursor.rowcount = 0
        self.archivar()
        self.assertEqual(self.mensajes()[-1][0], "archivo_error")
        self.log_mock.assert_not_called()

    def test_fallo_insert_sale_de_transaccion_con_error(self):
        self.cursor.execute.side_effect = RuntimeError("Fallo de INSERT")
        self.archivar()
        self.assertIs(self.conn.__exit__.call_args.args[0], RuntimeError)
        self.conn.close.assert_called_once()
        self.assertEqual(self.mensajes()[-1][0], "archivo_error")
        self.log_mock.assert_not_called()

    def test_fallo_log_auxiliar_no_reporta_reversion_del_archivado(self):
        self.log_mock.side_effect = RuntimeError("Log no disponible")
        self.archivar()
        self.assertEqual(self.mensajes()[-1][0], "archivo_success")

    def test_sucursal_no_puede_archivar(self):
        self.login("sucursal", "CO24")
        for folder in ("mayorista", "mayorista/tucuman", "minorista"):
            self.assertEqual(self.archivar(folder).status_code, 302)
        self.db_mock.assert_not_called()

    def test_formularios_y_confirmacion_en_las_tres_pantallas(self):
        for folder in ("mayorista", "mayorista/tucuman", "minorista"):
            with self.subTest(folder=folder):
                respuesta = self.client.get(f"/compras/folder/{folder}")
                self.assertEqual(respuesta.status_code, 200)
                html = respuesta.get_data(as_text=True)
                self.assertIn(f'action="/compras/folder/{folder}/archivar"', html)
                self.assertIn("confirmarArchivoFolder(this)", html)

    def test_redireccion_muestra_resultado_en_pantalla(self):
        respuesta = self.client.get(self.archivar().location)
        self.assertIn("12 cenefas", respuesta.get_data(as_text=True))

    def test_historico_filtra_sucursal_en_ambas_tablas_y_conserva_impresion(self):
        self.login("sucursal", " co24 ")
        fila = dict(
            id=11, origen="operativas", codigo="123", ean="779123", dep="1", departamento="Almacén",
            descripcion="Producto", normal=Decimal("1250.50"), oferta=Decimal("1100.25"),
            cenefa="OFERTA", desde=date(2026, 10, 15), hasta=date(2026, 10, 25),
            sucursales="CO24,CO25,CO27", tipo_cenefa="mayorista",
            fecha_carga=datetime(2026, 10, 10), lote_carga="lote-anterior",
            usuario_carga="comprador", fecha_archivado=datetime(2026, 10, 20),
            usuario_archivado="comprador",
        )
        self.cursor.fetchall.return_value = [fila]
        for estado in ("operativas", "archivadas"):
            with self.subTest(estado=estado):
                fila["origen"] = estado
                respuesta = self.client.get(
                    f"/compras/historico?estado={estado}&tipo=mayorista_tucuman&lote=anterior"
                )
                self.assertEqual(respuesta.status_code, 200)
                sql, params = self.cursor.execute.call_args.args
                self.assertIn("WHERE %s = ANY(", sql)
                self.assertEqual(params, ["CO24", "mayorista", ["CO24", "CO25", "CO27"], "%anterior%", 100, 0])
                self.assertIn("FROM public.cenefas_archivadas" if estado == "archivadas"
                              else "FROM public.cenefas", sql)
                html = respuesta.get_data(as_text=True)
                for texto in ("1.250,50", "1.100,25", "15/10/2026", "lote-anterior",
                              "imprimirSeleccionadas()", f'value="{estado}-11"'):
                    self.assertIn(texto, html)

    def test_estado_invalido_rechazado(self):
        self.login("sucursal", "CO24")
        self.assertEqual(self.client.get("/compras/historico?estado=otro").status_code, 400)
        self.db_mock.assert_not_called()

    def test_fechas_del_historico_admiten_texto_y_fecha(self):
        for valor in ("2026-10-15", "15/10/2026", date(2026, 10, 15)):
            self.assertEqual(self.compras._fecha_historico(valor), "15/10/2026")
        self.assertEqual(self.compras._fecha_historico(None), "")

    def test_historico_abre_vigentes_de_ambas_fuentes_con_limite(self):
        self.login("sucursal", "CO05")
        self.cursor.fetchall.return_value = []
        self.client.get("/compras/historico")
        sql, params = self.cursor.execute.call_args.args
        self.assertIn("UNION ALL", sql)
        self.assertIn("America/Argentina/Buenos_Aires", sql)
        self.assertIn("<=", sql)
        self.assertIn(">=", sql)
        self.assertIn("LIMIT %s OFFSET %s", sql)
        self.assertEqual(params, ["CO05", 100, 0])

    def test_paginacion_y_busqueda_preservan_filtros(self):
        self.login("sucursal", "CO05")
        self.cursor.fetchone.return_value = {"total": 250}
        self.cursor.fetchall.return_value = []
        respuesta = self.client.get("/compras/historico?pagina=2&codigo=azucar&vigencia=proximas&estado=archivadas")
        sql, params = self.cursor.execute.call_args.args
        self.assertIn("descripcion ILIKE %s", sql)
        self.assertEqual(params, ["CO05", "%azucar%", "%azucar%", "%azucar%", 100, 100])
        html = respuesta.get_data(as_text=True)
        for texto in ("Página 2 de 3", "pagina=3", "codigo=azucar", "vigencia=proximas", "estado=archivadas"):
            self.assertIn(texto, html)

    def test_pagina_fuera_de_rango_y_vigencia_invalida(self):
        self.login("sucursal", "CO05")
        self.cursor.fetchall.return_value = []
        for pagina in ("-2", "abc", "9999"):
            self.client.get("/compras/historico", query_string={"pagina": pagina})
            self.assertEqual(self.cursor.execute.call_args.args[1][-1], 0)
        self.assertEqual(self.client.get("/compras/historico?vigencia=otra").status_code, 400)


if __name__ == "__main__":
    unittest.main()
