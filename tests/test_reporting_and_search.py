import csv
from pathlib import Path

import pytest

from localdoc_ia.database.queries import buscar_documentos
from localdoc_ia.reporting.reports import CSV_FIELDS, generar_reporte_facturas


def test_csv_fields_include_observations_and_items_detail():
    assert "observations" in CSV_FIELDS
    assert "items_detail" in CSV_FIELDS


def test_buscar_documentos_serializes_observations_and_items():
    result = buscar_documentos(document_id=7)
    assert result["total_encontrados"] >= 1
    doc = result["documentos"][0]

    assert "observations" in doc
    assert "observations_list" in doc
    assert "items" in doc
    assert "items_detail" in doc
    assert "items_count" in doc

    assert isinstance(doc["observations_list"], list)
    assert len(doc["observations_list"]) > 0
    assert "0800-345-1411" in doc["observations"]
    assert "Mora Dolan Luisa Fabiana" in doc["items_detail"]
    assert len(doc["items"]) == 1
    assert doc["items"][0]["description"] == "Mora Dolan Luisa Fabiana"


def test_buscar_documentos_searches_by_item_and_observation():
    by_item = buscar_documentos(termino="Mora Dolan")
    assert any(d["id"] == 7 for d in by_item["documentos"])

    by_obs = buscar_documentos(termino="Novara")
    assert any(d["id"] == 7 for d in by_obs["documentos"])


def test_generar_reporte_contains_observations_and_items():
    report = generar_reporte_facturas(document_id=7)
    assert report["estado"] == "generado"

    report_path = Path(report["ruta"])
    assert report_path.is_file()

    with report_path.open(encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file, delimiter=";")
        rows = list(reader)

    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == "7"
    assert "0800-345-1411" in row["observations"]
    assert "Mora Dolan Luisa Fabiana" in row["items_detail"]


def test_buscar_documentos_ordenar_por_total():
    # Ordenar por total descendente debe traer la factura con mayor importe primero
    res_desc = buscar_documentos(ordenar_por="total", orden="desc", limite=5)
    assert res_desc["total_encontrados"] > 0
    primer_doc = res_desc["documentos"][0]
    # La factura con mayor saldo es la ID 4 (80086.00)
    assert primer_doc["id"] == 4
    assert primer_doc["total"] == "80086.00"

    # Filtro por monto mínimo
    res_min = buscar_documentos(monto_minimo=50000)
    totales = [float(d["total"]) for d in res_min["documentos"]]
    assert all(t >= 50000 for t in totales)


def test_obtener_estadisticas_factura_mayor_menor():
    from localdoc_ia.database.queries import obtener_estadisticas_facturas

    stats = obtener_estadisticas_facturas()
    assert stats["total_facturas_analizadas"] > 0
    resumen = stats["resumen_por_moneda"]
    assert len(resumen) > 0

    # Verificar que contenga comparativa de extremos
    comparativas = [r["comparativa_extremos"] for r in resumen if r.get("comparativa_extremos")]
    assert len(comparativas) > 0
    for comp in comparativas:
        assert "diferencia" in comp
        assert "resumen" in comp


def test_buscar_items_productos():
    from localdoc_ia.database.queries import buscar_items_productos

    res = buscar_items_productos(termino="Carnicería")
    assert res["total_items_coincidentes"] >= 2
    assert float(res["precio_promedio"]) > 0
    items = res["items"]
    assert any("Carnicería" in it["descripcion"] for it in items)

