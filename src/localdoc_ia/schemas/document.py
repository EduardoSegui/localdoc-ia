
import re
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from decimal import Decimal, InvalidOperation
import re

from pydantic import field_validator, model_validator

class SchemaBase(BaseModel):
    """Configuración común para los esquemas del proyecto."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class TaxBreakdown(SchemaBase):
    """Representa un impuesto o una alícuota aplicada."""

    name: str = Field(
        description="Nombre del impuesto. Por ejemplo: IVA."
    )

    rate: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
        allow_inf_nan=False,
        description="Alícuota expresada como porcentaje. Ejemplo: 21.",
    )

    taxable_base: Decimal | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Base imponible del impuesto.",
    )

    amount: Decimal | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Importe correspondiente al impuesto.",
    )


class InvoiceItem(SchemaBase):
    """Representa un producto o servicio incluido en la factura."""

    line_number: int = Field(
        ge=1,
        description="Número consecutivo del ítem, comenzando en 1.",
    )

    description: str = Field(
        min_length=1,
        description="Descripción del producto o servicio.",
    )

    product_code: str | None = Field(
        default=None,
        description="Código del producto, si aparece en el documento.",
    )

    quantity: Decimal | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Cantidad de unidades.",
    )

    unit: str | None = Field(
        default=None,
        description="Unidad de medida. Por ejemplo: unidad, kg, hora.",
    )

    unit_price: Decimal | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Precio unitario.",
    )

    tax_rate: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
        allow_inf_nan=False,
        description="Alícuota de IVA u otro impuesto expresada en porcentaje.",
    )

    tax_amount: Decimal | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Importe del impuesto correspondiente al ítem.",
    )

    line_total: Decimal | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Importe total del ítem.",
    )


class InvoiceData(SchemaBase):
    """Datos estructurados extraídos de una factura."""

    # -------------------------------------------------
    # Información del comprobante
    # -------------------------------------------------

    document_type: str | None = Field(
        default=None,
        description="Tipo de comprobante. Ejemplo: Factura A, Factura B.",
    )

    point_of_sale: str | None = Field(
        default=None,
        description="Punto de venta. Conservar los ceros iniciales.",
    )

    document_number: str | None = Field(
        default=None,
        description="Número del comprobante. Conservar los ceros iniciales.",
    )

    issue_date: date | None = Field(
        default=None,
        description="Fecha de emisión en formato YYYY-MM-DD.",
    )

    due_date: date | None = Field(
        default=None,
        description="Fecha de vencimiento en formato YYYY-MM-DD.",
    )

    currency: str | None = Field(
        default=None,
        description="Código ISO de moneda. Ejemplo: ARS o USD.",
    )

    # -------------------------------------------------
    # Información del proveedor
    # -------------------------------------------------

    supplier_name: str | None = Field(
        default=None,
        description="Razón social o nombre del proveedor.",
    )

    supplier_tax_id: str | None = Field(
        default=None,
        description="CUIT del proveedor, si aparece.",
    )

    supplier_address: str | None = Field(
        default=None,
        description="Domicilio del proveedor.",
    )

    # -------------------------------------------------
    # Información del cliente
    # -------------------------------------------------

    customer_name: str | None = Field(
        default=None,
        description="Razón social o nombre del cliente.",
    )

    customer_tax_id: str | None = Field(
        default=None,
        description="CUIT del cliente, si aparece.",
    )

    customer_address: str | None = Field(
        default=None,
        description="Domicilio del cliente.",
    )

    # -------------------------------------------------
    # Información económica
    # -------------------------------------------------

    subtotal: Decimal | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Subtotal de la factura.",
    )

    tax_total: Decimal | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Total de impuestos, incluido el IVA.",
    )

    other_taxes: Decimal | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Otros impuestos, percepciones o retenciones.",
    )

    discounts: Decimal | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Importe total de descuentos.",
    )

    total: Decimal | None = Field(
        default=None,
        allow_inf_nan=False,
        description="Importe total del comprobante.",
    )

    # -------------------------------------------------
    # Detalles de la factura
    # -------------------------------------------------

    items: list[InvoiceItem] = Field(
        default_factory=list,
        description="Productos y servicios incluidos en la factura.",
    )

    tax_breakdown: list[TaxBreakdown] = Field(
        default_factory=list,
        description="Desglose de impuestos y alícuotas.",
    )

    observations: list[str] = Field(
        default_factory=list,
        description="Observaciones relevantes o datos difíciles de interpretar.",
    )

    # -------------------------------------------------
    # Normalización de datos
    # -------------------------------------------------

    @field_validator("issue_date", "due_date", mode="before")
    @classmethod
    def normalize_dates(cls, value):
        """Acepta fechas ISO y fechas argentinas DD/MM/YYYY."""

        if value is None:
            return None

        if isinstance(value, datetime):
            return value.date()

        if isinstance(value, date):
            return value

        if isinstance(value, str):
            value = value.strip()

            if not value:
                return None

            formats = (
                "%d/%m/%Y",
                "%d-%m-%Y",
                "%Y-%m-%d",
            )

            for date_format in formats:
                try:
                    return datetime.strptime(
                        value,
                        date_format,
                    ).date()
                except ValueError:
                    continue

        # Si no coincide, Pydantic realizará la validación
        # habitual y devolverá un error si la fecha es incorrecta.
        return value

    @field_validator("supplier_tax_id", "customer_tax_id")
    @classmethod
    def normalize_tax_ids(cls, value):
        """
        Normaliza CUIT cuando tiene exactamente 11 dígitos.

        No comprueba el dígito verificador porque los documentos
        de prueba pueden contener CUIT ficticios.
        """

        if value is None:
            return None

        value = value.strip()

        if not value:
            return None

        digits = re.sub(r"\D", "", value)

        if len(digits) == 11:
            return f"{digits[:2]}-{digits[2:10]}-{digits[10]}"

        # Si no tiene 11 dígitos, conservamos el valor original
        # para no perder información recuperada por OCR.
        return value

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value):
        """Normaliza el código de moneda."""

        if value is None:
            return None

        value = value.strip().upper()

        if not value:
            return None

        aliases = {
            "$": "ARS",
            "PESOS": "ARS",
            "PESO ARGENTINO": "ARS",
            "DÓLARES": "USD",
            "DOLARES": "USD",
            "DÓLAR": "USD",
            "DOLAR": "USD",
        }

        return aliases.get(value, value)
