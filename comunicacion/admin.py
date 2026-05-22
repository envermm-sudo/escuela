from django import forms
from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models
from django.shortcuts import redirect, render
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from .audit import registrar_audit
from .forms import MateriaAdminForm
from .models import (
    AsignacionDocente,
    AuditLog,
    Comunicado,
    ConfiguracionPortal,
    FotoGaleria,
    Galeria,
    Grado,
    HorarioDocente,
    ImagenComunicado,
    Materia,
    PerfilDocente,
    PerfilPadre,
)


# =================================================================
# Overrides comunes para inputs compactos
# =================================================================
COMPACT_TEXTAREA = forms.Textarea(attrs={'rows': 6, 'style': 'max-width: 100%;'})
COMPACT_TEXTAREA_SMALL = forms.Textarea(attrs={'rows': 3, 'style': 'max-width: 100%;'})
COMMON_FORMFIELD_OVERRIDES = {
    models.TextField: {'widget': COMPACT_TEXTAREA},
}


# =================================================================
# Grado
# =================================================================
@admin.register(Grado)
class GradoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'turno', 'orden', 'activo')
    list_filter = ('turno', 'activo')
    list_editable = ('orden', 'activo')
    search_fields = ('nombre',)
    prepopulated_fields = {'slug': ('nombre', 'turno')}
    fieldsets = (
        ('Datos del grado', {
            'fields': ('nombre', 'turno', 'slug', 'orden', 'activo'),
        }),
    )


# =================================================================
# Materia
# =================================================================
@admin.register(Materia)
class MateriaAdmin(admin.ModelAdmin):
    form = MateriaAdminForm
    list_display = ('nombre', 'mostrar_color')
    search_fields = ('nombre',)

    def mostrar_color(self, obj):
        from django.utils.html import format_html
        color = obj.get_color()
        return format_html(
            '<span style="display:inline-block;width:60px;height:20px;background:{};border-radius:4px;border:1px solid #ddd;vertical-align:middle;"></span> <code style="margin-left:6px;">{}</code>',
            color, color or '(auto)'
        )
    mostrar_color.short_description = 'Color'


