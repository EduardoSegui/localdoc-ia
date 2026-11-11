
from pathlib import Path

import pytest
from mcp import Client

from localdoc_ia.mcp.server import mcp


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def mcp_client():
    async with Client(mcp, raise_exceptions=True) as client:
        yield client


@pytest.mark.anyio
async def test_mcp_tools(mcp_client):
    # 1. Comprobar que el servidor publica las tres herramientas.
    tools = await mcp_client.list_tools()

    tool_names = {tool.name for tool in tools.tools}

    assert "buscar_documentos" in tool_names
    assert "consultar_gastos" in tool_names
    assert "generar_reporte" in tool_names

    # 2. Probar búsqueda de documentos.
    search_result = await mcp_client.call_tool(
        "buscar_documentos",
        {
            "limite": 5,
            "desplazamiento": 0,
        },
    )

    assert not search_result.is_error
    assert search_result.structured_content is not None
    assert "documentos" in search_result.structured_content
    assert "total_encontrados" in search_result.structured_content

    # 3. Probar consulta de gastos.
    expenses_result = await mcp_client.call_tool(
        "consultar_gastos",
        {},
    )

    assert not expenses_result.is_error
    assert expenses_result.structured_content is not None
    assert "resumen_por_moneda" in expenses_result.structured_content
    assert "resumen_por_proveedor" in expenses_result.structured_content

    # 4. Probar generación de reporte.
    report_result = await mcp_client.call_tool(
        "generar_reporte",
        {},
    )

    assert not report_result.is_error
    assert report_result.structured_content is not None

    report_data = report_result.structured_content

    assert report_data["estado"] == "generado"
    assert report_data["registros_exportados"] >= 0

    report_path = Path(report_data["ruta"])

    assert report_path.exists()
    assert report_path.suffix == ".csv"
