
import asyncio
import logging
import mimetypes
import re

from pathlib import Path
from uuid import uuid4

from telegram import BotCommand, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from localdoc_ia.agent.context import AgentContext
from localdoc_ia.agent.harness import AgentHarness
from localdoc_ia.config import settings
from localdoc_ia.database.repository import DuplicateDocumentError
from localdoc_ia.ingestion.extractor import SUPPORTED_IMAGE_FORMATS
from localdoc_ia.services.document_processor import (
    process_uploaded_document,
)


logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
INBOX_DIR = PROJECT_ROOT / "data" / "inbox"
REPORTS_DIR = PROJECT_ROOT / "reports"

SUPPORTED_EXTENSIONS = SUPPORTED_IMAGE_FORMATS | {".pdf"}
TELEGRAM_DOWNLOAD_LIMIT_MB = 20


def is_authorized(update: Update) -> bool:
    """
    Autoriza únicamente usuarios registrados y chats privados.

    Si no hay IDs configurados, nadie puede utilizar el bot.
    """

    user = update.effective_user
    chat = update.effective_chat

    if user is None or chat is None:
        return False

    if chat.type != "private":
        return False

    allowed_ids = settings.allowed_telegram_user_ids

    return user.id in allowed_ids


def get_agent_context(
    context: ContextTypes.DEFAULT_TYPE,
) -> AgentContext:
    """Obtiene o crea la memoria de conversación del usuario."""

    agent_context = context.user_data.get("agent_context")

    if agent_context is None:
        agent_context = AgentContext(
            max_turns=settings.max_conversation_turns
        )
        context.user_data["agent_context"] = agent_context

    return agent_context


async def reply_in_chunks(message, text: str) -> None:
    """Divide respuestas largas para respetar el límite de Telegram."""

    max_length = 4000

    if not text:
        text = "No se recibió una respuesta textual."

    for start in range(0, len(text), max_length):
        await message.reply_text(
            text[start:start + max_length]
        )


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    if not is_authorized(update):
        await update.effective_message.reply_text(
            "No estás autorizado para utilizar LocalDoc AI."
        )
        return

    get_agent_context(context)

    await update.effective_message.reply_text(
        "¡Hola! Soy LocalDoc AI.\n\n"
        "Puedo ayudarte a:\n"
        "• Buscar facturas y documentos.\n"
        "• Consultar gastos por proveedor y período.\n"
        "• Generar reportes CSV.\n"
        "• Procesar facturas en PDF e imágenes.\n\n"
        "Enviame una factura como PDF, JPG o PNG, "
        "o escribime qué información necesitás consultar.\n\n"
        "Comandos disponibles:\n"
        "/reset - Reiniciar la conversación.\n"
        "/ayuda - Mostrar las funcionalidades."
    )


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    if not is_authorized(update):
        return

    await update.effective_message.reply_text(
        "LocalDoc AI permite:\n\n"
        "1. Enviar facturas PDF e imágenes para procesarlas.\n"
        "2. Buscar documentos por proveedor, CUIT o ID.\n"
        "3. Consultar gastos por fecha y proveedor.\n"
        "4. Generar y recibir reportes CSV.\n\n"
        "Formatos: PDF, JPG, JPEG, PNG, TIFF, BMP y WEBP.\n"
        "Tamaño máximo: 20 MB."
    )


async def reset_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:

    if not is_authorized(update):
        return

    agent_context = get_agent_context(context)
    agent_context.clear()

    await update.effective_message.reply_text(
        "La memoria de esta conversación fue reiniciada."
    )


