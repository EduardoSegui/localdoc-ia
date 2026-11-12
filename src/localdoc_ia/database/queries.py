
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import cast, func, or_, select, String
from sqlalchemy.orm import selectinload

from localdoc_ia.database.connection import SessionLocal
from localdoc_ia.database.models import Document, DocumentItem


def _build_filters(
    termino: str | None = None,
    proveedor: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    document_id: int | None = None,
    moneda: str | None = None,
    monto_minimo: float | Decimal | None = None,
    monto_maximo: float | Decimal | None = None,
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
                Document.items.any(DocumentItem.description.ilike(pattern)),
                Document.extracted_text.ilike(pattern),
                cast(Document.observations, String).ilike(pattern),
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

    if moneda and moneda.strip():
        filters.append(Document.currency.ilike(moneda.strip()))

    if monto_minimo is not None:
        try:
            filters.append(Document.total >= Decimal(str(monto_minimo)))
        except (InvalidOperation, ValueError):
            raise ValueError("monto_minimo debe ser un valor numérico válido.")

    if monto_maximo is not None:
        try:
            filters.append(Document.total <= Decimal(str(monto_maximo)))
        except (InvalidOperation, ValueError):
            raise ValueError("monto_maximo debe ser un valor numérico válido.")

    return filters


def _amount_to_string(value: Decimal | int | None) -> str:
    """Convierte importes a texto sin perder precisión decimal."""

    if value is None:
        return "0.00"

    return str(value)


def _serialize_document(document: Document) -> dict[str, Any]:
    """Convierte un documento ORM en un diccionario serializable."""

    obs_list: list[str] = []
    if document.observations:
        obs_list = list(document.observations)
    elif document.extracted_data and isinstance(
        document.extracted_data.get("observations"), list
    ):
        obs_list = [
            str(obs) for obs in document.extracted_data["observations"]
        ]

    obs_text = " | ".join(obs_list) if obs_list else ""

    items_list: list[dict[str, Any]] = []
    if document.items:
        for it in document.items:
            items_list.append(
                {
                    "line_number": it.line_number,
                    "description": it.description,
                    "product_code": it.product_code,
                    "quantity": (
                        _amount_to_string(it.quantity)
                        if it.quantity is not None
                        else None
                    ),
                    "unit": it.unit,
                    "unit_price": (
                        _amount_to_string(it.unit_price)
                        if it.unit_price is not None
                        else None
                    ),
                    "tax_rate": (
                        _amount_to_string(it.tax_rate)
                        if it.tax_rate is not None
                        else None
                    ),
                    "tax_amount": (
                        _amount_to_string(it.tax_amount)
                        if it.tax_amount is not None
                        else None
                    ),
                    "line_total": (
                        _amount_to_string(it.line_total)
                        if it.line_total is not None
                        else None
                    ),
                }
            )
    elif document.extracted_data and isinstance(
        document.extracted_data.get("items"), list
    ):
        for raw_it in document.extracted_data["items"]:
            if isinstance(raw_it, dict):
                items_list.append(
                    {
                        "line_number": raw_it.get("line_number") or 1,
                        "description": str(raw_it.get("description") or ""),
                        "product_code": raw_it.get("product_code"),
                        "quantity": (
                            str(raw_it.get("quantity"))
                            if raw_it.get("quantity") is not None
                            else None
                        ),
                        "unit": raw_it.get("unit"),
                        "unit_price": (
                            str(raw_it.get("unit_price"))
                            if raw_it.get("unit_price") is not None
                            else None
                        ),
                        "tax_rate": (
                            str(raw_it.get("tax_rate"))
                            if raw_it.get("tax_rate") is not None
                            else None
                        ),
                        "tax_amount": (
                            str(raw_it.get("tax_amount"))
                            if raw_it.get("tax_amount") is not None
                            else None
                        ),
                        "line_total": (
                            str(raw_it.get("line_total"))
                            if raw_it.get("line_total") is not None
                            else None
                        ),
                    }
                )

    items_detail_parts = []
    for it in items_list:
        desc = it.get("description", "")
        qty = it.get("quantity")
        price = it.get("unit_price")
        total = it.get("line_total")
        details = []
        if qty is not None:
            details.append(f"Cant: {qty}")
        if price is not None:
            details.append(f"Precio: {price}")
        if total is not None:
            details.append(f"Total: {total}")
        detail_str = f" ({', '.join(details)})" if details else ""
        items_detail_parts.append(
            f"{it.get('line_number') or '-'}. {desc}{detail_str}"
        )

    items_detail = " | ".join(items_detail_parts)

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
        "observations": obs_text,
        "observations_list": obs_list,
        "items_count": len(items_list),
        "items_detail": items_detail,
        "items": items_list,
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
    moneda: str | None = None,
    monto_minimo: float | Decimal | None = None,
    monto_maximo: float | Decimal | None = None,
    ordenar_por: str | None = "fecha",
    orden: str | None = "desc",
) -> dict[str, Any]:
    """
    Busca documentos por texto, proveedor, rango de fechas, moneda y rango de importes.

    Permite ordenar por 'total' / 'monto' (para consultar la factura de mayor o menor saldo),
    'fecha', 'proveedor' o 'id', de forma ascendente ('asc') o descendente ('desc').
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
        moneda=moneda,
        monto_minimo=monto_minimo,
        monto_maximo=monto_maximo,
    )

    orden_normalizado = (orden or "desc").lower().strip()
    if orden_normalizado not in {"asc", "desc"}:
        orden_normalizado = "desc"

    criterio = (ordenar_por or "fecha").lower().strip()
    if criterio in {"total", "monto", "saldo", "importe"}:
        order_col = Document.total
    elif criterio in {"proveedor", "supplier", "supplier_name"}:
        order_col = Document.supplier_name
    elif criterio in {"id", "document_id"}:
        order_col = Document.id
    else:
        order_col = Document.issue_date

    if orden_normalizado == "asc":
        order_clause = [order_col.asc().nullslast(), Document.id.asc()]
    else:
        order_clause = [order_col.desc().nullslast(), Document.id.desc()]

    with SessionLocal() as session:
        total = session.scalar(
            select(func.count(Document.id)).where(*filters)
        ) or 0

        statement = (
            select(Document)
            .options(selectinload(Document.items))
            .where(*filters)
            .order_by(*order_clause)
            .offset(desplazamiento)
            .limit(limite)
        )

        documents = session.scalars(statement).all()

        return {
            "total_encontrados": total,
            "limite": limite,
            "desplazamiento": desplazamiento,
            "ordenar_por": criterio,
            "orden": orden_normalizado,
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
    moneda: str | None = None,
    monto_minimo: float | Decimal | None = None,
    monto_maximo: float | Decimal | None = None,
    ordenar_por: str | None = "fecha",
    orden: str | None = "desc",
) -> tuple[list[dict[str, Any]], bool]:
    """
    Recupera documentos para exportarlos.

    Permite filtrar por moneda, monto y ordenar por fecha, total, proveedor o id.
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
        moneda=moneda,
        monto_minimo=monto_minimo,
        monto_maximo=monto_maximo,
    )

    orden_normalizado = (orden or "desc").lower().strip()
    if orden_normalizado not in {"asc", "desc"}:
        orden_normalizado = "desc"

    criterio = (ordenar_por or "fecha").lower().strip()
    if criterio in {"total", "monto", "saldo", "importe"}:
        order_col = Document.total
    elif criterio in {"proveedor", "supplier", "supplier_name"}:
        order_col = Document.supplier_name
    elif criterio in {"id", "document_id"}:
        order_col = Document.id
    else:
        order_col = Document.issue_date

    if orden_normalizado == "asc":
        order_clause = [order_col.asc().nullslast(), Document.id.asc()]
    else:
        order_clause = [order_col.desc().nullslast(), Document.id.desc()]

    with SessionLocal() as session:
        total = session.scalar(
            select(func.count(Document.id)).where(*filters)
        ) or 0

        statement = (
            select(Document)
            .options(selectinload(Document.items))
            .where(*filters)
            .order_by(*order_clause)
            .limit(maximo_registros)
        )

        documents = session.scalars(statement).all()

        records = [
            _serialize_document(document)
            for document in documents
        ]

        truncated = total > len(records)

    return records, truncated


