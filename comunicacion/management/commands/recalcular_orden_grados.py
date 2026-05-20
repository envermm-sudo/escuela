"""Recalcula el orden de todos los grados.
Orden correlativo: 1° Mañana, 1° Tarde, 1° Vespertino, 2° Mañana, ...
"""
import re

from django.core.management.base import BaseCommand

from comunicacion.models import Grado


class Command(BaseCommand):
    help = 'Recalcula el campo orden de todos los grados (correlativo por número, después por turno).'

    def handle(self, *args, **options):
        turno_offset = {'manana': 0, 'tarde': 1, 'vespertino': 2}

        for g in Grado.objects.all():
            numero = 99
            match = re.search(r'\d+', g.nombre)
            if match:
                try:
                    numero = int(match.group())
                except ValueError:
                    pass

            offset = turno_offset.get(g.turno, 9)
            nuevo_orden = numero * 10 + offset

            if g.orden != nuevo_orden:
                self.stdout.write(f'  {g.nombre} {g.turno}: {g.orden} → {nuevo_orden}')
                g.orden = nuevo_orden
                g.save(update_fields=['orden'])

        self.stdout.write(self.style.SUCCESS('Listo. Orden recalculado.'))
        self.stdout.write('')
        self.stdout.write('Listado final ordenado:')
        for g in Grado.objects.all().order_by('orden'):
            self.stdout.write(f'  {g.orden:>4} - {g.nombre} {g.get_turno_display()}')
