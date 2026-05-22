from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import Grado, Materia, PerfilPadre


class RegistroPadreForm(forms.Form):
    """Formulario público para que un padre se registre y elija los grados de sus hijos."""

    nombre = forms.CharField(
        max_length=80,
        label='Nombre y apellido',
        widget=forms.TextInput(attrs={'placeholder': 'Ej: María Pérez'})
    )
    email = forms.EmailField(
        label='Correo electrónico',
        widget=forms.EmailInput(attrs={'placeholder': 'tucorreo@ejemplo.com'})
    )
    password1 = forms.CharField(
        label='Contraseña',
        min_length=8,
        widget=forms.PasswordInput(attrs={'placeholder': 'Mínimo 8 caracteres'}),
        help_text='Al menos 8 caracteres.'
    )
    password2 = forms.CharField(
        label='Repetir contraseña',
        widget=forms.PasswordInput(attrs={'placeholder': 'Escribilo de nuevo'})
    )
    telefono = forms.CharField(
        max_length=30,
        required=False,
        label='Teléfono (opcional)',
        widget=forms.TextInput(attrs={'placeholder': 'Para contacto futuro'})
    )
    dni = forms.CharField(
        max_length=20,
        required=False,
        label='DNI (opcional)'
    )
    grados = forms.ModelMultipleChoiceField(
        queryset=Grado.objects.filter(activo=True).order_by('orden', 'nombre', 'turno'),
        label='Grados que seguís',
        help_text='Seleccioná los grados de tus hijos. Podés cambiarlo después.',
        widget=forms.CheckboxSelectMultiple
    )

    def clean_email(self):
        email = self.cleaned_data['email'].lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError(
                'Ya existe una cuenta con ese correo. Si la cuenta es tuya, iniciá sesión.'
            )
        return email

    def clean_password1(self):
        password = self.cleaned_data['password1']
        validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password1')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'Las contraseñas no coinciden.')
        return cleaned

    def save(self):
        data = self.cleaned_data
        # Generar username único a partir del email
        base_username = data['email'].split('@')[0][:30]
        username = base_username
        i = 1
        while User.objects.filter(username=username).exists():
            i += 1
            username = f'{base_username}{i}'[:30]

        # Separar nombre y apellido (best effort)
        partes = data['nombre'].strip().split(maxsplit=1)
        first_name = partes[0]
        last_name = partes[1] if len(partes) > 1 else ''

        user = User.objects.create_user(
            username=username,
            email=data['email'],
            password=data['password1'],
            first_name=first_name,
            last_name=last_name,
        )
        # Padres NO son staff
        user.is_staff = False
        user.save(update_fields=['is_staff'])

        perfil = PerfilPadre.objects.create(
            user=user,
            telefono=data.get('telefono', ''),
            dni=data.get('dni', ''),
        )
        # Crear un HijoPadre por cada grado elegido (sin nombre, es opcional)
        from .models import HijoPadre
        for grado in data['grados']:
            HijoPadre.objects.get_or_create(
                padre=perfil,
                grado=grado,
                defaults={'nombre': ''},
            )
        return user, perfil


class MisGradosForm(forms.Form):
    """OBSOLETO: la gestión de grados ahora se hace desde Mi cuenta (HijoPadre)."""

    grados = forms.ModelMultipleChoiceField(
        queryset=Grado.objects.filter(activo=True).order_by('orden', 'nombre', 'turno'),
        label='Grados que seguís',
        required=False,
        widget=forms.CheckboxSelectMultiple
    )


PALETA_COLORES = [
    ('#ef4444', 'Rojo'),
    ('#f97316', 'Naranja'),
    ('#eab308', 'Amarillo'),
    ('#22c55e', 'Verde'),
    ('#10b981', 'Esmeralda'),
    ('#06b6d4', 'Cian'),
    ('#3b82f6', 'Azul'),
    ('#6366f1', 'Indigo'),
    ('#8b5cf6', 'Violeta'),
    ('#ec4899', 'Rosa'),
    ('#64748b', 'Gris'),
    ('#0f172a', 'Negro'),
]


class PaletaColoresWidget(forms.Widget):
    """Widget que muestra una paleta visual de circulos clickeables."""
    template_name = 'comunicacion/widgets/paleta_colores.html'

    def __init__(self, attrs=None, paleta=None):
        super().__init__(attrs)
        self.paleta = paleta or PALETA_COLORES

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        ctx['paleta'] = self.paleta
        ctx['valor'] = value or ''
        return ctx


class MateriaAdminForm(forms.ModelForm):
    color = forms.CharField(
        required=False,
        widget=PaletaColoresWidget(),
        help_text='Toca un color de la paleta. Si no elegis ninguno, se asigna uno automatico.'
    )

    class Meta:
        model = Materia
        fields = ['nombre', 'color']
