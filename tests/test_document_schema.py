
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from localdoc_ia.schemas import InvoiceData


@pytest.fixture
def invoice_payload():
    """Datos ficticios para probar el esquema."""

    return {
        "document_type": "Factura A",
        "point_of_sale": "0001",
        "document_number": "00000045",
        "issue_date": "03/11/2026",
        "due_date": "03/12/2026",
        "currency": "ARS",
        "supplier_name": "Soluciones Informáticas del Litoral SRL",
        "supplier_tax_id": "30000000000",
        "supplier_address": "Rosario, Santa Fe",
        "customer_name": "Empresa Demo SA",
        "customer_tax_id": "30700000000",
        "customer_address": "Rosario, Santa Fe",
        "subtotal": 120000.00,
        "tax_total": 25200.00,
        "other_taxes": 0,
        "discounts": 0,
        "total": 145200.00,
        "items": [
            {
                "line_number": 1,
                "description": "Teclado",
                "quantity": 2,
                "unit": "unidad",
                "unit_price": 50000,
                "tax_rate": 21,
                "tax_amount": 21000,
                "line_total": 100000,
            },
            {
                "line_number": 2,
                "description": "Servicio técnico",
                "quantity": 1,
                "unit": "servicio",
                "unit_price": 20000,
                "tax_rate": 21,
                "tax_amount": 4200,
                "line_total": 20000,
            },
        ],
        "tax_breakdown": [
            {
                "name": "IVA",
                "rate": 21,
                "taxable_base": 120000,
                "amount": 25200,
            }
        ],
        "observations": [],
    }


def test_invoice_is_valid(invoice_payload):
    invoice = InvoiceData.model_validate(invoice_payload)

    assert invoice.document_type == "Factura A"
    assert invoice.supplier_name == (
        "Soluciones Informáticas del Litoral SRL"
    )
    assert invoice.total == Decimal("145200.0")
    assert len(invoice.items) == 2


def test_dates_are_normalized(invoice_payload):
    invoice = InvoiceData.model_validate(invoice_payload)

    assert invoice.issue_date == date(2026, 11, 3)
    assert invoice.due_date == date(2026, 12, 3)


def test_tax_id_is_normalized(invoice_payload):
    invoice = InvoiceData.model_validate(invoice_payload)

    assert invoice.supplier_tax_id == "30-00000000-0"


def test_currency_is_normalized(invoice_payload):
    invoice_payload["currency"] = "pesos"

    invoice = InvoiceData.model_validate(invoice_payload)

    assert invoice.currency == "ARS"


def test_unknown_field_is_rejected(invoice_payload):
    invoice_payload["invented_field"] = "dato incorrecto"

    with pytest.raises(ValidationError):
        InvoiceData.model_validate(invoice_payload)


def test_invalid_tax_rate_is_rejected(invoice_payload):
    invoice_payload["items"][0]["tax_rate"] = 150

    with pytest.raises(ValidationError):
        InvoiceData.model_validate(invoice_payload)


def test_invalid_date_is_rejected(invoice_payload):
    invoice_payload["issue_date"] = "31/31/2026"

    with pytest.raises(ValidationError):
        InvoiceData.model_validate(invoice_payload)
