
import hashlib
import mimetypes

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from localdoc_ia.config import PROJECT_ROOT
from localdoc_ia.database.connection import SessionLocal
from localdoc_ia.database.models import Document, DocumentItem
from localdoc_ia.ingestion.extractor import ExtractionResult
from localdoc_ia.schemas import InvoiceData


class DuplicateDocumentError(Exception):
    """Se produce cuando se intenta guardar un archivo ya registrado."""

    def __init__(self, document_id: int):
        self.document_id = document_id

        super().__init__(
            f"El documento ya está registrado. "
            f"ID existente: {document_id}"
        )


class DocumentProcessingInProgressError(Exception):
    """Se produce cuando otro proceso ya está procesando el mismo archivo."""

    def __init__(self, document_id: int):
        self.document_id = document_id

        super().__init__(
            "El documento ya está siendo procesado. "
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


def _get_existing_document(file_hash: str) -> tuple[int, str] | None:
    """Obtiene el ID y estado del documento asociado a un hash, si existe."""

    with SessionLocal() as session:
        return session.execute(
            select(Document.id, Document.processing_status).where(
                Document.file_sha256 == file_hash
            )
        ).one_or_none()


def _original_filename(
    file_path: Path,
    supplied_filename: str | None,
) -> str:
    """Normaliza el nombre mostrado sin alterar el archivo almacenado."""

    filename = (supplied_filename or file_path.name).strip()
    filename = Path(filename).name or file_path.name

    return filename[:255]


def start_document_processing(
    file_path: str | Path,
    file_sha256: str | None = None,
    original_filename: str | None = None,
) -> int:
    """
    Crea o reutiliza un registro pendiente antes de llamar al modelo.

    La consulta previa evita trabajo redundante y la restricción UNIQUE sobre
    `file_sha256` resuelve de forma segura cualquier carrera entre cargas
    simultáneas.
    """

    path = Path(file_path).resolve()

    if not path.is_file():
        raise FileNotFoundError(f"No se encontró el documento: {path}")

    document_hash = file_sha256 or calculate_file_sha256(path)
    stored_path = get_stored_file_path(path)
    mime_type, _ = mimetypes.guess_type(path.name)

    try:
        with SessionLocal.begin() as session:
            document = session.scalar(
                select(Document)
                .where(Document.file_sha256 == document_hash)
                .with_for_update()
            )

            if document is not None:
                if document.processing_status == "completed":
                    raise DuplicateDocumentError(document.id)

                if document.processing_status in {
                    "pending",
                    "extracted",
                    "validated",
                }:
                    raise DocumentProcessingInProgressError(document.id)

                # Un documento previo fallido puede volver a intentarse sin
                # romper la unicidad del hash.
                document.original_filename = _original_filename(
                    path,
                    original_filename,
                )
                document.file_path = stored_path
                document.mime_type = mime_type
                document.processing_status = "pending"
                document.processing_error = None
                document.processed_at = None
                session.flush()
                return document.id

            document = Document(
                original_filename=_original_filename(path, original_filename),
                file_path=stored_path,
                file_sha256=document_hash,
                mime_type=mime_type,
                processing_status="pending",
            )
            session.add(document)
            session.flush()

            return document.id

    except (DuplicateDocumentError, DocumentProcessingInProgressError):
        raise

    except IntegrityError as error:
        # Otra carga pudo insertar el mismo hash entre la consulta y el INSERT.
        existing_document = _get_existing_document(document_hash)

        if existing_document is not None:
            existing_document_id, existing_status = existing_document

            if existing_status == "completed":
                raise DuplicateDocumentError(existing_document_id) from error

            raise DocumentProcessingInProgressError(
                existing_document_id
            ) from error

        raise RuntimeError(
            "No se pudo registrar el documento pendiente en PostgreSQL."
        ) from error

    except SQLAlchemyError as error:
        raise RuntimeError(
            f"Error de base de datos al iniciar '{path.name}'."
        ) from error


def complete_document_processing(
    document_id: int,
    extraction: ExtractionResult,
    invoice: InvoiceData,
) -> None:
    """Guarda los datos extraídos y los ítems en una única transacción."""

    extracted_data = invoice.model_dump(mode="json")

    try:
        with SessionLocal.begin() as session:
            document = session.get(Document, document_id, with_for_update=True)

            if document is None:
                raise ValueError(
                    f"No existe el documento pendiente con ID {document_id}."
                )

            document.document_type = invoice.document_type
            document.point_of_sale = invoice.point_of_sale
            document.document_number = invoice.document_number
            document.issue_date = invoice.issue_date
            document.due_date = invoice.due_date
            document.currency = invoice.currency

            document.supplier_name = invoice.supplier_name
            document.supplier_tax_id = invoice.supplier_tax_id
            document.supplier_address = invoice.supplier_address

            document.customer_name = invoice.customer_name
            document.customer_tax_id = invoice.customer_tax_id
            document.customer_address = invoice.customer_address

            document.subtotal = invoice.subtotal
            document.tax_total = invoice.tax_total
            document.other_taxes = invoice.other_taxes
            document.discounts = invoice.discounts
            document.total = invoice.total

            document.extraction_method = extraction.method
            document.extracted_text = extraction.text
            document.extracted_data = extracted_data
            document.observations = invoice.observations
            document.processing_status = "completed"
            document.processing_error = None
            document.processed_at = datetime.now(timezone.utc)

            # En un reintento, sustituir cualquier ítem parcial anterior.
            session.execute(
                delete(DocumentItem).where(
                    DocumentItem.document_id == document_id
                )
            )

            session.add_all(
                [
                    DocumentItem(
                        document_id=document_id,
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
            )

    except SQLAlchemyError as error:
        raise RuntimeError(
            f"No se pudo completar el documento con ID {document_id}."
        ) from error


def mark_document_failed(document_id: int, error: str) -> None:
    """Conserva la traza funcional de un procesamiento fallido."""

    try:
        with SessionLocal.begin() as session:
            document = session.get(Document, document_id, with_for_update=True)

            if document is None:
                return

            document.processing_status = "failed"
            document.processing_error = error[:4000]
            document.processed_at = None

    except SQLAlchemyError as database_error:
        raise RuntimeError(
            f"No se pudo registrar el fallo del documento {document_id}."
        ) from database_error


def save_invoice_document(
    file_path: str | Path,
    extraction: ExtractionResult,
    invoice: InvoiceData,
) -> int:
    """
    Guarda una factura y todos sus conceptos en PostgreSQL.

    Args:
        file_path: Ruta del archivo original.
        extraction: Resultado de texto nativo o extracción visual.
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
        # La comprobación previa no elimina una carrera entre dos cargas
        # simultáneas; consultar nuevamente permite devolver un resultado
        # específico en vez de exponer el error de unicidad de PostgreSQL.
        existing_document = _get_existing_document(file_hash)

        if existing_document is not None:
            existing_document_id, _ = existing_document
            raise DuplicateDocumentError(existing_document_id) from error

        raise RuntimeError(
            "No se pudo guardar la factura porque se violó "
            "una restricción de integridad de PostgreSQL."
        ) from error

    except SQLAlchemyError as error:
        raise RuntimeError(
            f"Error de base de datos al guardar '{path.name}'."
        ) from error
