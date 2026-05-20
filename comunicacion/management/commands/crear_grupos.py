from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from comunicacion.models import (
    Comunicado,
    FotoGaleria,
    Galeria,
    ImagenComunicado,
)


class Command(BaseCommand):
    help = 'Crea los grupos de usuarios (Docentes, Preceptores) con sus permisos.'

    PERMS_DOCENTE = [
        # Comunicado
        ('comunicado', ['add', 'change', 'delete', 'view']),
        # Galeria
        ('galeria', ['add', 'change', 'delete', 'view']),
        # Imagenes
        ('imagencomunicado', ['add', 'change', 'delete', 'view']),
        ('fotogaleria', ['add', 'change', 'delete', 'view']),
    ]

    def handle(self, *args, **options):
        # Grupo Docentes
        grupo_docentes, created = Group.objects.get_or_create(name='Docentes')
        if created:
            self.stdout.write(self.style.SUCCESS('Grupo "Docentes" creado.'))
        else:
            self.stdout.write('Grupo "Docentes" ya existia.')

        modelos = {
            'comunicado': Comunicado,
            'galeria': Galeria,
            'imagencomunicado': ImagenComunicado,
            'fotogaleria': FotoGaleria,
        }

        permisos_aplicados = 0
        for modelo_lower, acciones in self.PERMS_DOCENTE:
            modelo_cls = modelos[modelo_lower]
            ct = ContentType.objects.get_for_model(modelo_cls)
            for accion in acciones:
                codename = f'{accion}_{modelo_lower}'
                try:
                    perm = Permission.objects.get(codename=codename, content_type=ct)
                    grupo_docentes.permissions.add(perm)
                    permisos_aplicados += 1
                except Permission.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f'Permiso no encontrado: {codename}'))

        self.stdout.write(self.style.SUCCESS(
            f'{permisos_aplicados} permisos asignados al grupo "Docentes".'
        ))
