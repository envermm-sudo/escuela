"""
Reconvierte a .webp todas las fotos de docentes que NO sean .webp.
Útil después de cambios en la lógica de conversión, o cuando hay fotos viejas.
"""
import os

from django.conf import settings
from django.core.management.base import BaseCommand

from comunicacion.models import PerfilDocente
from comunicacion.utils import convertir_a_webp


class Command(BaseCommand):
    help = 'Reconvierte a .webp las fotos de docentes que estén en formato JPEG/PNG.'

    def handle(self, *args, **options):
        total = 0
        convertidos = 0
        errores = 0
        ya_webp = 0

        for pd in PerfilDocente.objects.exclude(foto='').exclude(foto=None):
            total += 1
            ruta_actual = pd.foto.name if pd.foto else ''
            self.stdout.write(f'Procesando: {pd.user.username} -> {ruta_actual}')

            if ruta_actual.lower().endswith('.webp'):
                self.stdout.write(self.style.SUCCESS('  Ya es webp, salteando.'))
                ya_webp += 1
                continue

            ruta_completa = os.path.join(settings.MEDIA_ROOT, ruta_actual)
            if not os.path.isfile(ruta_completa):
                self.stdout.write(self.style.WARNING(f'  Archivo no existe en disco: {ruta_completa}'))
                errores += 1
                continue

            try:
                with open(ruta_completa, 'rb') as f:
                    webp_file = convertir_a_webp(f, max_size=(600, 600), calidad=85)

                if webp_file:
                    pd.foto.save(webp_file.name, webp_file, save=True)
                    self.stdout.write(self.style.SUCCESS(f'  Convertido a {pd.foto.name}'))
                    convertidos += 1

                    # Eliminar el archivo viejo si tiene nombre distinto
                    if os.path.isfile(ruta_completa) and pd.foto.name != ruta_actual:
                        try:
                            os.remove(ruta_completa)
                            self.stdout.write('  Archivo viejo eliminado.')
                        except OSError:
                            pass
                else:
                    self.stdout.write(self.style.ERROR('  La conversión devolvió None.'))
                    errores += 1

            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  Error: {e}'))
                errores += 1

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Total: {total} | Convertidos: {convertidos} | Ya eran webp: {ya_webp} | Errores: {errores}'
        ))
