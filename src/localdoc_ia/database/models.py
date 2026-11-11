
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from localdoc_ia.database.connection import Base


class Document(Base):
    """Representa una factura o documento procesado."""

    __tablename__ = "documents"

    __table_args__ = (
        CheckConstraint(
            "processing_status IN "
            "('pending', 'extracted', 'validated', 'completed', 'failed')",
            name="ck_documents_processing_status",
        ),
        CheckConstraint(
            "extraction_method IN ('text', 'ocr', 'mixed')",
            name="ck_documents_extraction_method",
        ),
        Index("ix_documents_issue_date", "issue_date"),
        Index("ix_documents_supplier_tax_id", "supplier_tax_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    # Información del archivo original
    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    file_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    file_sha256: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
    )

    mime_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    # Información del comprobante
    document_type: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    point_of_sale: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )

    document_number: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    issue_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    due_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    currency: Mapped[str | None] = mapped_column(
        String(3),
        nullable=True,
    )

    # Información del proveedor
    supplier_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    supplier_tax_id: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    supplier_address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Información del cliente
    customer_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    customer_tax_id: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    customer_address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Información económica
    subtotal: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
    )

    tax_total: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
    )

    other_taxes: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
    )

    discounts: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
    )

    total: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
    )

    # Información extraída por PyMuPDF / Tesseract
    extraction_method: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    extracted_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # JSON original generado y validado a partir de Ollama
    extracted_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # Seguimiento del procesamiento
    processing_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
    )

    processing_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relación: un documento puede tener muchos conceptos
    items: Mapped[list["DocumentItem"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class DocumentItem(Base):
    """Representa un producto o servicio de una factura."""

    __tablename__ = "document_items"

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "line_number",
            name="uq_document_items_document_line",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    document_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    line_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    product_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    quantity: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 3),
        nullable=True,
    )

    unit: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    unit_price: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
    )

    tax_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )

    tax_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
    )

    line_total: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
    )

    # Relación inversa con la factura
    document: Mapped["Document"] = relationship(
        back_populates="items",
    )

