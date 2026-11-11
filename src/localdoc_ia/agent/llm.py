
from ollama import Client
from pydantic import ValidationError

from localdoc_ia.agent.prompts import (
    SYSTEM_PROMPT,
    build_invoice_prompt,
)
from localdoc_ia.config import settings
from localdoc_ia.schemas import InvoiceData


def extract_invoice_data(
    document_text: str,
    model: str | None = None,
    client: Client | None = None,
) -> InvoiceData:
    """
    Utiliza Ollama para extraer información estructurada de una factura.

    Args:
        document_text: Texto extraído del PDF o imagen.
        model: Modelo Ollama opcional. Si no se indica,
               utiliza el configurado en .env.
        client: Cliente Ollama opcional, útil para pruebas.

    Returns:
        InvoiceData: Información extraída y validada con Pydantic.

    Raises:
        ValueError: Si el documento no contiene texto o la respuesta
                    no cumple el esquema de datos.
        RuntimeError: Si Ollama no responde correctamente.
    """

    # 1. Comprobar que haya texto para procesar
    if not document_text or not document_text.strip():
        raise ValueError(
            "No se puede extraer información: el documento no contiene texto."
        )

    # 2. Seleccionar el modelo configurado
    selected_model = model or settings.ollama_model

    # 3. Crear el cliente de Ollama
    ollama_client = client or Client(
        host=settings.ollama_host,
    )

    # 4. Construir el prompt
    user_prompt = build_invoice_prompt(document_text)

    # 5. Obtener el JSON Schema desde Pydantic
    invoice_schema = InvoiceData.model_json_schema()

    # 6. Solicitar la extracción a Ollama
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
                "temperature": settings.ollama_temperature,
            },
            stream=False,
        )

    except Exception as error:
        raise RuntimeError(
            f"No se pudo completar la solicitud a Ollama. "
            f"Verificá el servidor y el modelo '{selected_model}'."
        ) from error

    # 7. Obtener el contenido generado
    response_text = response.message.content

    if not response_text or not response_text.strip():
        raise RuntimeError(
            "Ollama devolvió una respuesta vacía."
        )

    # 8. Validar el JSON con Pydantic
    try:
        invoice = InvoiceData.model_validate_json(
            response_text
        )

    except ValidationError as error:
        raise ValueError(
            "Ollama devolvió datos que no cumplen "
            "con el esquema InvoiceData."
        ) from error

    # 9. Devolver el objeto validado
    return invoice