def obtener_estadisticas_facturas(
    moneda: str | None = None,
    proveedor: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
) -> dict[str, Any]:
    """
    Calcula estadísticas analíticas de las facturas registradas:
    - Factura con mayor saldo / importe.
    - Factura con menor saldo / importe.
    - Comparativa directa entre extremos (diferencia monetaria y relación).
    - Monto total acumulado, subtotales, impuestos y promedio por comprobante.
    - Top facturas con mayor importe.
    - Proveedor con mayor concentración de gasto.
    """

    base_filters = _build_filters(
        proveedor=proveedor,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        moneda=moneda,
    )
    base_filters.append(Document.processing_status == "completed")

    with SessionLocal() as session:
        total_analizados = session.scalar(
            select(func.count(Document.id)).where(*base_filters)
        ) or 0

        if total_analizados == 0:
            return {
                "total_facturas_analizadas": 0,
                "mensaje": "No se encontraron facturas completadas con los filtros indicados.",
                "resumen_por_moneda": [],
            }

        monedas_existentes = session.scalars(
            select(Document.currency)
            .where(*base_filters)
            .distinct()
            .order_by(Document.currency.nullslast())
        ).all()

        resumen_por_moneda = []

        for curr in monedas_existentes:
            curr_label = curr or "NO_ESPECIFICADA"
            curr_filter = list(base_filters)
            if curr is None:
                curr_filter.append(Document.currency.is_(None))
            else:
                curr_filter.append(Document.currency == curr)

            valid_total_filter = list(curr_filter)
            valid_total_filter.append(Document.total.isnot(None))
            valid_total_filter.append(Document.total > 0)

            stats_row = session.execute(
                select(
                    func.count(Document.id).label("total_docs"),
                    func.coalesce(func.sum(Document.subtotal), 0).label("subtotal"),
                    func.coalesce(func.sum(Document.tax_total), 0).label("impuestos"),
                    func.coalesce(func.sum(Document.total), 0).label("total"),
                ).where(*curr_filter)
            ).one()

            total_docs = stats_row.total_docs
            total_acumulado = stats_row.total

            docs_con_total = session.scalar(
                select(func.count(Document.id)).where(*valid_total_filter)
            ) or 0

            promedio_ticket = (
                (total_acumulado / Decimal(docs_con_total))
                if docs_con_total > 0
                else Decimal("0.00")
            )

            top_mayores_docs = session.scalars(
                select(Document)
                .options(selectinload(Document.items))
                .where(*valid_total_filter)
                .order_by(Document.total.desc(), Document.id.desc())
                .limit(3)
            ).all()

            factura_mayor = None
            top_mayores = []
            if top_mayores_docs:
                doc_max = top_mayores_docs[0]
                factura_mayor = {
                    "archivo": doc_max.original_filename,
                    "proveedor": doc_max.supplier_name or "No identificado",
                    "fecha": (
                        doc_max.issue_date.isoformat()
                        if doc_max.issue_date else None
                    ),
                    "total": _amount_to_string(doc_max.total),
                    "moneda": curr_label,
                    "comprobante": doc_max.document_type or "No identificado",
                    "numero_comprobante": doc_max.document_number,
                    "punto_venta": doc_max.point_of_sale,
                    "items": [it.description for it in doc_max.items],
                    "observaciones": (
                        doc_max.observations or []
                    ),
                }
                top_mayores = [
                    {
                        "archivo": d.original_filename,
                        "proveedor": d.supplier_name or "No identificado",
                        "total": _amount_to_string(d.total),
                        "fecha": d.issue_date.isoformat() if d.issue_date else None,
                        "numero_comprobante": d.document_number,
                        "punto_venta": d.point_of_sale,
                    }
                    for d in top_mayores_docs
                ]

            top_menores_docs = session.scalars(
                select(Document)
                .options(selectinload(Document.items))
                .where(*valid_total_filter)
                .order_by(Document.total.asc(), Document.id.asc())
                .limit(3)
            ).all()

            factura_menor = None
            if top_menores_docs:
                doc_min = top_menores_docs[0]
                factura_menor = {
                    "archivo": doc_min.original_filename,
                    "proveedor": doc_min.supplier_name or "No identificado",
                    "fecha": (
                        doc_min.issue_date.isoformat()
                        if doc_min.issue_date else None
                    ),
                    "total": _amount_to_string(doc_min.total),
                    "moneda": curr_label,
                    "comprobante": doc_min.document_type or "No identificado",
                    "numero_comprobante": doc_min.document_number,
                    "punto_venta": doc_min.point_of_sale,
                    "items": [it.description for it in doc_min.items],
                    "observaciones": (
                        doc_min.observations or []
                    ),
                }

            comparativa_extremos = None
            if top_mayores_docs and top_menores_docs:
                val_max = top_mayores_docs[0].total
                val_min = top_menores_docs[0].total
                diff = val_max - val_min
                ratio = (val_max / val_min) if val_min > 0 else None

                max_label = (
                    top_mayores_docs[0].document_number
                    or top_mayores_docs[0].original_filename
                    or f"ID {top_mayores_docs[0].id}"
                )
                min_label = (
                    top_menores_docs[0].document_number
                    or top_menores_docs[0].original_filename
                    or f"ID {top_menores_docs[0].id}"
                )

                comparativa_extremos = {
                    "diferencia": _amount_to_string(diff),
                    "relacion_veces": round(float(ratio), 2) if ratio else None,
                    "resumen": (
                        f"La factura de mayor monto (comprobante {max_label}: "
                        f"${_amount_to_string(val_max)}) supera a la de menor "
                        f"monto (comprobante {min_label}: "
                        f"${_amount_to_string(val_min)}) por "
                        f"${_amount_to_string(diff)} {curr_label}"
                        + (f" ({round(float(ratio), 1)} veces)." if ratio else ".")
                    ),
                }

            top_prov_row = session.execute(
                select(
                    Document.supplier_name,
                    func.sum(Document.total).label("total_prov"),
                    func.count(Document.id).label("count_prov"),
                )
                .where(*curr_filter, Document.supplier_name.isnot(None))
                .group_by(Document.supplier_name)
                .order_by(func.sum(Document.total).desc())
                .limit(1)
            ).first()

            proveedor_top = None
            if top_prov_row:
                proveedor_top = {
                    "proveedor": top_prov_row[0],
                    "total_gastado": _amount_to_string(top_prov_row[1]),
                    "cantidad_facturas": top_prov_row[2],
                }

            resumen_por_moneda.append(
                {
                    "moneda": curr_label,
                    "cantidad_facturas": total_docs,
                    "facturas_con_monto": docs_con_total,
                    "subtotal_acumulado": _amount_to_string(stats_row.subtotal),
                    "impuestos_acumulados": _amount_to_string(stats_row.impuestos),
                    "total_acumulado": _amount_to_string(total_acumulado),
                    "promedio_por_factura": _amount_to_string(round(promedio_ticket, 2)),
                    "factura_mayor": factura_mayor,
                    "factura_menor": factura_menor,
                    "comparativa_extremos": comparativa_extremos,
                    "top_3_mayores": top_mayores,
                    "proveedor_principal_gasto": proveedor_top,
                }
            )

        return {
            "filtros": {
                "moneda": moneda,
                "proveedor": proveedor,
                "fecha_desde": fecha_desde.isoformat() if fecha_desde else None,
                "fecha_hasta": fecha_hasta.isoformat() if fecha_hasta else None,
            },
            "total_facturas_analizadas": total_analizados,
            "resumen_por_moneda": resumen_por_moneda,
        }


