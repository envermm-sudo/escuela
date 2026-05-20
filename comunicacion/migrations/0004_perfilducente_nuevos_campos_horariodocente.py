# Migración manual — agregar campos a PerfilDocente y crear HorarioDocente

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('comunicacion', '0003_comunicado_ocultar_al_vencer_materia_color'),
    ]

    operations = [
        # ── Nuevos campos en PerfilDocente ──────────────────────────────────
        migrations.AddField(
            model_name='perfildocente',
            name='titulo',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Título profesional. Ej: "Profesora de Matemáticas", "Lic. en Educación".',
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name='perfildocente',
            name='fecha_ingreso',
            field=models.DateField(
                blank=True,
                null=True,
                help_text='Fecha en que comenzó a trabajar en la institución.',
            ),
        ),
        migrations.AddField(
            model_name='perfildocente',
            name='observaciones',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Notas internas del director (no son visibles para el docente ni para padres).',
            ),
        ),
        # ── Actualizar verbose_name de PerfilDocente ─────────────────────────
        migrations.AlterModelOptions(
            name='perfildocente',
            options={
                'verbose_name': 'Docente',
                'verbose_name_plural': 'Docentes',
            },
        ),
        # ── Nuevo modelo HorarioDocente ──────────────────────────────────────
        migrations.CreateModel(
            name='HorarioDocente',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dia', models.CharField(
                    choices=[
                        ('lun', 'Lunes'),
                        ('mar', 'Martes'),
                        ('mie', 'Miércoles'),
                        ('jue', 'Jueves'),
                        ('vie', 'Viernes'),
                        ('sab', 'Sábado'),
                    ],
                    max_length=3,
                )),
                ('hora_inicio', models.TimeField()),
                ('hora_fin', models.TimeField()),
                ('aula', models.CharField(blank=True, default='', max_length=30)),
                ('asignacion', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='horarios',
                    to='comunicacion.asignaciondocente',
                )),
            ],
            options={
                'verbose_name': 'Horario',
                'verbose_name_plural': 'Horarios',
                'ordering': ['dia', 'hora_inicio'],
            },
        ),
    ]
