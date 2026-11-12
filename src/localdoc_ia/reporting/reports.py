
import csv

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from localdoc_ia.config import PROJECT_ROOT, settings
from localdoc_ia.database.queries import (
    obtener_documentos_para_reporte,
)


REPORTS_DIR = settings.reports_path
TELEGRAM_REPORTS_DIR = REPORTS_DIR / "telegram"


def _path_for_response(path: Path) -> str:
    """Devuelve una ruta relativa si está dentro del proyecto."""

    resolved = path.resolve()

    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(resolved)

CSV_FIELDS = [
    "id",
    "original_filename",
    "document_type",
    "point_of_sale",
    "document_number",
    "issue_date",
    "due_date",
    "supplier_name",
    "supplier_tax_id",
    "customer_name",
    "customer_tax_id",
    "currency",
    "subtotal",
    "tax_total",
    "other_taxes",
    "discounts",
    "total",
    "processing_status",
    "extraction_method",
    "observations",
    "items_detail",
    "created_at",
]


def generar_reporte_facturas(
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
    Genera un CSV con las facturas que coinciden con los filtros y ordenamiento.

    El archivo se guarda en la carpeta reports/telegram/ para poder
    adjuntarlo luego a la conversación de Telegram sin eliminarlo.
    """

    records, truncated = obtener_documentos_para_reporte(
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

    TELEGRAM_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    generated_at = datetime.now(timezone.utc)

    timestamp = generated_at.strftime("%Y%m%d_%H%M%S_%f")
    filename = f"reporte_facturas_{timestamp}.csv"
    output_path = TELEGRAM_REPORTS_DIR / filename

    try:
        with output_path.open(
            mode="w",
            encoding="utf-8-sig",
            newline="",
        ) as csv_file:

            writer = csv.DictWriter(
                csv_file,
                fieldnames=CSV_FIELDS,
                delimiter=";",
                extrasaction="ignore",
            )

            writer.writeheader()
            writer.writerows(records)

    except OSError as error:
        raise RuntimeError(
            f"No se pudo escribir el reporte CSV: {error}"
        ) from error

    return {
        "estado": "generado",
        "nombre_archivo": filename,
        "ruta": _path_for_response(output_path),
        "registros_exportados": len(records),
        "resultados_truncados": truncated,
        "fecha_generacion": generated_at.isoformat(),
        "filtros": {
            "termino": termino,
            "proveedor": proveedor,
            "fecha_desde": (
                fecha_desde.isoformat() if fecha_desde else None
            ),
            "fecha_hasta": (
                fecha_hasta.isoformat() if fecha_hasta else None
            ),
        },
        "formato": "CSV UTF-8 con BOM y separador punto y coma",
    }
