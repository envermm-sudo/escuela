from django.db import migrations


def crear_hijo_generico_por_padre(apps, schema_editor):
    """
    Por cada PerfilPadre que tenga hijos_grados cargados, crear un HijoPadre
    genérico llamado 'Hijo/a' por cada grado. Después el padre los edita en /mi-cuenta/.
    """
    PerfilPadre = apps.get_model('comunicacion', 'PerfilPadre')
    HijoPadre = apps.get_model('comunicacion', 'HijoPadre')

    for perfil in PerfilPadre.objects.all():
        grados_existentes = list(perfil.hijos_grados.all())
        if not grados_existentes:
            continue
        # Si ya tiene hijos cargados, no duplicar
        if perfil.hijos.exists():
            continue
        for grado in grados_existentes:
            HijoPadre.objects.create(
                padre=perfil,
                nombre='Hijo/a',
                grado=grado,
            )


def revertir(apps, schema_editor):
    HijoPadre = apps.get_model('comunicacion', 'HijoPadre')
    HijoPadre.objects.all().delete()


class Migration(migrations.Migration):

    # IMPORTANTE: Si makemigrations genera un nombre distinto para la 0008,
    # editar la línea de dependencies con el nombre real antes de correr migrate.
    dependencies = [
        ('comunicacion', '0008_perfilpadre_foto_perfilpadre_tipo_notificacion_and_more'),
    ]

    operations = [
        migrations.RunPython(crear_hijo_generico_por_padre, revertir),
    ]
