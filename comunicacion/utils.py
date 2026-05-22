"""Utilidades de procesamiento de imágenes."""
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image

# Activar soporte para imágenes HEIC/HEIF (fotos de iPhone)
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass


def convertir_a_webp(imagen_field, calidad=80, max_size=None):
    """
    Convierte un ImageField/FileField/UploadedFile a formato WEBP.
    Parámetros:
    - imagen_field: el campo o archivo subido.
    - calidad: 0-100 (default 80).
    - max_size: tupla (ancho, alto) — si la imagen excede, se redimensiona
                manteniendo aspect ratio. Por defecto no redimensiona.

    Devuelve un ContentFile listo para asignar al campo, o None si la entrada
    está vacía. NO lanza excepciones por formatos raros: las atrapa y devuelve None.
    """
    if not imagen_field:
        return None

    try:
        # Si es un FieldFile, abrir desde el archivo. Si es un UploadedFile, leer su .file.
        if hasattr(imagen_field, 'open'):
            try:
                imagen_field.open('rb')
            except Exception:
                pass

        img = Image.open(imagen_field)

        # Convertir a RGB (WEBP no soporta paleta indexada bien)
        if img.mode in ('RGBA', 'LA', 'P'):
            # Para fotos con transparencia, fondo blanco
            fondo = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            fondo.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = fondo
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # Redimensionar si excede max_size
        if max_size:
            img.thumbnail(max_size, Image.LANCZOS)

        output = BytesIO()
        img.save(output, format='WEBP', quality=calidad, method=6)
        output.seek(0)

        # Generar nombre seguro: solo el basename original sin extensión + .webp
        try:
            nombre_original = imagen_field.name
        except AttributeError:
            nombre_original = 'imagen'
        # Quitar la extensión y los caracteres problemáticos del nombre
        import os
        import re
        base = os.path.basename(nombre_original).rsplit('.', 1)[0]
        # Reemplazar espacios y caracteres no ASCII por guion bajo
        base_limpio = re.sub(r'[^a-zA-Z0-9_-]', '_', base)[:60]
        if not base_limpio:
            base_limpio = 'imagen'
        nombre_webp = f'{base_limpio}.webp'

        return ContentFile(output.read(), name=nombre_webp)
    except Exception as e:
        # Loggear pero no romper
        import logging
        logging.getLogger(__name__).exception(f'Error convirtiendo imagen a webp: {e}')
        return None
