from ollama import Client
from pydantic import ValidationError
import base64
from pathlib import Path

from localdoc_ia.agent.invoice_prompts import (
    SYSTEM_PROMPT,
    build_invoice_prompt,
)
from localdoc_ia.config import settings
from localdoc_ia.schemas import InvoiceData


def extract_invoice_data(
    document_text: str,
    model: str = "gpt-oss:20b",
    client: Client | None = None,
) -> InvoiceData:
    """
    Utiliza Ollama para extraer información estructurada de una factura.

    Args:
        document_text: Texto extraído del PDF o imagen.
        model: Modelo Ollama opcional.
        client: Cliente Ollama opcional, útil para pruebas.

    Returns:
        InvoiceData: Información extraída y validada con Pydantic.
    """

    if not document_text or not document_text.strip():
        raise ValueError(
            "No se puede extraer información: el documento no contiene texto."
        )

    selected_model = model or settings.ollama_model

    ollama_client = client or Client(
        host=settings.ollama_host,
    )

    user_prompt = build_invoice_prompt(document_text)
    invoice_schema = InvoiceData.model_json_schema()

    try:
        response = ollama_client.chat(
            model=selected_model,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            format=invoice_schema,
            options={
                # Forzamos 0.0 para extracción determinista, ignorando el .env
                "temperature": 0.0,
                "top_p": 0.1,
            },
            stream=False,
        )

    except Exception as error:
        raise RuntimeError(
            f"No se pudo completar la solicitud a Ollama. "
            f"Verificá el servidor y el modelo '{selected_model}'."
        ) from error

    response_text = response.message.content

    if not response_text or not response_text.strip():
        raise RuntimeError(
            "Ollama devolvió una respuesta vacía."
        )

    try:
        invoice = InvoiceData.model_validate_json(
            response_text
        )
    except ValidationError as error:
        raise ValueError(
            "Ollama devolvió datos que no cumplen "
            "con el esquema InvoiceData."
        ) from error

    return invoice



def extract_invoice_from_vision(
    image_path: Path,
    model: str = "llama3.2-vision",
) -> InvoiceData:
    """Extrae datos enviando la imagen directamente a un VLM en Ollama."""
    
    ollama_client = Client(host=settings.ollama_host)
    invoice_schema = InvoiceData.model_json_schema()
    
    # Construir un prompt adaptado a imágenes
    system_instruction = """
    Sos un experto analista contable argentino. 
    Tu tarea es analizar la imagen de la factura proporcionada y extraer 
    sus datos estrictamente en el esquema JSON solicitado.
    Aplicá las mismas reglas de CUITs, fechas (YYYY-MM-DD) e importes decimales.
    El nombre, domicilio y CUIT que aparecen en el recuadro superior izquierdo 
    corresponden OBLIGATORIAMENTE al PROVEEDOR, nunca al cliente.
    El valor final indicado como 'Importe Total:$' debe mapearse 
    al campo total. No lo coloques en campos de impuestos.
    NUNCA calcules matemáticamente ni inventes montos de impuestos (como el IVA) 
    si la factura no los muestra explícitamente impresos en su resumen.
    Las Facturas C no discriminan IVA.
    """
    
    try:
        response = ollama_client.chat(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": system_instruction,
                },
                {
                    "role": "user",
                    "content": "Extraé los datos de esta factura utilizando el esquema JSON provisto.",
                    "images": [str(image_path.resolve())] # Ollama acepta la ruta o el base64 directamente
                }
            ],
            format=invoice_schema,
            options={
                "temperature": 0.0,
            },
        )
    except Exception as error:
        raise RuntimeError(f"Error procesando imagen con {model}: {error}")

    return InvoiceData.model_validate_json(response.message.content)