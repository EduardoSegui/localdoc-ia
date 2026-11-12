
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pymupdf
from PIL import Image, UnidentifiedImageError

from localdoc_ia.config import settings


ExtractionMethod = Literal["text", "ocr", "mixed", "vision"]
PageExtractionMethod = Literal["text", "ocr", "vision"]


@dataclass
class ExtractedPage:
    """Resultado de extracción de una página."""

    page_number: int
    method: PageExtractionMethod
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

    Evita usar el modelo visual cuando el PDF ya tiene texto útil.
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

    # Cuando alguna página no posee texto seleccionable, todo el PDF se
    # analiza con el VLM para preservar el contexto entre sus páginas.
    if "vision" in methods:
        return "vision"

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
        if page.text.strip()
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
    minimum_text_chars: int = 30,
) -> ExtractionResult:
    """
    Inspecciona el texto nativo de un PDF.

    Si una página no tiene texto seleccionable suficiente, se marca para
    extracción visual. El renderizado y el análisis VLM se realizan luego en
    el servicio documental, donde se envían todas las páginas juntas.
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

                extracted_pages.append(
                    ExtractedPage(
                        page_number=page_number,
                        method="vision",
                        text="",
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


def extract_image(file_path: Path) -> ExtractionResult:
    """Valida una imagen y la marca para extracción directa con VLM."""

    try:
        with Image.open(file_path) as image:
            image.verify()

    except (UnidentifiedImageError, OSError) as error:
        raise RuntimeError(
            f"No se pudo abrir la imagen '{file_path.name}': {error}"
        ) from error

    page = ExtractedPage(
        page_number=1,
        method="vision",
        text="",
    )

    return build_result(
        source_path=file_path,
        file_type="image",
        pages=[page],
    )


def render_pdf_pages(
    file_path: str | Path,
    output_dir: str | Path,
    dpi: int | None = None,
) -> list[Path]:
    """Renderiza todas las páginas de un PDF en PNG para el modelo visual."""

    path = Path(file_path)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    rendered_pages: list[Path] = []
    effective_dpi = dpi if dpi is not None else settings.ocr_dpi

    try:
        with pymupdf.open(str(path)) as pdf:

            if pdf.needs_pass:
                raise ValueError(
                    f"El PDF está protegido con contraseña: {path.name}"
                )

            if len(pdf) == 0:
                raise ValueError(
                    f"El PDF no contiene páginas: {path.name}"
                )

            for page_index, page in enumerate(pdf, start=1):
                pixmap = page.get_pixmap(
                    dpi=effective_dpi,
                    colorspace=pymupdf.csRGB,
                    alpha=False,
                )
                output_path = destination / f"pagina_{page_index:04d}.png"
                pixmap.save(str(output_path))
                rendered_pages.append(output_path)

    except Exception as error:
        raise RuntimeError(
            f"No se pudo renderizar el PDF '{path.name}': {error}"
        ) from error

    return rendered_pages


def extract_document(
    file_path: str | Path,
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
        # Los PDF sin texto pasan al VLM; el renderizado se realiza luego
        # en el servicio documental usando OCR_DPI.
        return extract_pdf(
            file_path=path,
        )

    if extension in SUPPORTED_IMAGE_FORMATS:
        return extract_image(
            file_path=path,
        )

    raise ValueError(
        f"Formato no soportado: {extension}. "
        "Formatos admitidos: PDF, JPG, JPEG, PNG, TIFF, BMP y WEBP."
    )
