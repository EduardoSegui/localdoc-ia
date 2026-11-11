
from PIL import Image, ImageOps
import pytesseract


DEFAULT_OCR_LANG = "spa"
DEFAULT_OCR_CONFIG = "--oem 3 --psm 3"


def ocr_image(
    image: Image.Image,
    lang: str = DEFAULT_OCR_LANG,
    config: str = DEFAULT_OCR_CONFIG,
) -> str:
    """
    Reconoce el texto de una imagen utilizando Tesseract OCR.

    Args:
        image: Imagen PIL que contiene el documento.
        lang: Idioma utilizado por Tesseract.
        config: Configuración del motor OCR.

    Returns:
        Texto reconocido.
    """

    # Corregir la orientación según los metadatos EXIF
    prepared_image = ImageOps.exif_transpose(image)

    # Convertir a escala de grises
    prepared_image = ImageOps.grayscale(prepared_image)

    # Mejorar el contraste
    prepared_image = ImageOps.autocontrast(prepared_image)

    # Ejecutar el reconocimiento OCR
    extracted_text = pytesseract.image_to_string(
        prepared_image,
        lang=lang,
        config=config,
    )

    return extracted_text.strip()


def check_ocr_environment(lang: str = DEFAULT_OCR_LANG) -> dict:
    """
    Comprueba que Tesseract y el idioma solicitado estén disponibles.
    """

    version = str(pytesseract.get_tesseract_version())
    available_languages = pytesseract.get_languages(config="")

    if lang not in available_languages:
        raise RuntimeError(
            f"No está instalado el idioma '{lang}'. "
            f"Idiomas disponibles: {available_languages}"
        )

    return {
        "tesseract_version": version,
        "language": lang,
        "available_languages": available_languages,
    }