# =================================================================
# PerfilDocente — Form unificado User + PerfilDocente
# =================================================================
class PerfilDocenteAdminForm(forms.ModelForm):
    """
    Form que en una sola pantalla edita: User (email/nombre/apellido/password)
    + PerfilDocente (rol/dni/teléfono/foto/título/observaciones).
    """
    email = forms.EmailField(
        label='Email (será el usuario para iniciar sesión) *',
        required=True,
        help_text='Tiene que ser un email válido. Lo va a usar el docente para entrar al sistema y para recuperar contraseña.'
    )
    nombre = forms.CharField(
        max_length=150,
        required=True,
        label='Nombre *',
        help_text='Es el nombre que aparece en los comunicados.'
    )
    apellido = forms.CharField(
        max_length=150,
        required=True,
        label='Apellido *',
    )
    password_nueva = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        label='Nueva contraseña',
        help_text='Solo completar si querés cambiar la contraseña. Dejar vacío para mantener la actual.',
        min_length=6,
    )

    class Meta:
        model = PerfilDocente
        fields = (
            'email', 'nombre', 'apellido', 'password_nueva',
            'rol', 'titulo', 'foto',
            'dni', 'telefono', 'fecha_ingreso',
            'observaciones',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.user_id:
            self.fields['email'].initial = self.instance.user.email or self.instance.user.username
            self.fields['nombre'].initial = self.instance.user.first_name
            self.fields['apellido'].initial = self.instance.user.last_name

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip().lower()
        try:
            validate_email(email)
        except ValidationError:
            raise ValidationError('Ingresá un email válido (ej. nombre@escuela.com).')
        qs = User.objects.filter(username__iexact=email)
        if self.instance and self.instance.pk and self.instance.user_id:
            qs = qs.exclude(pk=self.instance.user_id)
        if qs.exists():
            raise ValidationError('Ya existe un usuario con ese email.')
        return email

    def save(self, commit=True):
        perfil = super().save(commit=False)
        email = self.cleaned_data['email']
        nombre = self.cleaned_data['nombre'].strip()
        apellido = self.cleaned_data['apellido'].strip()
        password = self.cleaned_data.get('password_nueva') or ''

        if perfil.pk and perfil.user_id:
            user = perfil.user
        else:
            user = User()

        user.username = email
        user.email = email
        user.first_name = nombre
        user.last_name = apellido
        user.is_staff = True
        user.is_active = True

        if password:
            user.set_password(password)
        elif not user.pk:
            user.set_password(email)

        user.save()
        perfil.user = user
        if commit:
            perfil.save()
        return perfil


class HorarioDocenteInline(admin.TabularInline):
    model = HorarioDocente
    extra = 0
    fields = ('dia', 'hora_inicio', 'hora_fin', 'aula')


@admin.register(PerfilDocente)
class PerfilDocenteAdmin(admin.ModelAdmin):
    form = PerfilDocenteAdminForm
    list_display = ('mini_foto', 'mostrar_nombre_completo', 'rol', 'titulo', 'cant_asignaciones', 'mostrar_email')
    list_display_links = ('mostrar_nombre_completo',)
    list_filter = ('rol',)
    search_fields = ('user__first_name', 'user__last_name', 'user__email', 'user__username', 'dni', 'titulo')
    readonly_fields = ('preview_foto_grande', 'link_matriz_asignaciones')
    inlines = []
    fieldsets = (
        ('🪪 Identidad y acceso', {
            'fields': (
                'preview_foto_grande',
                'foto',
                'nombre', 'apellido',
                'email',
                'password_nueva',
            ),
            'description': 'El email es lo que el docente usa para iniciar sesión. Si dejás la contraseña vacía al crear, será el mismo email (avísale para que la cambie en su primer ingreso).',
        }),
        ('🎓 Datos profesionales', {
            'fields': ('rol', 'titulo', 'fecha_ingreso'),
        }),
        ('📞 Datos personales', {
            'fields': ('dni', 'telefono'),
            'classes': ('collapse',),
        }),
        ('📝 Observaciones internas', {
            'fields': ('observaciones',),
            'classes': ('collapse',),
            'description': 'Notas privadas del director. NO son visibles para el docente ni para padres.',
        }),
        ('🎓 Asignaciones (matriz)', {
            'fields': ('link_matriz_asignaciones',),
            'description': 'Las asignaciones se cargan en una pantalla separada con una matriz de checkboxes.',
        }),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                '<int:object_id>/asignaciones-matriz/',
                self.admin_site.admin_view(self.matriz_asignaciones_view),
                name='comunicacion_perfildocente_matriz',
            ),
        ]
        return custom + urls

    def matriz_asignaciones_view(self, request, object_id):
        """Vista de matriz: Materias (cols) × Grados (filas) con checkboxes."""
        perfil = PerfilDocente.objects.get(pk=object_id)
        grados = list(Grado.objects.filter(activo=True).order_by('orden', 'nombre', 'turno'))
        materias = list(Materia.objects.all().order_by('nombre'))

        if request.method == 'POST':
            seleccionadas = set()
            for clave in request.POST:
                if clave.startswith('cell_g') and '_m' in clave:
                    try:
                        g_part, m_part = clave[len('cell_'):].split('_m', 1)
                        grado_id = int(g_part[1:])
                        materia_id = int(m_part)
                        seleccionadas.add((grado_id, materia_id))
                    except (ValueError, IndexError):
                        continue

            actuales = set(
                AsignacionDocente.objects
                .filter(docente=perfil)
                .values_list('grado_id', 'materia_id')
            )

            a_crear = seleccionadas - actuales
            a_borrar = actuales - seleccionadas

            AsignacionDocente.objects.bulk_create([
                AsignacionDocente(docente=perfil, grado_id=grado_id, materia_id=materia_id)
                for (grado_id, materia_id) in a_crear
            ])

            if a_borrar:
                for (grado_id, materia_id) in a_borrar:
                    AsignacionDocente.objects.filter(
                        docente=perfil,
                        grado_id=grado_id,
                        materia_id=materia_id,
                    ).delete()

            messages.success(
                request,
                f'Asignaciones actualizadas: +{len(a_crear)} agregadas, -{len(a_borrar)} eliminadas.'
            )
            return redirect('admin:comunicacion_perfildocente_matriz', object_id=object_id)

        actuales = set(
            AsignacionDocente.objects
            .filter(docente=perfil)
            .values_list('grado_id', 'materia_id')
        )
        matriz_filas = []
        for grado in grados:
            celdas = []
            for materia in materias:
                celdas.append({
                    'materia_id': materia.id,
                    'asignada': (grado.id, materia.id) in actuales,
                    'clave': f'cell_g{grado.id}_m{materia.id}',
                })
            matriz_filas.append({
                'grado': grado,
                'celdas': celdas,
            })

        contexto = {
            **self.admin_site.each_context(request),
            'title': f'Asignaciones de {perfil.user.first_name} {perfil.user.last_name}',
            'perfil': perfil,
            'grados': grados,
            'materias': materias,
            'filas': matriz_filas,
            'opts': self.model._meta,
            'has_view_permission': True,
            'original': perfil,
        }
        return TemplateResponse(request, 'admin/comunicacion/matriz_asignaciones.html', contexto)

    def mini_foto(self, obj):
        if obj.foto:
            return format_html(
                '<img src="{}" style="height:42px;width:42px;border-radius:50%;object-fit:cover;border:2px solid #e5e7eb;" />',
                obj.foto.url
            )
        iniciales = ''
        if obj.user:
            iniciales = (obj.user.first_name[:1] + obj.user.last_name[:1]).upper() or '?'
        return format_html(
            '<span style="display:inline-flex;align-items:center;justify-content:center;height:42px;width:42px;border-radius:50%;background:#6366f1;color:white;font-weight:bold;font-size:13px;">{}</span>',
            iniciales or '?'
        )
    mini_foto.short_description = 'Foto'

    def mostrar_nombre_completo(self, obj):
        if not obj.user:
            return '(sin usuario)'
        nombre = obj.user.first_name or ''
        apellido = obj.user.last_name or ''
        completo = f'{nombre} {apellido}'.strip()
        return completo or obj.user.username
    mostrar_nombre_completo.short_description = 'Docente'
    mostrar_nombre_completo.admin_order_field = 'user__last_name'

    def mostrar_email(self, obj):
        return obj.user.email if obj.user else '—'
    mostrar_email.short_description = 'Email'

    def cant_asignaciones(self, obj):
        return obj.asignaciones.count()
    cant_asignaciones.short_description = 'Asignaciones'

    def preview_foto_grande(self, obj):
        if obj and obj.pk and obj.foto:
            return format_html(
                '<img src="{}" alt="Foto" style="height:160px;width:160px;border-radius:50%;object-fit:cover;border:4px solid #e5e7eb;box-shadow:0 4px 12px rgba(0,0,0,0.10);" />',
                obj.foto.url
            )
        return format_html(
            '<div style="height:160px;width:160px;border-radius:50%;background:#f3f4f6;border:4px dashed #d1d5db;display:flex;align-items:center;justify-content:center;color:#9ca3af;">Sin foto</div>'
        )
    preview_foto_grande.short_description = 'Vista previa'

    def link_matriz_asignaciones(self, obj):
        if not obj or not obj.pk:
            return format_html(
                '<em style="color:#6b7280;">Primero guardá el docente. '
                'Después podrás cargar sus asignaciones desde la matriz.</em>'
            )
        url = reverse('admin:comunicacion_perfildocente_matriz', args=[obj.pk])
        cantidad = obj.asignaciones.count()
        return format_html(
            '<a href="{}" class="button" style="display:inline-flex;align-items:center;gap:6px;'
            'padding:8px 16px;background:#6366f1;color:white;border-radius:6px;'
            'text-decoration:none;font-weight:600;">'
            '🎓 Editar matriz de asignaciones <span style="background:rgba(255,255,255,0.25);'
            'padding:2px 8px;border-radius:10px;font-size:12px;">{} cargadas</span></a>',
            url,
            cantidad,
        )
    link_matriz_asignaciones.short_description = 'Asignaciones'

    def response_add(self, request, obj, post_url_continue=None):
        """Después de crear un docente nuevo, redirigir directo a la matriz de asignaciones."""
        if "_addanother" not in request.POST and "_continue" not in request.POST:
            messages.success(
                request,
                f'Docente "{obj.user.first_name} {obj.user.last_name}" creado. '
                f'Ahora cargá sus materias y grados en la matriz.'
            )
            return redirect('admin:comunicacion_perfildocente_matriz', object_id=obj.pk)
        return super().response_add(request, obj, post_url_continue)


