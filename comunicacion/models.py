from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

from .utils import convertir_a_webp


TURNO_CHOICES = [
    ('manana', 'Mañana'),
    ('tarde', 'Tarde'),
    ('vespertino', 'Vespertino'),
]

TIPO_COMUNICADO_CHOICES = [
    ('aviso', '📢 Aviso'),
    ('tarea', '📚 Tarea'),
    ('evento', '📅 Evento'),
    ('material', '📎 Material'),
    ('urgente', '🚨 Urgente'),
]

ROL_DOCENTE_CHOICES = [
    ('docente', 'Docente'),
    ('preceptor', 'Preceptor'),
    ('directivo', 'Directivo'),
]

NOTIF_PADRE_CHOICES = [
    ('todos', 'Recibir todos los avisos por email'),
    ('urgentes', 'Solo avisos marcados como urgentes'),
    ('ninguno', 'No recibir emails (entro al portal cuando quiero)'),
]


class Grado(models.Model):
    nombre = models.CharField(max_length=50, help_text='Ej: 1ro A, 2do B')
    turno = models.CharField(max_length=20, choices=TURNO_CHOICES, default='manana')
    slug = models.SlugField(unique=True, blank=True)
    activo = models.BooleanField(default=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['orden', 'nombre']
        verbose_name_plural = 'Grados'

    def __str__(self):
        return f'{self.nombre} - {self.get_turno_display()}'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f'{self.nombre}-turno-{self.turno}')
        super().save(*args, **kwargs)


class Materia(models.Model):
    nombre = models.CharField(max_length=50, help_text='Ej: Matemáticas, Educación Física')
    color = models.CharField(
        max_length=7,
        blank=True,
        default='',
        help_text='Color hex (ej: #fb923c). Si está vacío, se genera automáticamente del nombre.'
    )

    class Meta:
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    def get_color(self):
        """Devuelve el color hex configurado, o uno generado a partir del nombre."""
        # Si tiene color válido (hex de 7 chars empezando con #), usarlo
        if self.color and self.color.startswith('#') and len(self.color) == 7:
            return self.color
        # Generar color estable a partir del nombre usando paleta predefinida
        paleta = [
            '#ef4444', '#f97316', '#eab308', '#22c55e',
            '#10b981', '#06b6d4', '#3b82f6', '#6366f1',
            '#8b5cf6', '#ec4899', '#64748b', '#0f172a',
        ]
        if not self.nombre:
            return paleta[0]
        indice = sum(ord(c) for c in self.nombre) % len(paleta)
        return paleta[indice]


