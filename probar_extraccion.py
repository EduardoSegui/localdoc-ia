from pathlib import Path

from localdoc_ia.ingestion.extractor import extract_document
from localdoc_ia.agent.llm import extract_invoice_data


# Seleccionar una factura de prueba
file_path = Path("data/samples/F8161405585.pdf")

print("=" * 60)
print("LOCALDOC AI - PRUEBA DE EXTRACCIÓN")
print("=" * 60)

# 1. Extraer el texto del documento
print("\n[1] Extrayendo texto...")

extraction = extract_document(file_path)

print(f"Archivo: {file_path.name}")
print(f"Método: {extraction.method}")
print(f"Páginas: {extraction.page_count}")
print(f"Caracteres extraídos: {len(extraction.text)}")

# 2. Enviar el texto a Ollama
print("\n[2] Generando datos estructurados con Ollama...")

invoice = extract_invoice_data(
    document_text=extraction.text
)

# 3. Mostrar los datos validados por Pydantic
print("\n[3] Datos validados correctamente")

print("\nCOMPROBANTE")
print(f"Tipo: {invoice.document_type}")
print(f"Punto de venta: {invoice.point_of_sale}")
print(f"Número: {invoice.document_number}")
print(f"Fecha: {invoice.issue_date}")

print("\nPROVEEDOR")
print(f"Nombre: {invoice.supplier_name}")
print(f"CUIT: {invoice.supplier_tax_id}")

print("\nCLIENTE")
print(f"Nombre: {invoice.customer_name}")
print(f"CUIT: {invoice.customer_tax_id}")

print("\nIMPORTES")
print(f"Subtotal: {invoice.subtotal}")
print(f"Impuestos: {invoice.tax_total}")
print(f"Total: {invoice.total}")

print("\nPRODUCTOS Y SERVICIOS")

for item in invoice.items:
    print(
        f"{item.line_number}. {item.description} | "
        f"Cantidad: {item.quantity} | "
        f"Precio: {item.unit_price} | "
        f"Total: {item.line_total}"
    )

print("\n" + "=" * 60)
print("PROCESAMIENTO FINALIZADO")
print("=" * 60)

# 4. Guardar una copia del JSON validado para inspección
output_path = Path("reports/factura_extraida.json")
output_path.parent.mkdir(parents=True, exist_ok=True)

output_path.write_text(
    invoice.model_dump_json(indent=2),
    encoding="utf-8",
)

print(f"\nJSON guardado en: {output_path}")

