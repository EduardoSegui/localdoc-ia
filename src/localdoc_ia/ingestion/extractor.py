
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pymupdf
from PIL import Image, UnidentifiedImageError

from localdoc_ia.ingestion.ocr import ocr_image


ExtractionMethod = Literal["text", "ocr", "mixed"]


@dataclass
class ExtractedPage:
    """Resultado de extracción de una página."""

    page_number: int
    method: Literal["text", "ocr"]
    text: str


@dataclass
class ExtractionResult:
    """Resultado completo de extracción de un documento."""

    source_path: str
    file_type: str
    method: ExtractionMethod
    page_count: int
    text: str
    pages: list[ExtractedPage]


SUPPORTED_IMAGE_FORMATS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".tif",
    ".tiff",
    ".bmp",
    ".webp",
}


def has_usable_text(
    text: str,
    minimum_chars: int = 30,
) -> bool:
    """
    Determina si una página tiene suficiente texto seleccionable.

    Evita usar OCR cuando el PDF ya tiene una capa de texto útil.
    """

    normalized_text = " ".join(text.split())

    alphanumeric_chars = sum(
        character.isalnum()
        for character in normalized_text
    )

    return alphanumeric_chars >= minimum_chars


def classify_method(pages: list[ExtractedPage]) -> ExtractionMethod:
    """Determina el método utilizado en todo el documento."""

    methods = {page.method for page in pages}

    if methods == {"text"}:
        return "text"

    if methods == {"ocr"}:
        return "ocr"

    return "mixed"


def build_result(
    source_path: Path,
    file_type: str,
    pages: list[ExtractedPage],
) -> ExtractionResult:
    """Construye el resultado final del procesamiento."""

    full_text = "\n\n".join(
        f"--- Página {page.page_number} "
        f"(método: {page.method}) ---\n"
        f"{page.text}"
        for page in pages
    )

    return ExtractionResult(
        source_path=str(source_path.resolve()),
        file_type=file_type,
        method=classify_method(pages),
        page_count=len(pages),
        text=full_text,
        pages=pages,
    )


def extract_pdf(
    file_path: Path,
    dpi: int = 300,
    lang: str = "spa",
    minimum_text_chars: int = 30,
) -> ExtractionResult:
    """
    Extrae el texto de un PDF.

    Usa PyMuPDF cuando la página contiene texto seleccionable.
    Usa Tesseract cuando la página necesita OCR.
    """

    extracted_pages: list[ExtractedPage] = []

    try:
        with pymupdf.open(str(file_path)) as pdf:

            if pdf.needs_pass:
                raise ValueError(
                    f"El PDF está protegido con contraseña: {file_path.name}"
                )

            if len(pdf) == 0:
                raise ValueError(
                    f"El PDF no contiene páginas: {file_path.name}"
                )

            for page_index, page in enumerate(pdf):

                page_number = page_index + 1

                # Intentar primero extraer texto nativo
                native_text = page.get_text("text", sort=True).strip()

                if has_usable_text(
                    native_text,
                    minimum_chars=minimum_text_chars,
                ):
                    extracted_pages.append(
                        ExtractedPage(
                            page_number=page_number,
                            method="text",
                            text=native_text,
                        )
                    )

                    continue

                # Si no hay texto suficiente, convertir la página
                # del PDF en una imagen para aplicar OCR.
                pixmap = page.get_pixmap(
                    dpi=dpi,
                    colorspace=pymupdf.csRGB,
                    alpha=False,
                )

                page_image = Image.frombytes(
                    "RGB",
                    (pixmap.width, pixmap.height),
                    pixmap.samples,
                )

                try:
                    recognized_text = ocr_image(
                        page_image,
                        lang=lang,
                    )
                finally:
                    page_image.close()

                extracted_pages.append(
                    ExtractedPage(
                        page_number=page_number,
                        method="ocr",
                        text=recognized_text,
                    )
                )

    except Exception as error:
        raise RuntimeError(
            f"Error procesando el PDF '{file_path.name}': {error}"
        ) from error

    return build_result(
        source_path=file_path,
        file_type="pdf",
        pages=extracted_pages,
    )


def extract_image(
    file_path: Path,
    lang: str = "spa",
) -> ExtractionResult:
    """Extrae el texto de una imagen utilizando OCR."""

    try:
        with Image.open(file_path) as image:
            recognized_text = ocr_image(
                image,
                lang=lang,
            )

    except (UnidentifiedImageError, OSError) as error:
        raise RuntimeError(
            f"No se pudo abrir la imagen '{file_path.name}': {error}"
        ) from error

    page = ExtractedPage(
        page_number=1,
        method="ocr",
        text=recognized_text,
    )

    return build_result(
        source_path=file_path,
        file_type="image",
        pages=[page],
    )


def extract_document(
    file_path: str | Path,
    dpi: int = 300,
    lang: str = "spa",
) -> ExtractionResult:
    """
    Punto de entrada único para procesar documentos.

    Detecta el formato y deriva al extractor correspondiente.
    """

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(
            f"No existe el archivo: {path}"
        )

    if not path.is_file():
        raise ValueError(
            f"La ruta no corresponde a un archivo: {path}"
        )

    extension = path.suffix.lower()

    if extension == ".pdf":
        return extract_pdf(
            file_path=path,
            dpi=dpi,
            lang=lang,
        )

    if extension in SUPPORTED_IMAGE_FORMATS:
        return extract_image(
            file_path=path,
            lang=lang,
        )

    raise ValueError(
        f"Formato no soportado: {extension}. "
        "Formatos admitidos: PDF, JPG, JPEG, PNG, TIFF, BMP y WEBP."
    )
