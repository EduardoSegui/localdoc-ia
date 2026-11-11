import sys
from pathlib import Path

from localdoc_ia.ingestion.extractor import extract_document
from localdoc_ia.agent.llm import extract_invoice_data, extract_invoice_from_vision

# 1. Permite pasar el archivo por consola. Si no pasas nada, usa el de prueba por defecto.
# Ejemplo de uso: uv run python probar_extraccion.py data/samples/F8161405585.pdf
file_path_str = sys.argv[1] if len(sys.argv) > 1 else "data/samples/facturaPrueba.png"
file_path = Path(file_path_str)

print("=" * 60)
print("LOCALDOC AI - PRUEBA DE EXTRACCIÓN HÍBRIDA")
print(f"Archivo a procesar: {file_path.name}")
print("=" * 60)

if not file_path.exists():
    print(f"\n❌ Error: El archivo {file_path} no existe.")
    sys.exit(1)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
is_image = file_path.suffix.lower() in IMAGE_EXTENSIONS

try:
    if is_image:
        print("\n[1] Imagen detectada. Saltando OCR clásico...")
        print("\n[2] Enviando imagen cruda al modelo de Visión (Qwen 2.5 VL)...")
        
        invoice = extract_invoice_from_vision(
            image_path=file_path,
            model="qwen2.5vl:7b" 
        )
        
    else:
        print("\n[1] Documento PDF detectado. Extrayendo texto nativo...")
        extraction = extract_document(file_path)
        
        print(f"Método: {extraction.method} | Caracteres extraídos: {len(extraction.text)}")
        
        # Mostrar exactamente qué texto se le está enviando al LLM
        print("\n--- TEXTO EXTRAÍDO (Entrada del LLM) ---")
        print(extraction.text)
        print("----------------------------------------\n")
        
        print("[2] Generando datos estructurados con el LLM de texto...")
        invoice = extract_invoice_data(document_text=extraction.text)

except Exception as e:
    print("\n❌ FALLÓ LA EXTRACCIÓN:")
    print(str(e))
    print("\nTip: Si el error viene de Pydantic, significa que Qwen no respetó la estructura JSON.")
    sys.exit(1)

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
if invoice.items:
    for item in invoice.items:
        print(
            f"{item.line_number or '-'}. {item.description[:30]}... | "
            f"Cantidad: {item.quantity} | "
            f"Precio: {item.unit_price} | "
            f"Total: {item.line_total}"
        )
else:
    print("No se extrajeron productos/servicios.")

print("\n" + "=" * 60)
print("PROCESAMIENTO FINALIZADO")
print("=" * 60)

# 4. Guardar copia
output_path = Path("reports/factura_extraida.json")
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(invoice.model_dump_json(indent=2), encoding="utf-8")
print(f"\nJSON guardado en: {output_path}")