
import logging
from datetime import date
from typing import Any

from mcp.server import MCPServer

from localdoc_ia.database.queries import (
    buscar_documentos as query_buscar_documentos,
    consultar_gastos as query_consultar_gastos,
)
from localdoc_ia.reporting.reports import generar_reporte_facturas


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Servidor MCP oficial del proyecto
mcp = MCPServer(
    "LocalDoc AI",
    instructions=(
        "Servidor MCP para gestión documental y análisis de facturas. "
        "Expone tres herramientas: buscar_documentos, consultar_gastos "
        "y generar_reporte. "
        "Las herramientas consultan PostgreSQL y generan reportes CSV. "
        "No ejecuta SQL arbitrario ni realiza modificaciones "
        "sobre las facturas almacenadas."
    ),
)
@mcp.tool()
def buscar_documentos(
    termino: str | None = None,
    proveedor: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    limite: int = 20,
    desplazamiento: int = 0,
) -> dict[str, Any]:
    """
    Busca facturas y documentos almacenados en PostgreSQL.

    Puede buscar por nombre de archivo, proveedor, CUIT,
    cliente, número de comprobante y rango de fechas.

    Las fechas deben expresarse como YYYY-MM-DD.
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
    )


@mcp.tool()
def consultar_gastos(
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
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
    )


@mcp.tool()
def generar_reporte(
    termino: str | None = None,
    proveedor: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
) -> dict[str, Any]:
    """
    Genera un reporte CSV de las facturas almacenadas.

    Permite filtrar por texto, proveedor y fechas.
    Guarda el archivo en la carpeta reports/ del proyecto.

    El resultado informa la ruta del reporte generado.
    """

    logger.info("Herramienta MCP ejecutada: generar_reporte")

    return generar_reporte_facturas(
        termino=termino,
        proveedor=proveedor,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )


if __name__ == "__main__":
    # Transporte STDIO: recomendado para clientes MCP locales.
    mcp.run()