# =================================================================
# HorarioDocente
# =================================================================
@admin.register(HorarioDocente)
class HorarioDocenteAdmin(admin.ModelAdmin):
    list_display = ('asignacion', 'dia', 'hora_inicio', 'hora_fin', 'aula')
    list_filter = ('dia', 'asignacion__grado', 'asignacion__materia')
    search_fields = ('asignacion__docente__user__first_name', 'asignacion__docente__user__last_name', 'aula')
    autocomplete_fields = ('asignacion',)


# =================================================================
# AsignacionDocente (registro independiente, además de inline)
# =================================================================
@admin.register(AsignacionDocente)
class AsignacionDocenteAdmin(admin.ModelAdmin):
    list_display = ('docente', 'grado', 'materia', 'cant_horarios')
    list_filter = ('grado', 'materia')
    search_fields = (
        'docente__user__first_name',
        'docente__user__last_name',
        'grado__nombre',
        'materia__nombre',
    )
    autocomplete_fields = ('docente', 'grado', 'materia')
    inlines = [HorarioDocenteInline]

    def cant_horarios(self, obj):
        return obj.horarios.count()
    cant_horarios.short_description = 'Horarios cargados'


# =================================================================
# Comunicado
# =================================================================
class ImagenComunicadoInline(admin.TabularInline):
    model = ImagenComunicado
    extra = 1
    max_num = 10
    fields = ('imagen',)
    verbose_name = 'Imagen'
    verbose_name_plural = '🖼️ Imágenes adjuntas (máximo 10)'
    classes = ('collapse',)


