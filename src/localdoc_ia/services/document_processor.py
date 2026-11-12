
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from localdoc_ia.agent.llm import (
    extract_invoice_data,
    extract_invoice_from_vision,
)
from localdoc_ia.database.repository import (
    calculate_file_sha256,
    complete_document_processing,
    mark_document_failed,
    start_document_processing,
)
from localdoc_ia.ingestion.extractor import (
    ExtractionResult,
    extract_document,
    render_pdf_pages,
)
from localdoc_ia.schemas import InvoiceData


@dataclass
class DocumentProcessingResult:
    """Resultado completo del procesamiento documental."""

    document_id: int
    file_path: str
    extraction: ExtractionResult
    invoice: InvoiceData
    warnings: list[str]


def assess_invoice_quality(invoice: InvoiceData) -> list[str]:
    """
    Detecta posibles problemas de calidad en los datos extraídos.

    Las advertencias no impiden guardar el documento.
    """

    warnings = []

    if not invoice.supplier_name:
        warnings.append(
            "No se pudo identificar el proveedor."
        )

    if not invoice.issue_date:
        warnings.append(
            "No se pudo identificar la fecha de emisión."
        )

    if invoice.total is None:
        warnings.append(
            "No se pudo identificar el importe total."
        )

    if (
        invoice.subtotal == Decimal("0")
        and invoice.total is not None
        and invoice.total > 0
    ):
        warnings.append(
            "El subtotal es cero y el total es positivo. "
            "Se recomienda revisar la extracción."
        )

    if not invoice.items:
        warnings.append(
            "No se identificaron productos o servicios."
        )

    return warnings


def process_uploaded_document(
    source_path: str | Path,
    original_filename: str | None = None,
) -> DocumentProcessingResult:
    """
    Procesa un archivo recibido mediante Telegram.

    Flujo:
    1. Registra el archivo recibido como pendiente en PostgreSQL.
    2. Usa texto nativo para PDF digitales o VLM para imágenes/PDF escaneados.
    3. Valida la respuesta con Pydantic y guarda factura + ítems en una
       transacción.
    4. Ante un error, conserva el original en inbox y registra estado failed.
    """

    source = Path(source_path).resolve()

    if not source.exists() or not source.is_file():
        raise FileNotFoundError(
            f"No se encontró el archivo: {source}"
        )

    # El hash y el INSERT de estado pending ocurren antes del trabajo pesado.
    # La restricción UNIQUE de PostgreSQL también protege ante cargas iguales
    # que lleguen casi al mismo tiempo.
    file_hash = calculate_file_sha256(source)
    document_id = start_document_processing(
        file_path=source,
        file_sha256=file_hash,
        original_filename=original_filename,
    )

    try:
        extraction = extract_document(source)

        if extraction.method == "vision":
            if extraction.file_type == "pdf":
                # Un PDF escaneado o mixto se analiza completo como imágenes.
                # Los PNG son temporales; el original permanece en inbox.
                with TemporaryDirectory(prefix="localdoc_vision_") as temp_dir:
                    page_images = render_pdf_pages(source, temp_dir)
                    invoice = extract_invoice_from_vision(page_images)
            else:
                invoice = extract_invoice_from_vision(source)
        else:
            if not extraction.text.strip():
                raise ValueError(
                    "No se pudo obtener texto útil del PDF digital."
                )

            invoice = extract_invoice_data(extraction.text)

        warnings = assess_invoice_quality(invoice)

        # Factura e ítems se confirman juntos, desde el mismo registro pending.
        complete_document_processing(
            document_id=document_id,
            extraction=extraction,
            invoice=invoice,
        )

    except Exception as error:
        try:
            mark_document_failed(document_id, str(error))
        except Exception:
            # No ocultar el error original si el registro de fallo también falla.
            pass
        raise

    return DocumentProcessingResult(
        document_id=document_id,
        file_path=str(source),
        extraction=extraction,
        invoice=invoice,
        warnings=warnings,
    )
