
import hashlib
import mimetypes

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from localdoc_ia.database.connection import SessionLocal
from localdoc_ia.database.models import Document, DocumentItem
from localdoc_ia.ingestion.extractor import ExtractionResult
from localdoc_ia.schemas import InvoiceData


# Raíz del proyecto:
# repository.py -> database -> localdoc_ia -> src -> raíz
PROJECT_ROOT = Path(__file__).resolve().parents[3]

class DuplicateDocumentError(Exception):
    """Se produce cuando se intenta guardar un archivo ya registrado."""

    def __init__(self, document_id: int):
        self.document_id = document_id

        super().__init__(
            f"El documento ya está registrado. "
            f"ID existente: {document_id}"
        )

def calculate_file_sha256(file_path: Path) -> str:
    """
    Calcula el hash SHA-256 del archivo.

    Lee el archivo por bloques para no cargarlo completo en memoria.
    """

    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def get_stored_file_path(file_path: Path) -> str:
    """
    Devuelve una ruta relativa a la raíz del proyecto cuando es posible.
    Si el archivo está fuera del proyecto, conserva su ruta absoluta.
    """

    try:
        return str(file_path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(file_path)


def save_invoice_document(
    file_path: str | Path,
    extraction: ExtractionResult,
    invoice: InvoiceData,
) -> int:
    """
    Guarda una factura y todos sus conceptos en PostgreSQL.

    Args:
        file_path: Ruta del archivo original.
        extraction: Resultado de PyMuPDF/Tesseract.
        invoice: Información extraída y validada por Pydantic.

    Returns:
        ID del documento creado en PostgreSQL.

    Raises:
        FileNotFoundError: Si el archivo original no existe.
        DuplicateDocumentError: Si el archivo ya fue registrado.
        RuntimeError: Si ocurre un error de persistencia.
    """

    path = Path(file_path).resolve()

    if not path.exists() or not path.is_file():
        raise FileNotFoundError(
            f"No se encontró el documento: {path}"
        )

    # 1. Calcular el hash del archivo original
    file_hash = calculate_file_sha256(path)

    # 2. Obtener la ruta y el tipo MIME
    stored_path = get_stored_file_path(path)
    mime_type, _ = mimetypes.guess_type(path.name)

    # 3. Convertir el modelo Pydantic a un diccionario JSON compatible
    #    Las fechas y los Decimal se serializan de forma segura.
    extracted_data = invoice.model_dump(mode="json")

    try:
        # Una única transacción para factura + conceptos.
        with SessionLocal.begin() as session:

            # 4. Comprobar si el archivo ya existe
            existing_document_id = session.scalar(
                select(Document.id).where(
                    Document.file_sha256 == file_hash
                )
            )

            if existing_document_id is not None:
                raise DuplicateDocumentError(existing_document_id)

            # 5. Crear el registro principal
            document = Document(
                original_filename=path.name,
                file_path=stored_path,
                file_sha256=file_hash,
                mime_type=mime_type,

                document_type=invoice.document_type,
                point_of_sale=invoice.point_of_sale,
                document_number=invoice.document_number,
                issue_date=invoice.issue_date,
                due_date=invoice.due_date,
                currency=invoice.currency,

                supplier_name=invoice.supplier_name,
                supplier_tax_id=invoice.supplier_tax_id,
                supplier_address=invoice.supplier_address,

                customer_name=invoice.customer_name,
                customer_tax_id=invoice.customer_tax_id,
                customer_address=invoice.customer_address,

                subtotal=invoice.subtotal,
                tax_total=invoice.tax_total,
                other_taxes=invoice.other_taxes,
                discounts=invoice.discounts,
                total=invoice.total,

                extraction_method=extraction.method,
                extracted_text=extraction.text,
                extracted_data=extracted_data,

                processing_status="completed",
                processed_at=datetime.now(timezone.utc),
            )

            # 6. Crear los conceptos de la factura
            document.items = [
                DocumentItem(
                    line_number=item.line_number,
                    description=item.description,
                    product_code=item.product_code,
                    quantity=item.quantity,
                    unit=item.unit,
                    unit_price=item.unit_price,
                    tax_rate=item.tax_rate,
                    tax_amount=item.tax_amount,
                    line_total=item.line_total,
                )
                for item in invoice.items
            ]

            # 7. Agregar factura y conceptos a la sesión
            session.add(document)

            # Ejecutar INSERT para obtener el ID antes del commit
            session.flush()

            document_id = document.id

        # Al salir del contexto se confirma la transacción.
        return document_id

    except DuplicateDocumentError:
        raise

    except IntegrityError as error:
        raise RuntimeError(
            "No se pudo guardar la factura porque se violó "
            "una restricción de integridad de PostgreSQL."
        ) from error

    except SQLAlchemyError as error:
        raise RuntimeError(
            f"Error de base de datos al guardar '{path.name}'."
        ) from error
