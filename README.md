# megaSip

## Archivado de folders

Antes de desplegar, ejecutar en PostgreSQL
`database/migrations/20261020_cenefas_archivadas.sql`. El script conserva los
registros existentes y crea la tabla de archivo y sus índices si faltan.

En Compras, abrir Folder Mayorista, Folder Mayorista Tucumán o Folder Minorista.
En «Archivar», ingresar las fechas Desde y Hasta originales del folder y confirmar.
Se archivan las cenefas de esa vigencia exacta, incluidos todos sus lotes; no se
interpreta como un rango de fechas de carga. Puede archivarse un folder que aún
está vigente antes de transmitir el siguiente.

Las sucursales acceden a Histórico de Cenefas → Archivadas para buscar por código,
tipo o lote, seleccionar e imprimir con los precios y fechas conservados. Cada
sucursal ve solamente los registros que la incluyen como destino. No se exige
que el folder haya vencido ni se eliminan sus cenefas al vencer.

El histórico abre con las cenefas vigentes de hoy, tanto actuales como archivadas,
y muestra hasta 100 por página. Las opciones «Próximas», «Vencidas» y «Todas las
fechas» permiten cambiar la vigencia; «Ubicación» permite filtrar las archivadas.
La búsqueda admite código, EAN o descripción. La selección para imprimir se
realiza por página. La vigencia considera el día local de Argentina, incluidos
ambos extremos del período.

Tucumán utiliza el tipo `mayorista`: se reconoce cuando todos los destinos del
registro pertenecen a CO24, CO25 y CO27. Los demás registros mayoristas pertenecen
al folder general. Se conservan el ID original, lote y usuario de carga, y se
agregan fecha y usuario de archivado. El movimiento es atómico; si falla la
inserción en el archivo, las cenefas permanecen operativas.

Pruebas sin servicios externos: `python -m unittest discover -s tests -v`.

Validación con PostgreSQL real, usando las variables de conexión del contenedor:
`docker compose exec -T flaskapp python tests/validar_archivado_postgres.py`.
La validación crea registros temporales, comprueba las rutas de archivado e
histórico y un fallo real de inserción, y revierte todos sus datos al terminar.
No aplica la migración automáticamente.
