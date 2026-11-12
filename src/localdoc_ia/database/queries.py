
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select

from localdoc_ia.database.connection import SessionLocal
from localdoc_ia.database.models import Document


def _build_filters(
    termino: str | None = None,
    proveedor: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    document_id: int | None = None,
) -> list[Any]:
    """Construye filtros reutilizables para las consultas."""

    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        raise ValueError(
            "La fecha desde no puede ser posterior a la fecha hasta."
        )

    filters = []

    if document_id is not None:
        if document_id < 1:
            raise ValueError("El ID del documento debe ser positivo.")

        filters.append(Document.id == document_id)

    if termino and termino.strip():
        pattern = f"%{termino.strip()}%"

        filters.append(
            or_(
                Document.original_filename.ilike(pattern),
                Document.document_number.ilike(pattern),
                Document.point_of_sale.ilike(pattern),
                Document.supplier_name.ilike(pattern),
                Document.supplier_tax_id.ilike(pattern),
                Document.customer_name.ilike(pattern),
                Document.customer_tax_id.ilike(pattern),
            )
        )

    if proveedor and proveedor.strip():
        pattern = f"%{proveedor.strip()}%"

        filters.append(
            or_(
                Document.supplier_name.ilike(pattern),
                Document.supplier_tax_id.ilike(pattern),
            )
        )

    if fecha_desde:
        filters.append(Document.issue_date >= fecha_desde)

    if fecha_hasta:
        filters.append(Document.issue_date <= fecha_hasta)

    return filters


def _amount_to_string(value: Decimal | int | None) -> str:
    """Convierte importes a texto sin perder precisión decimal."""

    if value is None:
        return "0.00"

    return str(value)


def _serialize_document(document: Document) -> dict[str, Any]:
    """Convierte un documento ORM en un diccionario serializable."""

    return {
        "id": document.id,
        "original_filename": document.original_filename,
        "document_type": document.document_type,
        "point_of_sale": document.point_of_sale,
        "document_number": document.document_number,
        "issue_date": (
            document.issue_date.isoformat()
            if document.issue_date else None
        ),
        "due_date": (
            document.due_date.isoformat()
            if document.due_date else None
        ),
        "supplier_name": document.supplier_name,
        "supplier_tax_id": document.supplier_tax_id,
        "customer_name": document.customer_name,
        "customer_tax_id": document.customer_tax_id,
        "currency": document.currency,
        "subtotal": _amount_to_string(document.subtotal),
        "tax_total": _amount_to_string(document.tax_total),
        "other_taxes": _amount_to_string(document.other_taxes),
        "discounts": _amount_to_string(document.discounts),
        "total": _amount_to_string(document.total),
        "processing_status": document.processing_status,
        "extraction_method": document.extraction_method,
        "created_at": (
            document.created_at.isoformat()
            if document.created_at else None
        ),
    }


def buscar_documentos(
    termino: str | None = None,
    proveedor: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    limite: int = 20,
    desplazamiento: int = 0,
    document_id: int | None = None,
) -> dict[str, Any]:
    """
    Busca documentos por texto, proveedor y rango de fechas.

    La búsqueda de texto considera nombre de archivo, número,
    punto de venta, proveedor y cliente.
    """

    if not 1 <= limite <= 100:
        raise ValueError("El límite debe estar entre 1 y 100.")

    if desplazamiento < 0:
        raise ValueError("El desplazamiento no puede ser negativo.")

    filters = _build_filters(
        termino=termino,
        proveedor=proveedor,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        document_id=document_id,
    )

    with SessionLocal() as session:
        total = session.scalar(
            select(func.count(Document.id)).where(*filters)
        ) or 0

        statement = (
            select(Document)
            .where(*filters)
            .order_by(
                Document.issue_date.desc().nullslast(),
                Document.id.desc(),
            )
            .offset(desplazamiento)
            .limit(limite)
        )

        documents = session.scalars(statement).all()

        return {
            "total_encontrados": total,
            "limite": limite,
            "desplazamiento": desplazamiento,
            "documentos": [
                _serialize_document(document)
                for document in documents
            ],
        }


