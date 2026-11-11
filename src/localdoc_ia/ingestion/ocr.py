from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import pytesseract


DEFAULT_OCR_LANG = "spa"
# --oem 3 usa el motor LSTM por defecto.
# --psm 4 es excelente para facturas porque asume columnas de texto de tamaño variable.
DEFAULT_OCR_CONFIG = "--oem 3 --psm 4"


def ocr_image(
    image: Image.Image,
    lang: str = DEFAULT_OCR_LANG,
    config: str = DEFAULT_OCR_CONFIG,
) -> str:
    """
    Reconoce el texto de una imagen utilizando Tesseract OCR con preprocesamiento avanzado.
    """

    # 1. Corregir la orientación según los metadatos EXIF
    prepared_image = ImageOps.exif_transpose(image)

    # 2. Escalar la imagen x2 (Tesseract lee mucho mejor en alta resolución)
    width, height = prepared_image.size
    prepared_image = prepared_image.resize(
        (width * 2, height * 2), 
        Image.Resampling.LANCZOS
    )

    # 3. Convertir a escala de grises
    prepared_image = ImageOps.grayscale(prepared_image)

    # 4. Aumentar el contraste drásticamente para separar letras del fondo
    enhancer = ImageEnhance.Contrast(prepared_image)
    prepared_image = enhancer.enhance(2.0)

    # 5. Aplicar filtro de nitidez para corregir fotos borrosas (como las de celular)
    prepared_image = prepared_image.filter(ImageFilter.SHARPEN)

    # 6. Binarización (Umbral). Todo lo más oscuro que 150 será negro (0), el resto blanco (255)
    # Esto elimina el fondo grisáceo y los patrones extraños de fotos a monitores
    prepared_image = prepared_image.point(lambda p: 255 if p > 150 else 0)

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