async def handle_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Envía mensajes de texto al Agent Loop."""

    if not is_authorized(update):
        await update.effective_message.reply_text(
            "No estás autorizado para utilizar LocalDoc AI."
        )
        return

    message = update.effective_message
    user_message = (message.text or "").strip()

    if not user_message:
        return

    agent_context = get_agent_context(context)

    await context.bot.send_chat_action(
        chat_id=message.chat_id,
        action=ChatAction.TYPING,
    )

    agent = AgentHarness(context=agent_context)

    try:
        result = await agent.ask(user_message)

    except Exception:
        logger.exception("Error procesando la consulta de Telegram.")

        await message.reply_text(
            "No pude procesar tu consulta. "
            "Verificá que Ollama, PostgreSQL y el servidor MCP "
            "estén funcionando."
        )
        return

    finally:
        await agent.aclose()

    await reply_in_chunks(message, result.answer)

    # Si el agente generó un CSV, entregarlo como archivo adjunto.
    for tool_result in result.tool_results:

        if tool_result["tool_name"] != "generar_reporte":
            continue

        report_data = tool_result["result"]

        if report_data.get("estado") != "generado":
            continue

        report_relative_path = report_data.get("ruta")

        if not report_relative_path:
            continue

        report_path = (
            PROJECT_ROOT / report_relative_path
        ).resolve()

        # Impedir enviar archivos fuera de reports/.
        if not report_path.is_relative_to(REPORTS_DIR.resolve()):
            logger.warning("Ruta de reporte fuera del directorio autorizado.")
            continue

        if not report_path.is_file():
            logger.warning("No existe el CSV generado: %s", report_path)
            continue

        try:
            with report_path.open("rb") as report_file:
                await message.reply_document(
                    document=report_file,
                    filename=report_path.name,
                    caption=(
                        f"Reporte generado: "
                        f"{report_data.get('registros_exportados', 0)} "
                        "facturas exportadas."
                    ),
                )

        except Exception:
            logger.exception("No se pudo enviar el CSV por Telegram.")
            await message.reply_text(
                "El reporte se generó, pero no pude adjuntarlo."
            )


async def handle_document(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Recibe PDFs e imágenes enviados como documentos."""

    if not is_authorized(update):
        await update.effective_message.reply_text(
            "No estás autorizado para utilizar LocalDoc AI."
        )
        return

    message = update.effective_message
    document = message.document

    if document is None:
        return

    original_name = document.file_name or "documento"
    extension = Path(original_name).suffix.lower()

    if not extension and document.mime_type:
        extension = mimetypes.guess_extension(document.mime_type) or ""

    await download_and_process(
        update=update,
        context=context,
        attachment=document,
        original_name=original_name,
        extension=extension,
        file_size=document.file_size,
    )