class PerfilDocente(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil_docente')
    rol = models.CharField(max_length=20, choices=ROL_DOCENTE_CHOICES, default='docente')
    dni = models.CharField(max_length=20, blank=True, default='')
    telefono = models.CharField(max_length=30, blank=True)
    foto = models.ImageField(upload_to='docentes/', blank=True, null=True)
    titulo = models.CharField(
        max_length=120,
        blank=True,
        default='',
        help_text='Título profesional. Ej: "Profesora de Matemáticas", "Lic. en Educación".'
    )
    fecha_ingreso = models.DateField(
        null=True,
        blank=True,
        help_text='Fecha en que comenzó a trabajar en la institución.'
    )
    observaciones = models.TextField(
        blank=True,
        default='',
        help_text='Notas internas del director (no son visibles para el docente ni para padres).'
    )

    def get_iniciales(self):
        """Devuelve las iniciales (max 2) del docente para usar como avatar."""
        nombre = (self.user.first_name or self.user.username or '?').strip()
        apellido = (self.user.last_name or '').strip()
        if apellido:
            return (nombre[:1] + apellido[:1]).upper()
        partes = nombre.split()
        if len(partes) >= 2:
            return (partes[0][:1] + partes[1][:1]).upper()
        return nombre[:2].upper() or '?'

    def get_nombre_completo(self):
        """Devuelve el nombre completo o username como fallback."""
        nombre = (self.user.first_name or '').strip()
        apellido = (self.user.last_name or '').strip()
        completo = (nombre + ' ' + apellido).strip()
        return completo or self.user.username

    class Meta:
        verbose_name = 'Docente'
        verbose_name_plural = 'Docentes'

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    @property
    def puede_publicar_general(self):
        return self.rol in ('preceptor', 'directivo')


class AsignacionDocente(models.Model):
    docente = models.ForeignKey(PerfilDocente, on_delete=models.CASCADE, related_name='asignaciones')
    grado = models.ForeignKey(Grado, on_delete=models.CASCADE, related_name='asignaciones')
    materia = models.ForeignKey(Materia, on_delete=models.CASCADE, related_name='asignaciones')

    class Meta:
        unique_together = ('docente', 'grado', 'materia')
        ordering = ['docente', 'grado', 'materia']
        verbose_name = 'Asignación de Docente'
        verbose_name_plural = 'Asignaciones de Docentes'

    def __str__(self):
        return f'{self.docente} → {self.materia} en {self.grado}'


class Comunicado(models.Model):
    titulo = models.CharField(max_length=200)
    contenido = models.TextField()
    fecha_publicacion = models.DateTimeField(auto_now_add=True)
    autor = models.ForeignKey(User, on_delete=models.CASCADE)
    grados = models.ManyToManyField(Grado, related_name='comunicados')
    materia = models.ForeignKey(
        Materia,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text='Dejar vacío para comunicados generales del aula (solo preceptores/directivos)',
    )
    archivo_adjunto = models.FileField(upload_to='adjuntos/', blank=True, null=True)
    activo = models.BooleanField(default=True)
    tipo = models.CharField(max_length=20, choices=TIPO_COMUNICADO_CHOICES, default='aviso')
    fijado = models.BooleanField(default=False, help_text='Los comunicados fijados aparecen siempre arriba')
    urgente = models.BooleanField(default=False, help_text='Marca el comunicado con un badge rojo destacado')
    es_institucional = models.BooleanField(
        default=False,
        help_text='Comunicado de la institución (director). Sin materia, dirigido a la escuela.'
    )
    fecha_vencimiento = models.DateField(null=True, blank=True, help_text='Solo para tareas con plazo')
    ocultar_al_vencer = models.BooleanField(
        default=False,
        help_text='Si está marcado, el comunicado se oculta automáticamente del muro público después de la fecha de vencimiento.'
    )
    vistas = models.PositiveIntegerField(default=0, editable=False)
    creado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='comunicados_creados',
        editable=False,
    )
    modificado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='comunicados_modificados',
        editable=False,
    )
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-fijado', '-fecha_publicacion']

    def __str__(self):
        return self.titulo

    def esta_vencido(self):
        """True si tiene fecha_vencimiento y ya pasó."""
        if not self.fecha_vencimiento:
            return False
        from django.utils import timezone
        return self.fecha_vencimiento < timezone.localdate()

    def dias_para_vencer(self):
        """Devuelve días que faltan para vencer (negativo si ya venció), o None si no tiene fecha."""
        if not self.fecha_vencimiento:
            return None
        from django.utils import timezone
        return (self.fecha_vencimiento - timezone.localdate()).days


class ImagenComunicado(models.Model):
    comunicado = models.ForeignKey(Comunicado, related_name='imagenes', on_delete=models.CASCADE)
    imagen = models.ImageField(upload_to='comunicados_imagenes/')

    def __str__(self):
        return f'Imagen de: {self.comunicado.titulo}'

    def save(self, *args, **kwargs):
        if self.imagen and not self.imagen.name.endswith('.webp'):
            self.imagen = convertir_a_webp(self.imagen)
        super().save(*args, **kwargs)


class Galeria(models.Model):
    titulo = models.CharField(max_length=200, help_text='Ej: Acto del 25 de Mayo')
    descripcion = models.TextField(blank=True)
    fecha_evento = models.DateField()
    fecha_publicacion = models.DateTimeField(auto_now_add=True)
    autor = models.ForeignKey(User, on_delete=models.CASCADE)
    grados = models.ManyToManyField(Grado, related_name='galerias')
    activa = models.BooleanField(default=True)
    creado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='galerias_creadas',
        editable=False,
    )
    modificado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='galerias_modificadas',
        editable=False,
    )
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-fecha_evento']
        verbose_name_plural = 'Galerías'

    def __str__(self):
        return self.titulo


class FotoGaleria(models.Model):
    galeria = models.ForeignKey(Galeria, related_name='fotos', on_delete=models.CASCADE)
    imagen = models.ImageField(upload_to='galerias/')
    descripcion = models.CharField(max_length=200, blank=True)
    orden = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['orden', 'id']

    def save(self, *args, **kwargs):
        if self.imagen and not self.imagen.name.endswith('.webp'):
            self.imagen = convertir_a_webp(self.imagen)
        super().save(*args, **kwargs)


