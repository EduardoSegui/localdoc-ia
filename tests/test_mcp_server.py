
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
    # 1. Comprobar que el servidor publica todas las herramientas.
    tools = await mcp_client.list_tools()

    tool_names = {tool.name for tool in tools.tools}

    assert "buscar_documentos" in tool_names
    assert "consultar_gastos" in tool_names
    assert "obtener_estadisticas" in tool_names
    assert "comparar_periodos" in tool_names
    assert "buscar_items_productos" in tool_names
    assert "generar_reporte" in tool_names

    # 2. Probar búsqueda de documentos con ordenamiento por total.
    search_result = await mcp_client.call_tool(
        "buscar_documentos",
        {
            "limite": 5,
            "desplazamiento": 0,
            "ordenar_por": "total",
            "orden": "desc",
        },
    )

    assert not search_result.is_error
    assert search_result.structured_content is not None
    assert "documentos" in search_result.structured_content
    assert "total_encontrados" in search_result.structured_content
    docs = search_result.structured_content["documentos"]
    assert len(docs) > 0

    # 3. Probar estadísticas analíticas (factura mayor, menor, comparativa).
    stats_result = await mcp_client.call_tool(
        "obtener_estadisticas",
        {},
    )
    assert not stats_result.is_error
    assert stats_result.structured_content is not None
    stats_data = stats_result.structured_content
    assert "resumen_por_moneda" in stats_data
    assert stats_data["total_facturas_analizadas"] > 0
    # Comprobar que al menos una moneda tiene factura mayor
    resumen_list = stats_data["resumen_por_moneda"]
    has_mayor = any(r.get("factura_mayor") is not None for r in resumen_list)
    assert has_mayor

    # 4. Probar búsqueda de productos e ítems.
    items_result = await mcp_client.call_tool(
        "buscar_items_productos",
        {"termino": "Carnicería"},
    )
    assert not items_result.is_error
    assert items_result.structured_content is not None
    items_data = items_result.structured_content
    assert items_data["total_items_coincidentes"] >= 1
    assert "items" in items_data
    assert "precio_promedio" in items_data

    # 5. Probar comparación de períodos.
    comp_result = await mcp_client.call_tool(
        "comparar_periodos",
        {
            "fecha_desde_1": "2021-01-01",
            "fecha_hasta_1": "2021-12-31",
            "fecha_desde_2": "2026-01-01",
            "fecha_hasta_2": "2026-12-31",
        },
    )
    assert not comp_result.is_error
    assert comp_result.structured_content is not None
    comp_data = comp_result.structured_content
    assert "periodo_1" in comp_data
    assert "periodo_2" in comp_data
    assert "comparacion" in comp_data

    # 6. Probar consulta de gastos.
    expenses_result = await mcp_client.call_tool(
        "consultar_gastos",
        {},
    )

    assert not expenses_result.is_error
    assert expenses_result.structured_content is not None
    assert "resumen_por_moneda" in expenses_result.structured_content
    assert "resumen_por_proveedor" in expenses_result.structured_content

    # 7. Probar generación de reporte con ordenamiento por total.
    report_result = await mcp_client.call_tool(
        "generar_reporte",
        {
            "ordenar_por": "total",
            "orden": "desc",
        },
    )

    assert not report_result.is_error
    assert report_result.structured_content is not None

    report_data = report_result.structured_content

    assert report_data["estado"] == "generado"
    assert report_data["registros_exportados"] >= 0

    report_path = Path(report_data["ruta"])

    assert report_path.exists()
    assert report_path.suffix == ".csv"
