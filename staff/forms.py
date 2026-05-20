from django import forms
from django.utils import timezone

from comunicacion.models import Comunicado, Grado, Materia, TIPO_COMUNICADO_CHOICES


class ComunicadoForm(forms.ModelForm):
    """
    Form para crear/editar comunicados desde el panel staff.
    El queryset de grados/materias se restringe en init segun el perfil.
    """

    fecha_publicacion = forms.DateTimeField(
        required=False,
        input_formats=['%Y-%m-%dT%H:%M'],
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
    )

    class Meta:
        model = Comunicado
        fields = [
            'titulo', 'contenido', 'tipo',
            'grados', 'materia',
            'fecha_vencimiento',
            'fijado', 'urgente', 'activo',
            'archivo_adjunto',
            'ocultar_al_vencer',
        ]
        widgets = {
            'fecha_vencimiento': forms.DateInput(attrs={'type': 'date'}),
            'contenido': forms.Textarea(attrs={'rows': 8}),
        }

    def __init__(self, *args, perfil_docente=None, es_directivo=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.perfil_docente = perfil_docente
        self.es_directivo = es_directivo

        # Restringir grados/materias para docentes comunes
        if not es_directivo and perfil_docente is not None:
            asignaciones = perfil_docente.asignaciones.all()
            grados_ids = list(asignaciones.values_list('grado_id', flat=True).distinct())
            materias_ids = list(asignaciones.values_list('materia_id', flat=True).distinct())
            self.fields['grados'].queryset = Grado.objects.filter(id__in=grados_ids, activo=True)
            self.fields['materia'].queryset = Materia.objects.filter(id__in=materias_ids)
            self.fields['materia'].help_text = 'Solo podes elegir entre tus materias asignadas.'
        else:
            self.fields['grados'].queryset = Grado.objects.filter(activo=True).order_by('orden', 'nombre')
            self.fields['materia'].queryset = Materia.objects.all().order_by('nombre')
            self.fields['materia'].help_text = 'Deja vacio para "General del aula" (solo preceptores/directivos).'

        # Default razonable para fecha_publicacion
        if self.instance.pk and self.instance.fecha_publicacion and not self.initial.get('fecha_publicacion'):
            self.initial['fecha_publicacion'] = timezone.localtime(self.instance.fecha_publicacion)
        elif not self.instance.pk and not self.initial.get('fecha_publicacion'):
            self.initial['fecha_publicacion'] = timezone.now()

    def clean(self):
        cleaned = super().clean()
        materia = cleaned.get('materia')
        # Solo preceptor/directivo puede dejar materia vacia (= general del aula)
        if materia is None and not self.es_directivo:
            self.add_error('materia', 'Como docente debes seleccionar una materia. Solo preceptores/directivos pueden crear comunicados generales.')
        return cleaned


from comunicacion.models import Galeria


class GaleriaForm(forms.ModelForm):
    """Form para crear/editar galerias desde el panel staff."""

    class Meta:
        model = Galeria
        fields = ['titulo', 'descripcion', 'fecha_evento', 'grados', 'activa']
        widgets = {
            'fecha_evento': forms.DateInput(attrs={'type': 'date'}),
            'descripcion': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, perfil_docente=None, es_directivo=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.perfil_docente = perfil_docente
        self.es_directivo = es_directivo

        if not es_directivo and perfil_docente is not None:
            asignaciones = perfil_docente.asignaciones.all()
            grados_ids = list(asignaciones.values_list('grado_id', flat=True).distinct())
            self.fields['grados'].queryset = Grado.objects.filter(id__in=grados_ids, activo=True)
        else:
            self.fields['grados'].queryset = Grado.objects.filter(activo=True).order_by('orden', 'nombre')
