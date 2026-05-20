"""Recalcula el orden de los grados existentes con la nueva fórmula correlativa."""
import re

from django.db import migrations


def recalcular_orden(apps, schema_editor):
    Grado = apps.get_model('comunicacion', 'Grado')
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
            g.orden = nuevo_orden
            g.save(update_fields=['orden'])


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('comunicacion', '0005_comunicado_es_institucional'),
    ]

    operations = [
        migrations.RunPython(recalcular_orden, reverse_noop),
    ]