def consultar_gastos(
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    proveedor: str | None = None,
    document_id: int | None = None
) -> dict[str, Any]:
    """
    Calcula gastos agrupados por moneda y proveedor.

    No suma monedas diferentes entre sí.
    Solo considera documentos con procesamiento completado.
    """

    filters = _build_filters(
        proveedor=proveedor,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        document_id=document_id
    )

    filters.append(Document.processing_status == "completed")

    with SessionLocal() as session:

        # Resumen general, separado por moneda.
        currency_statement = (
            select(
                Document.currency,
                func.count(Document.id).label("document_count"),
                func.coalesce(
                    func.sum(Document.subtotal), 0
                ).label("subtotal"),
                func.coalesce(
                    func.sum(Document.tax_total), 0
                ).label("tax_total"),
                func.coalesce(
                    func.sum(Document.total), 0
                ).label("total"),
            )
            .where(*filters)
            .group_by(Document.currency)
            .order_by(Document.currency)
        )

        currency_rows = session.execute(currency_statement).all()

        currencies = [
            {
                "moneda": currency or "NO_ESPECIFICADA",
                "cantidad_documentos": count,
                "subtotal": _amount_to_string(subtotal),
                "impuestos": _amount_to_string(taxes),
                "total": _amount_to_string(total),
            }
            for currency, count, subtotal, taxes, total in currency_rows
        ]

        # Desglose por proveedor y moneda.
        supplier_statement = (
            select(
                Document.supplier_name,
                Document.currency,
                func.count(Document.id).label("document_count"),
                func.coalesce(
                    func.sum(Document.total), 0
                ).label("total"),
            )
            .where(*filters)
            .group_by(
                Document.supplier_name,
                Document.currency,
            )
            .order_by(
                func.sum(Document.total).desc()
            )
            .limit(20)
        )

        supplier_rows = session.execute(supplier_statement).all()

        suppliers = [
            {
                "proveedor": name or "NO_ESPECIFICADO",
                "moneda": currency or "NO_ESPECIFICADA",
                "cantidad_documentos": count,
                "total": _amount_to_string(total),
            }
            for name, currency, count, total in supplier_rows
        ]

    return {
        "filtros": {
            "fecha_desde": (
                fecha_desde.isoformat() if fecha_desde else None
            ),
            "fecha_hasta": (
                fecha_hasta.isoformat() if fecha_hasta else None
            ),
            "proveedor": proveedor,
        },
        "resumen_por_moneda": currencies,
        "resumen_por_proveedor": suppliers,
        "nota": (
            "Los importes están agrupados por moneda. "
            "No se suman monedas diferentes entre sí."
        ),
    }


def obtener_documentos_para_reporte(
    termino: str | None = None,
    proveedor: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    maximo_registros: int = 10000,
    document_id: int | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """
    Recupera documentos para exportarlos.

    Devuelve los registros y un indicador de si hubo truncamiento.
    """

    if not 1 <= maximo_registros <= 10000:
        raise ValueError(
            "El máximo de registros debe estar entre 1 y 10000."
        )

    filters = _build_filters(
        termino=termino,
        proveedor=proveedor,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        document_id=document_id,
    )

    with SessionLocal() as session:
        total = session.scalar(
            select(func.count(Document.id)).where(*filters)
        ) or 0

        statement = (
            select(Document)
            .where(*filters)
            .order_by(
                Document.issue_date.desc().nullslast(),
                Document.id.desc(),
            )
            .limit(maximo_registros)
        )

        documents = session.scalars(statement).all()

        records = [
            _serialize_document(document)
            for document in documents
        ]

        truncated = total > len(records)

    return records, truncated