class ConfiguracionPortal(models.Model):
    nombre_institucion = models.CharField(max_length=100, default='Mi Escuela')
    color_primario = models.CharField(max_length=7, default='#0f172a', help_text='Código HEX (ej. #0f172a)')
    color_secundario = models.CharField(max_length=7, default='#3b82f6', help_text='Código HEX (ej. #3b82f6)')
    logo = models.ImageField(upload_to='portal/logos/', null=True, blank=True)
    portada = models.ImageField(upload_to='portal/portadas/', null=True, blank=True)
    titulo_landing = models.CharField(max_length=200, default='Bienvenidos al Portal Escolar')
    texto_bienvenida = models.TextField(default='Aquí encontrarás todas las comunicaciones.')
    whatsapp_escuela = models.CharField(max_length=30, blank=True, default='', help_text='Número con código de país, sin espacios. Ej: 5493624123456')
    email_contacto = models.EmailField(blank=True, default='')
    mostrar_portada_grande = models.BooleanField(default=False, help_text='Si está activo, muestra el banner grande con la portada en el landing. Si no, muestra solo un header sutil.')
    mensaje_bienvenida = models.CharField(max_length=200, blank=True, default='', help_text='Texto principal del landing. Ej: "Bienvenidos al Portal".')
    mensaje_secundario = models.CharField(max_length=300, blank=True, default='', help_text='Texto debajo del mensaje principal. Ej: "Encontrá rápido el aula de tu hijo/a".')

    class Meta:
        verbose_name = 'Configuración del Portal'
        verbose_name_plural = 'Configuraciones del Portal'

    def __str__(self):
        return 'Configuración Activa'

    def save(self, *args, **kwargs):
        if ConfiguracionPortal.objects.exists() and not self.pk:
            raise ValidationError('Solo puede existir una Configuración del Portal')
        super(ConfiguracionPortal, self).save(*args, **kwargs)


class PerfilPadre(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil_padre')
    dni = models.CharField(max_length=20, blank=True, default='')
    telefono = models.CharField(max_length=30, blank=True, default='')
    hijos_grados = models.ManyToManyField(Grado, related_name='padres_seguidores', blank=True)
    email_verificado = models.BooleanField(default=False)
    notif_email = models.BooleanField(default=True, help_text='Recibir notificaciones por email')
    tipo_notificacion = models.CharField(
        max_length=20,
        choices=NOTIF_PADRE_CHOICES,
        default='todos',
        help_text='Qué emails quiere recibir el padre/tutor',
    )
    foto = models.ImageField(
        upload_to='padres/',
        blank=True,
        null=True,
        help_text='Foto opcional del padre/tutor',
    )
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Perfil de Padre/Tutor'
        verbose_name_plural = 'Perfiles de Padres/Tutores'

    def __str__(self):
        return self.user.get_full_name() or self.user.username


ACCION_AUDIT_CHOICES = [
    ('crear', 'Creación'),
    ('editar', 'Edición'),
    ('eliminar', 'Eliminación'),
    ('publicar', 'Publicación'),
]


class AuditLog(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    accion = models.CharField(max_length=20, choices=ACCION_AUDIT_CHOICES)
    modelo = models.CharField(max_length=50)
    objeto_id = models.PositiveIntegerField(null=True, blank=True)
    objeto_repr = models.CharField(max_length=200, blank=True, default='')
    timestamp = models.DateTimeField(auto_now_add=True)
    cambios = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Registro de Auditoría'
        verbose_name_plural = 'Registros de Auditoría'

    def __str__(self):
        return f'{self.timestamp:%Y-%m-%d %H:%M} - {self.usuario} - {self.accion} {self.modelo}'


DIA_CHOICES = [
    ('lun', 'Lunes'),
    ('mar', 'Martes'),
    ('mie', 'Miércoles'),
    ('jue', 'Jueves'),
    ('vie', 'Viernes'),
    ('sab', 'Sábado'),
]


class HorarioDocente(models.Model):
    asignacion = models.ForeignKey(
        AsignacionDocente,
        on_delete=models.CASCADE,
        related_name='horarios'
    )
    dia = models.CharField(max_length=3, choices=DIA_CHOICES)
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    aula = models.CharField(max_length=30, blank=True, default='')

    class Meta:
        ordering = ['dia', 'hora_inicio']
        verbose_name = 'Horario'
        verbose_name_plural = 'Horarios'

    def __str__(self):
        return f'{self.get_dia_display()} {self.hora_inicio:%H:%M}-{self.hora_fin:%H:%M}'

    @property
    def duracion_minutos(self):
        from datetime import datetime, timedelta
        inicio = datetime.combine(datetime.today(), self.hora_inicio)
        fin = datetime.combine(datetime.today(), self.hora_fin)
        delta = fin - inicio
        return int(delta.total_seconds() // 60)


class HijoPadre(models.Model):
    padre = models.ForeignKey(
        PerfilPadre,
        on_delete=models.CASCADE,
        related_name='hijos',
    )
    nombre = models.CharField(
        max_length=100,
        help_text='Nombre y apellido del hijo/a',
    )
    grado = models.ForeignKey(
        Grado,
        on_delete=models.PROTECT,
        related_name='alumnos_seguidos',
        help_text='Grado/aula que cursa este hijo/a',
    )
    fecha_alta = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = 'Hijo/a de padre'
        verbose_name_plural = 'Hijos/as de padres'

    def __str__(self):
        return f'{self.nombre} ({self.grado})'