@admin.register(Comunicado)
class ComunicadoAdmin(admin.ModelAdmin):
    list_display = (
        'titulo', 'tipo', 'fecha_publicacion', 'autor',
        'fijado', 'urgente', 'vistas', 'activo', 'creado_por', 'fecha_modificacion',
    )
    list_filter = ('tipo', 'fijado', 'urgente', 'activo', 'grados', 'materia')
    list_editable = ('fijado', 'urgente', 'activo')
    search_fields = ('titulo', 'contenido')
    date_hierarchy = 'fecha_publicacion'
    autocomplete_fields = ('materia',)
    filter_horizontal = ('grados',)
    readonly_fields = ('fecha_publicacion', 'autor', 'vistas', 'creado_por', 'modificado_por', 'fecha_modificacion')
    inlines = [ImagenComunicadoInline]
    formfield_overrides = COMMON_FORMFIELD_OVERRIDES
    fieldsets = (
        ('📝 Contenido', {
            'fields': ('titulo', 'contenido', 'archivo_adjunto'),
        }),
        ('🎯 Clasificación', {
            'fields': ('tipo', 'grados', 'materia'),
        }),
        ('⚙️ Opciones', {
            'fields': (
                ('fijado', 'urgente', 'activo'),
                'fecha_publicacion',
                'fecha_vencimiento',
                'ocultar_al_vencer',
            ),
            'description': 'Los comunicados fijados aparecen siempre arriba. Los urgentes muestran un badge rojo.',
        }),
        ('📊 Auditoría', {
            'fields': ('autor', 'creado_por', 'modificado_por', 'fecha_modificacion', 'vistas'),
            'classes': ('collapse',),
            'description': 'Datos de auditoría. El autor se asigna automáticamente al usuario que crea el comunicado.',
        }),
    )

    def save_model(self, request, obj, form, change):
        if not change:
            # Es nuevo: asignar autor + creado_por automáticamente
            obj.autor = request.user
            obj.creado_por = request.user
            obj.modificado_por = request.user
        super().save_model(request, obj, form, change)
        registrar_audit(
            request.user,
            'editar' if change else 'crear',
            obj,
            cambios={'campos_modificados': list(form.changed_data)} if change else None,
        )

    def add_view(self, request, form_url='', extra_context=None):
        return redirect('staff:comunicado_crear')

    def delete_model(self, request, obj):
        registrar_audit(request.user, 'eliminar', obj)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            registrar_audit(request.user, 'eliminar', obj)
        super().delete_queryset(request, queryset)