def comparar_periodos(
    fecha_desde_1: date,
    fecha_hasta_1: date,
    fecha_desde_2: date,
    fecha_hasta_2: date,
    proveedor: str | None = None,
    moneda: str | None = None,
) -> dict[str, Any]:
    """
    Compara el gasto y cantidad de comprobantes entre dos períodos de fechas.
    Calcula la variación porcentual y la diferencia absoluta.
    """

    if fecha_desde_1 > fecha_hasta_1:
        raise ValueError(
            "El período 1 tiene fecha_desde posterior a fecha_hasta."
        )

    if fecha_desde_2 > fecha_hasta_2:
        raise ValueError(
            "El período 2 tiene fecha_desde posterior a fecha_hasta."
        )

    filters_p1 = _build_filters(
        proveedor=proveedor,
        fecha_desde=fecha_desde_1,
        fecha_hasta=fecha_hasta_1,
        moneda=moneda,
    )
    filters_p1.append(Document.processing_status == "completed")

    filters_p2 = _build_filters(
        proveedor=proveedor,
        fecha_desde=fecha_desde_2,
        fecha_hasta=fecha_hasta_2,
        moneda=moneda,
    )
    filters_p2.append(Document.processing_status == "completed")

    with SessionLocal() as session:
        def _get_metrics(f):
            row = session.execute(
                select(
                    func.count(Document.id),
                    func.coalesce(func.sum(Document.total), 0),
                ).where(*f)
            ).one()
            count = row[0] or 0
            total = row[1] or Decimal("0.00")
            avg = (total / Decimal(count)) if count > 0 else Decimal("0.00")
            return count, total, avg

        count_1, total_1, avg_1 = _get_metrics(filters_p1)
        count_2, total_2, avg_2 = _get_metrics(filters_p2)

        diff_total = total_2 - total_1
        if total_1 > 0:
            var_pct = round(float((diff_total / total_1) * 100), 2)
        else:
            var_pct = 100.0 if total_2 > 0 else 0.0

        if diff_total > 0:
            tendencia = "incremento"
        elif diff_total < 0:
            tendencia = "reducción"
        else:
            tendencia = "sin variación"

        return {
            "periodo_1": {
                "desde": fecha_desde_1.isoformat(),
                "hasta": fecha_hasta_1.isoformat(),
                "cantidad_facturas": count_1,
                "total": _amount_to_string(total_1),
                "promedio": _amount_to_string(round(avg_1, 2)),
            },
            "periodo_2": {
                "desde": fecha_desde_2.isoformat(),
                "hasta": fecha_hasta_2.isoformat(),
                "cantidad_facturas": count_2,
                "total": _amount_to_string(total_2),
                "promedio": _amount_to_string(round(avg_2, 2)),
            },
            "comparacion": {
                "diferencia_total": _amount_to_string(diff_total),
                "variacion_porcentual": f"{var_pct:+.2f}%",
                "diferencia_cantidad_facturas": count_2 - count_1,
                "tendencia": tendencia,
                "conclusion": (
                    f"El período 2 tuvo una {tendencia} del {abs(var_pct)}% "
                    f"(${_amount_to_string(abs(diff_total))}) respecto al período 1."
                ),
            },
        }


