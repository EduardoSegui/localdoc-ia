
import shutil

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from localdoc_ia.agent.llm import extract_invoice_data
from localdoc_ia.database.repository import (
    save_invoice_document,
)
from localdoc_ia.ingestion.extractor import (
    ExtractionResult,
    extract_document,
)
from localdoc_ia.schemas import InvoiceData


PROJECT_ROOT = Path(__file__).resolve().parents[3]

INBOX_DIR = PROJECT_ROOT / "data" / "inbox"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


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
) -> DocumentProcessingResult:
    """
    Procesa un archivo recibido mediante Telegram.

    Flujo:
    1. Extraer el texto.
    2. Obtener JSON estructurado con Ollama.
    3. Validar con Pydantic.
    4. Evaluar posibles problemas.
    5. Mover el archivo a processed/.
    6. Guardar la factura en PostgreSQL.

    Si falla la persistencia, intenta devolver el archivo a inbox/.
    """

    source = Path(source_path).resolve()

    if not source.exists() or not source.is_file():
        raise FileNotFoundError(
            f"No se encontró el archivo: {source}"
        )

    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Extraer texto utilizando PyMuPDF o Tesseract.
    extraction = extract_document(source)

    if not extraction.text.strip():
        raise ValueError(
            "No se pudo obtener texto del documento. "
            "Revisá la calidad de la imagen o el PDF."
        )

    # 2. Extraer datos mediante Ollama.
    # 3. Validar la respuesta mediante Pydantic.
    invoice = extract_invoice_data(extraction.text)

    # 4. Evaluar calidad sin bloquear el guardado.
    warnings = assess_invoice_quality(invoice)

    # 5. Mover el archivo antes de persistir para registrar
    #    directamente su ubicación definitiva.
    destination = PROCESSED_DIR / source.name

    if destination.exists():
        raise FileExistsError(
            f"Ya existe un archivo con ese nombre: {destination}"
        )

    source.replace(destination)

    try:
        # 6. Guardar factura y conceptos en una transacción.
        document_id = save_invoice_document(
            file_path=destination,
            extraction=extraction,
            invoice=invoice,
        )

    except Exception:
        # Si falla PostgreSQL, devolver el archivo a inbox/.
        if destination.exists() and not source.exists():
            destination.replace(source)

        raise

    return DocumentProcessingResult(
        document_id=document_id,
        file_path=str(destination),
        extraction=extraction,
        invoice=invoice,
        warnings=warnings,
    )