# =================================================================
# Galería
# =================================================================
class FotoGaleriaInline(admin.TabularInline):
    model = FotoGaleria
    extra = 1
    max_num = 30
    fields = ('imagen', 'descripcion', 'orden')
    verbose_name = 'Foto'
    verbose_name_plural = '📷 Fotos de la galería (máximo 30)'
    classes = ('collapse',)


@admin.register(Galeria)
class GaleriaAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'fecha_evento', 'fecha_publicacion', 'autor', 'activa')
    list_filter = ('activa', 'grados', 'fecha_evento')
    list_editable = ('activa',)
    search_fields = ('titulo', 'descripcion')
    date_hierarchy = 'fecha_evento'
    filter_horizontal = ('grados',)
    readonly_fields = ('autor', 'creado_por', 'modificado_por', 'fecha_modificacion')
    inlines = [FotoGaleriaInline]
    formfield_overrides = COMMON_FORMFIELD_OVERRIDES
    fieldsets = (
        ('📝 Datos del evento', {
            'fields': ('titulo', 'descripcion', 'fecha_evento'),
        }),
        ('🎯 Visibilidad', {
            'fields': ('grados', 'activa'),
        }),
        ('📊 Auditoría', {
            'fields': ('autor', 'creado_por', 'modificado_por', 'fecha_modificacion'),
            'classes': ('collapse',),
        }),
    )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.autor = request.user
            obj.creado_por = request.user
            obj.modificado_por = request.user
        super().save_model(request, obj, form, change)
        registrar_audit(
            request.user,
            'editar' if change else 'crear',
            obj,
            cambios={'campos_modificados': list(form.changed_data)} if change else None,
        )

    def delete_model(self, request, obj):
        registrar_audit(request.user, 'eliminar', obj)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            registrar_audit(request.user, 'eliminar', obj)
        super().delete_queryset(request, queryset)


# =================================================================
# ConfiguracionPortal (singleton)
# =================================================================
@admin.register(ConfiguracionPortal)
class ConfiguracionPortalAdmin(admin.ModelAdmin):
    formfield_overrides = COMMON_FORMFIELD_OVERRIDES
    fieldsets = (
        ('🏫 Identidad institucional', {
            'fields': ('nombre_institucion', 'titulo_landing', 'texto_bienvenida'),
        }),
        ('🎨 Branding', {
            'fields': ('logo', 'portada', 'color_primario', 'color_secundario'),
        }),
        ('📞 Contacto', {
            'fields': ('email_contacto', 'whatsapp_escuela'),
            'description': 'El campo whatsapp_escuela está deprecated y será eliminado en una próxima versión.',
        }),
    )

    def has_add_permission(self, request):
        return not ConfiguracionPortal.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


# =================================================================
# PerfilPadre
# =================================================================
@admin.register(PerfilPadre)
class PerfilPadreAdmin(admin.ModelAdmin):
    list_display = ('user', 'dni', 'telefono', 'email_verificado', 'fecha_registro')
    list_filter = ('email_verificado', 'notif_email')
    search_fields = ('user__username', 'user__email', 'user__first_name', 'dni')
    
    readonly_fields = ('fecha_registro',)
    fieldsets = (
        ('👤 Cuenta', {
            'fields': ('user', 'dni', 'telefono'),
        }),
        
        ('🔔 Notificaciones', {
            'fields': ('notif_email', 'email_verificado'),
        }),
        ('📅 Sistema', {
            'fields': ('fecha_registro',),
            'classes': ('collapse',),
        }),
    )


# =================================================================
# AuditLog (solo lectura)
# =================================================================
@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'usuario', 'accion', 'modelo', 'objeto_repr')
    list_filter = ('accion', 'modelo', 'timestamp')
    search_fields = ('objeto_repr', 'usuario__username')
    date_hierarchy = 'timestamp'
    readonly_fields = ('usuario', 'accion', 'modelo', 'objeto_id', 'objeto_repr', 'timestamp', 'cambios')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ================================================================
# Ocultar User del menú lateral (se gestiona desde PerfilDocente)
# La visibilidad se controla vía JAZZMIN_SETTINGS['hide_models']
# ================================================================