def buscar_items_productos(
    termino: str | None = None,
    proveedor: str | None = None,
    fecha_desde: date | None = None,
    fecha_hasta: date | None = None,
    ordenar_por: str | None = "precio",
    orden: str | None = "desc",
    limite: int = 20,
) -> dict[str, Any]:
    """
    Busca productos y servicios facturados en las líneas de detalle (items).
    Permite conocer precios unitarios, cantidades y proveedores que vendieron cada ítem.
    """

    if not 1 <= limite <= 100:
        raise ValueError("El límite debe estar entre 1 y 100.")

    statement = (
        select(DocumentItem, Document)
        .join(Document, DocumentItem.document_id == Document.id)
    )

    filters = [Document.processing_status == "completed"]

    if termino and termino.strip():
        pattern = f"%{termino.strip()}%"
        filters.append(
            or_(
                DocumentItem.description.ilike(pattern),
                DocumentItem.product_code.ilike(pattern),
            )
        )

    if proveedor and proveedor.strip():
        prov_pat = f"%{proveedor.strip()}%"
        filters.append(
            or_(
                Document.supplier_name.ilike(prov_pat),
                Document.supplier_tax_id.ilike(prov_pat),
            )
        )

    if fecha_desde:
        filters.append(Document.issue_date >= fecha_desde)

    if fecha_hasta:
        filters.append(Document.issue_date <= fecha_hasta)

    statement = statement.where(*filters)

    criterio = (ordenar_por or "precio").lower().strip()
    if criterio in {"precio", "unit_price", "unitario"}:
        order_col = DocumentItem.unit_price
    elif criterio in {"total", "line_total"}:
        order_col = DocumentItem.line_total
    elif criterio in {"cantidad", "quantity"}:
        order_col = DocumentItem.quantity
    elif criterio in {"fecha", "date"}:
        order_col = Document.issue_date
    else:
        order_col = DocumentItem.unit_price

    orden_norm = (orden or "desc").lower().strip()
    if orden_norm == "asc":
        statement = statement.order_by(
            order_col.asc().nullslast(), DocumentItem.id.asc()
        )
    else:
        statement = statement.order_by(
            order_col.desc().nullslast(), DocumentItem.id.desc()
        )

    with SessionLocal() as session:
        stats_query = (
            select(
                func.count(DocumentItem.id),
                func.coalesce(func.sum(DocumentItem.line_total), 0),
                func.coalesce(func.avg(DocumentItem.unit_price), 0),
                func.coalesce(func.max(DocumentItem.unit_price), 0),
                func.coalesce(func.min(DocumentItem.unit_price), 0),
            )
            .join(Document, DocumentItem.document_id == Document.id)
            .where(*filters)
        )
        total_items, suma_totales, avg_unit, max_unit, min_unit = (
            session.execute(stats_query).one()
        )

        rows = session.execute(statement.limit(limite)).all()

        items_encontrados = []
        for it, doc in rows:
            items_encontrados.append(
                {
                    "item_id": it.id,
                    "linea": it.line_number,
                    "descripcion": it.description,
                    "codigo": it.product_code,
                    "cantidad": (
                        _amount_to_string(it.quantity)
                        if it.quantity is not None
                        else "1"
                    ),
                    "unidad": it.unit,
                    "precio_unitario": _amount_to_string(it.unit_price),
                    "total_linea": _amount_to_string(it.line_total),
                    "document_id": doc.id,
                    "archivo": doc.original_filename,
                    "proveedor": doc.supplier_name or "No identificado",
                    "fecha": (
                        doc.issue_date.isoformat()
                        if doc.issue_date else None
                    ),
                    "moneda": doc.currency or "ARS",
                }
            )

        return {
            "criterio_busqueda": termino,
            "total_items_coincidentes": total_items or 0,
            "precio_promedio": _amount_to_string(
                round(Decimal(str(avg_unit)), 2)
            ),
            "precio_maximo": _amount_to_string(max_unit),
            "precio_minimo": _amount_to_string(min_unit),
            "monto_total_items": _amount_to_string(suma_totales),
            "items": items_encontrados,
        }
