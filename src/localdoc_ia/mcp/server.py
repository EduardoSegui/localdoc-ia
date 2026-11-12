
import logging
from datetime import date
from typing import Any

from mcp.server import MCPServer

from localdoc_ia.config import settings
from localdoc_ia.database.queries import (
    buscar_documentos as query_buscar_documentos,
    buscar_items_productos as query_buscar_items_productos,
    comparar_periodos as query_comparar_periodos,
    consultar_gastos as query_consultar_gastos,
    obtener_estadisticas_facturas as query_obtener_estadisticas,
)
from localdoc_ia.reporting.reports import generar_reporte_facturas


logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


# Servidor MCP oficial del proyecto
mcp = MCPServer(
    settings.app_name,
    instructions=(
        "Servidor MCP para gestión documental, análisis financiero y estadísticas de facturas. "
        "Expone herramientas para buscar documentos con ordenamiento y filtros de importe, "
        "obtener estadísticas clave (mayor/menor saldo, promedios, comparativas de extremos), "
        "comparar períodos de tiempo, buscar productos/ítems facturados y generar reportes CSV. "
        "No ejecuta SQL arbitrario ni realiza modificaciones sobre las facturas almacenadas."
    ),
)


@mcp.tool()
def buscar_documentos(
    termino: str | None = None,
    proveedor: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    document_id: int | None = None,
    moneda: str | None = None,
    monto_minimo: float | None = None,
    monto_maximo: float | None = None,
    ordenar_por: str | None = "fecha",
    orden: str | None = "desc",
    limite: int = 20,
    desplazamiento: int = 0,
) -> dict[str, Any]:
    """
    Busca facturas y documentos almacenados en PostgreSQL.

    Permite buscar por texto (nombre de archivo, proveedor, CUIT, cliente, ítems, observaciones),
    número de comprobante, rango de fechas, moneda y rango de importes (monto_minimo, monto_maximo).

    Permite ordenar por 'total' o 'monto' (para ver la factura más cara o más barata),
    'fecha', 'proveedor' o 'id', con orden 'desc' (descendente) o 'asc' (ascendente).

    El límite admite entre 1 y 100 resultados.
    """

    logger.info("Herramienta MCP ejecutada: buscar_documentos")

    return query_buscar_documentos(
        termino=termino,
        proveedor=proveedor,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        limite=limite,
        desplazamiento=desplazamiento,
        document_id=document_id,
        moneda=moneda,
        monto_minimo=monto_minimo,
        monto_maximo=monto_maximo,
        ordenar_por=ordenar_por,
        orden=orden,
    )


@mcp.tool()
def obtener_estadisticas(
    moneda: str | None = None,
    proveedor: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
) -> dict[str, Any]:
    """
    Calcula estadísticas analíticas de las facturas almacenadas:
    - Identifica la factura con mayor saldo / importe y la de menor saldo.
    - Comparativa de extremos (diferencia exacta en dinero y relación en veces).
    - Monto total acumulado, subtotales, impuestos y promedio por comprobante (ticket promedio).
    - Top 3 facturas con mayor importe.
    - Proveedor con mayor concentración de gasto.

    Usá esta herramienta para responder:
    - ¿Cuál es la factura con mayor saldo / importe hasta ahora?
    - Comparar la factura con mayor y menor monto.
    - ¿Cuál es el promedio de gasto por factura?
    - ¿Cuáles son las facturas más caras registradas?

    Si el usuario no especifica moneda, proveedor ni fechas, llamala sin
    argumentos: analiza la totalidad de las facturas. No agregues filtros
    inferidos, porque "hasta ahora" no significa un rango de fechas.
    """

    logger.info("Herramienta MCP ejecutada: obtener_estadisticas")

    return query_obtener_estadisticas(
        moneda=moneda,
        proveedor=proveedor,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )


@mcp.tool()
def comparar_periodos(
    fecha_desde_1: date,
    fecha_hasta_1: date,
    fecha_desde_2: date,
    fecha_hasta_2: date,
    proveedor: str | None = None,
    moneda: str | None = None,
) -> dict[str, Any]:
    """
    Compara el gasto y cantidad de comprobantes entre dos períodos de tiempo distintos.

    Calcula la variación porcentual, diferencia de dinero y conclusión sobre si hubo
    un incremento o reducción en el gasto.

    Las fechas deben expresarse como YYYY-MM-DD.
    """

    logger.info("Herramienta MCP ejecutada: comparar_periodos")

    return query_comparar_periodos(
        fecha_desde_1=fecha_desde_1,
        fecha_hasta_1=fecha_hasta_1,
        fecha_desde_2=fecha_desde_2,
        fecha_hasta_2=fecha_hasta_2,
        proveedor=proveedor,
        moneda=moneda,
    )


@mcp.tool()
def buscar_items_productos(
    termino: str | None = None,
    proveedor: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    ordenar_por: str | None = "precio",
    orden: str | None = "desc",
    limite: int = 20,
) -> dict[str, Any]:
    """
    Busca productos y servicios facturados en las líneas de detalle (items).

    Permite saber cuánto se pagó por un producto específico, precio unitario promedio,
    precio máximo, precio mínimo, y qué proveedor lo vendió en cada fecha.

    Usá esta herramienta para responder:
    - ¿Cuánto pagamos por electrodos, carnicería o teclados?
    - ¿Qué producto fue el más caro adquirido?
    - Listar compras de un producto en particular.
    """

    logger.info("Herramienta MCP ejecutada: buscar_items_productos")

    return query_buscar_items_productos(
        termino=termino,
        proveedor=proveedor,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        ordenar_por=ordenar_por,
        orden=orden,
        limite=limite,
    )


@mcp.tool()
def consultar_gastos(
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    document_id: int | None = None,
    proveedor: str | None = None,
) -> dict[str, Any]:
    """
    Consulta los gastos registrados en las facturas.

    Devuelve subtotales, impuestos y totales agrupados
    por moneda y proveedor.

    No mezcla importes de diferentes monedas.
    Solo considera documentos procesados correctamente.
    """

    logger.info("Herramienta MCP ejecutada: consultar_gastos")

    return query_consultar_gastos(
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        proveedor=proveedor,
        document_id=document_id,
    )


@mcp.tool()
def generar_reporte(
    termino: str | None = None,
    proveedor: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    document_id: int | None = None,
    moneda: str | None = None,
    monto_minimo: float | None = None,
    monto_maximo: float | None = None,
    ordenar_por: str | None = "fecha",
    orden: str | None = "desc",
) -> dict[str, Any]:
    """
    Genera un reporte CSV de las facturas almacenadas.

    Permite filtrar por texto, proveedor, fechas, moneda, monto mínimo/máximo
    y ordenar por fecha o total (ascendente o descendente).

    Guarda el archivo en la carpeta de reportes configurada
    (por defecto `reports/telegram/` del proyecto).
    El resultado informa la ruta del reporte generado.
    """

    logger.info("Herramienta MCP ejecutada: generar_reporte")

    return generar_reporte_facturas(
        termino=termino,
        proveedor=proveedor,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        document_id=document_id,
        moneda=moneda,
        monto_minimo=monto_minimo,
        monto_maximo=monto_maximo,
        ordenar_por=ordenar_por,
        orden=orden,
    )


if __name__ == "__main__":
    # Transporte STDIO: recomendado para clientes MCP locales.
    mcp.run()