async def handle_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Recibe fotografías enviadas como imágenes de Telegram."""

    if not is_authorized(update):
        await update.effective_message.reply_text(
            "No estás autorizado para utilizar LocalDoc AI."
        )
        return

    message = update.effective_message

    if not message.photo:
        return

    # Seleccionar la versión de mayor resolución.
    photo = message.photo[-1]

    filename = f"fotografia_{message.message_id}.jpg"

    await download_and_process(
        update=update,
        context=context,
        attachment=photo,
        original_name=filename,
        extension=".jpg",
        file_size=photo.file_size,
    )


async def download_and_process(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    attachment,
    original_name: str,
    extension: str,
    file_size: int | None,
) -> None:
    """Descarga el archivo y ejecuta el procesamiento documental."""

    message = update.effective_message

    if extension.lower() not in SUPPORTED_EXTENSIONS:
        await message.reply_text(
            "Formato no soportado.\n"
            "Enviá un PDF o una imagen JPG, PNG, TIFF, BMP o WEBP."
        )
        return

    configured_limit = min(
        settings.max_file_size_mb,
        TELEGRAM_DOWNLOAD_LIMIT_MB,
    )

    max_bytes = configured_limit * 1024 * 1024

    if file_size is not None and file_size > max_bytes:
        await message.reply_text(
            f"El archivo supera el límite de {configured_limit} MB."
        )
        return

    INBOX_DIR.mkdir(parents=True, exist_ok=True)

    # Evitar path traversal y colisiones de nombres.
    safe_name = re.sub(
        r"[^A-Za-z0-9._-]",
        "_",
        Path(original_name).name,
    )

    if not Path(safe_name).suffix:
        safe_name += extension

    destination = INBOX_DIR / f"{uuid4().hex}_{safe_name}"

    await message.reply_text(
        f"Recibí el archivo '{original_name}'.\n"
        "Voy a extraer el texto, identificar los datos de la factura "
        "y guardarlos en PostgreSQL."
    )

    try:
        telegram_file = await context.bot.get_file(
            attachment.file_id
        )

        await telegram_file.download_to_drive(
            custom_path=destination
        )

        # Comprobar el tamaño real después de descargar.
        if destination.stat().st_size > max_bytes:
            destination.unlink(missing_ok=True)

            await message.reply_text(
                f"El archivo supera el límite de {configured_limit} MB."
            )
            return

        # OCR, Ollama y SQLAlchemy son operaciones síncronas.
        # Ejecutarlas en otro hilo evita bloquear el event loop.
        result = await asyncio.to_thread(
            process_uploaded_document,
            destination,
        )

        invoice = result.invoice

        # Conservar el contexto para preguntas posteriores:
        # "Generá un reporte de esta factura".
        agent_context = get_agent_context(context)

        agent_context.remember_exchange(
            user_message=f"El usuario cargó el archivo {original_name}.",
            assistant_message=(
                f"Se procesó y guardó la factura con ID "
                f"{result.document_id}. "
                f"Proveedor: {invoice.supplier_name}. "
                f"Total: {invoice.total} {invoice.currency or ''}."
            ),
        )

        summary = (
            "Documento procesado y guardado correctamente.\n\n"
            f"ID interno: {result.document_id}\n"
            f"Archivo: {original_name}\n"
            f"Proveedor: {invoice.supplier_name or 'No identificado'}\n"
            f"Comprobante: {invoice.document_type or 'No identificado'}\n"
            f"Fecha: {invoice.issue_date or 'No identificada'}\n"
            f"Moneda: {invoice.currency or 'No identificada'}\n"
            f"Subtotal: {invoice.subtotal if invoice.subtotal is not None else 'No identificado'}\n"
            f"Impuestos: {invoice.tax_total if invoice.tax_total is not None else 'No identificados'}\n"
            f"Total: {invoice.total if invoice.total is not None else 'No identificado'}\n"
            f"Método de extracción: {result.extraction.method}\n"
            f"Ítems reconocidos: {len(invoice.items)}"
        )

        if result.warnings:
            summary += "\n\nAdvertencias para revisar:\n"
            summary += "\n".join(
                f"• {warning}"
                for warning in result.warnings
            )

        await reply_in_chunks(message, summary)

    except DuplicateDocumentError as error:
        await message.reply_text(
            "Este archivo ya había sido procesado.\n"
            f"ID del documento existente: {error.document_id}"
        )

    except Exception:
        logger.exception(
            "Error procesando el archivo recibido por Telegram."
        )

        await message.reply_text(
            "No pude procesar el documento.\n"
            "El archivo descargado se conserva en data/inbox/ "
            "para que puedas revisar el problema."
        )


async def post_init(application: Application) -> None:
    """Registra los comandos del bot en Telegram."""

    await application.bot.set_my_commands(
        [
            BotCommand("start", "Iniciar LocalDoc AI"),
            BotCommand("ayuda", "Ver funcionalidades"),
            BotCommand("reset", "Reiniciar conversación"),
        ]
    )


async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    logger.error(
        "Error no controlado en Telegram.",
        exc_info=context.error,
    )


def main() -> None:
    """Punto de entrada del bot."""

    token = settings.telegram_bot_token

    if not token:
        raise RuntimeError(
            "Falta TELEGRAM_BOT_TOKEN en el archivo .env."
        )

    if not settings.allowed_telegram_user_ids:
        raise RuntimeError(
            "TELEGRAM_ALLOWED_USER_IDS está vacío. "
            "Configurá al menos un ID autorizado."
        )

    application = (
        Application.builder()
        .token(token)
        .concurrent_updates(1)
        .post_init(post_init)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("ayuda", help_command)
    )

    application.add_handler(
        CommandHandler("reset", reset_command)
    )

    application.add_handler(
        MessageHandler(
            filters.Document.ALL,
            handle_document,
        )
    )

    application.add_handler(
        MessageHandler(
            filters.PHOTO,
            handle_photo,
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text,
        )
    )

    application.add_error_handler(error_handler)

    logger.info("Iniciando LocalDoc AI Telegram Bot...")

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    main()
