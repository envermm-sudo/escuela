from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from comunicacion.audit import registrar_audit
from comunicacion.models import Comunicado, Galeria, ImagenComunicado, TIPO_COMUNICADO_CHOICES, TURNO_CHOICES
from comunicacion.utils import convertir_a_webp
from .forms import ComunicadoForm
from .plantillas_comunicado import PLANTILLAS_COMUNICADO, get_plantilla
from .permissions import (
    es_directivo_o_preceptor,
    es_directivo_o_superuser,
    get_perfil_docente,
    staff_required,
    puede_editar_perfil,
    puede_eliminar_perfil,
    filtrar_personal_visible,
    aplicar_defaults_permisos_por_rol,
    DEFAULTS_PERMISOS_POR_ROL,
    permiso_institucional_required,
    permiso_auditoria_required,
    permiso_configuracion_required,
    permiso_materias_grados_required,
)


# ================================================================
# AUTH
# ================================================================
def login_view(request):
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('staff:dashboard')
    error = None
    if request.method == 'POST':
        identificador = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')

        # Buscar por email O por username (para superuser que puede no tener email)
        user_obj = User.objects.filter(email__iexact=identificador).first()
        if not user_obj:
            user_obj = User.objects.filter(username__iexact=identificador).first()

        if user_obj and user_obj.is_staff:
            user_auth = authenticate(request, username=user_obj.username, password=password)
            if user_auth is not None:
                auth_login(request, user_auth)
                return redirect('staff:dashboard')
            error = 'Contraseña incorrecta.'
        elif user_obj and not user_obj.is_staff:
            # Existe el usuario pero es un padre — orientarlo a la puerta correcta
            error = (
                'Esta entrada es solo para personal de la escuela. '
                'Si sos un padre/madre, ingresá por la página de login de familias.'
            )
        else:
            error = 'No existe una cuenta de personal con ese correo o usuario.'

    return render(request, 'staff/login.html', {'error': error})


def logout_view(request):
    auth_logout(request)
    messages.info(request, 'Sesión cerrada.')
    return redirect('staff:login')


# ================================================================
# Helper: queryset de comunicados visibles para el usuario
# ================================================================
def _comunicados_visibles(user):
    if user.is_superuser:
        return Comunicado.objects.all()
    perfil = get_perfil_docente(user)
    if es_directivo_o_preceptor(user):
        return Comunicado.objects.all()
    if perfil is None:
        return Comunicado.objects.none()

    asignaciones = perfil.asignaciones.all()
    grados_ids = asignaciones.values_list('grado_id', flat=True).distinct()
    materias_ids = asignaciones.values_list('materia_id', flat=True).distinct()

    propios = Comunicado.objects.filter(autor=user)
    de_asignaciones = Comunicado.objects.filter(
        grados__in=grados_ids,
        materia__in=materias_ids,
    )
    return (propios | de_asignaciones).distinct()


def _puede_editar(user, comunicado):
    """Reglas: directivos/preceptores editan todo. Docentes solo si son autor o el comunicado esta en sus asignaciones."""
    if user.is_superuser:
        return True
    if es_directivo_o_preceptor(user):
        return True
    if comunicado.autor_id == user.id or comunicado.creado_por_id == user.id:
        return True

    perfil = get_perfil_docente(user)
    if perfil is None:
        return False

    asignaciones = perfil.asignaciones.all()
    grados_ids = set(asignaciones.values_list('grado_id', flat=True))
    materias_ids = set(asignaciones.values_list('materia_id', flat=True))
    if comunicado.materia_id and comunicado.materia_id in materias_ids:
        if comunicado.grados.filter(id__in=grados_ids).exists():
            return True
    return False


# ================================================================
# DASHBOARD
# ================================================================
@staff_required
def dashboard_view(request):
    perfil = get_perfil_docente(request.user)
    es_directivo_super = es_directivo_o_superuser(request.user)

    # Stats globales (solo para directivo/superuser)
    stats = {}
    if es_directivo_super:
        from comunicacion.models import AsignacionDocente, Grado, Materia, PerfilDocente
        stats = {
            'total_docentes': PerfilDocente.objects.count(),
            'total_materias': Materia.objects.count(),
            'total_grados': Grado.objects.filter(activo=True).count(),
            'total_asignaciones': AsignacionDocente.objects.count(),
            'total_comunicados': Comunicado.objects.filter(activo=True).count(),
            'total_galerias': Galeria.objects.filter(activa=True).count(),
        }

    # Para docente comun: sus comunicados recientes
    if perfil and not es_directivo_super:
        comunicados_propios = Comunicado.objects.filter(autor=request.user).order_by('-fecha_publicacion')[:5]
        asignaciones = list(perfil.asignaciones.select_related('grado', 'materia'))
    else:
        comunicados_propios = Comunicado.objects.all().order_by('-fecha_publicacion')[:5]
        asignaciones = []

    return render(request, 'staff/dashboard.html', {
        'perfil': perfil,
        'es_directivo': es_directivo_super,
        'stats': stats,
        'comunicados_propios': comunicados_propios,
        'asignaciones': asignaciones,
    })


# ================================================================
# COMUNICADOS - LISTA
# ================================================================
@staff_required
def comunicados_lista(request):
    qs = _comunicados_visibles(request.user)

    busqueda = request.GET.get('q', '').strip()
    tipo = request.GET.get('tipo', '').strip()
    grado_id = request.GET.get('grado', '').strip()
    estado = request.GET.get('estado', '').strip()  # '', 'activo', 'inactivo', 'fijado', 'urgente'

    if busqueda:
        qs = qs.filter(Q(titulo__icontains=busqueda) | Q(contenido__icontains=busqueda))
    if tipo:
        qs = qs.filter(tipo=tipo)
    if grado_id.isdigit():
        qs = qs.filter(grados__id=int(grado_id))
    if estado == 'activo':
        qs = qs.filter(activo=True)
    elif estado == 'inactivo':
        qs = qs.filter(activo=False)
    elif estado == 'fijado':
        qs = qs.filter(fijado=True)
    elif estado == 'urgente':
        qs = qs.filter(urgente=True)

    qs = qs.distinct().order_by('-fijado', '-fecha_publicacion')

    paginator = Paginator(qs, 12)
    page_num = request.GET.get('page', 1)
    page = paginator.get_page(page_num)

    # Para el filtro de grados, usamos los grados de las asignaciones del docente
    perfil = get_perfil_docente(request.user)
    if es_directivo_o_preceptor(request.user):
        from comunicacion.models import Grado
        grados_filtro = Grado.objects.filter(activo=True).order_by('orden', 'nombre')
    elif perfil:
        from comunicacion.models import Grado
        grados_ids = perfil.asignaciones.values_list('grado_id', flat=True).distinct()
        grados_filtro = Grado.objects.filter(id__in=grados_ids).order_by('orden', 'nombre')
    else:
        grados_filtro = []

    return render(request, 'staff/comunicados_lista.html', {
        'page': page,
        'busqueda': busqueda,
        'tipo': tipo,
        'grado_id': grado_id,
        'estado': estado,
        'tipos': TIPO_COMUNICADO_CHOICES,
        'grados_filtro': grados_filtro,
    })


# ================================================================
# COMUNICADOS - CREAR / EDITAR
# ================================================================
def _procesar_imagenes(request, comunicado):
    """Sube imagenes adjuntas convertidas a .webp. Captura errores por imagen sin tirar abajo el comunicado."""
    import logging

    logger = logging.getLogger(__name__)
    archivos = request.FILES.getlist('imagenes_nuevas')
    for f in archivos:
        try:
            content_type = getattr(f, 'content_type', '') or ''
            if not content_type.startswith('image/'):
                logger.info('Imagen omitida (content_type=%s): %s', content_type, getattr(f, 'name', '?'))
                continue
            webp_file = convertir_a_webp(f)
            if webp_file:
                ImagenComunicado.objects.create(comunicado=comunicado, imagen=webp_file)
            else:
                logger.warning('convertir_a_webp devolvió None para: %s', getattr(f, 'name', '?'))
        except Exception as exc:
            logger.exception('Error procesando imagen %s: %s', getattr(f, 'name', '?'), exc)
            # Seguimos con las demás


@staff_required
def comunicado_crear(request):
    perfil = get_perfil_docente(request.user)
    es_directivo = es_directivo_o_preceptor(request.user)

    # Verificar que el docente tenga asignaciones cargadas (si no es directivo)
    if not es_directivo and perfil and not perfil.asignaciones.exists():
        messages.warning(
            request,
            'Todavía no tenés materias ni grados asignados. Pedile al director que cargue tus asignaciones desde la matriz del docente.'
        )
        return redirect('staff:comunicados_lista')

    if request.method == 'POST':
        form = ComunicadoForm(request.POST, request.FILES, perfil_docente=perfil, es_directivo=es_directivo)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.autor = request.user
            obj.creado_por = request.user
            obj.modificado_por = request.user
            obj.save()
            fecha_publicacion = form.cleaned_data.get('fecha_publicacion')
            if fecha_publicacion:
                obj.fecha_publicacion = fecha_publicacion
                obj.save(update_fields=['fecha_publicacion'])
            form.save_m2m()
            _procesar_imagenes(request, obj)
            registrar_audit(request.user, 'crear', obj)
            # Notificar a padres por email (async, no bloquea)
            from comunicacion.emails import notificar_comunicado_a_padres
            try:
                notificar_comunicado_a_padres(obj)
            except Exception:
                pass  # No queremos que un fallo de email rompa la creación
            messages.success(request, f'Comunicado "{obj.titulo}" creado correctamente.')
            return redirect('staff:comunicado_detalle', pk=obj.pk)
    else:
        plantilla_codigo = request.GET.get('plantilla', '').strip()
        plantilla = get_plantilla(plantilla_codigo)
        initial = {}
        if plantilla:
            initial['tipo'] = plantilla['tipo']
            initial['titulo'] = plantilla['titulo']
            initial['contenido'] = plantilla['contenido']
        form = ComunicadoForm(initial=initial, perfil_docente=perfil, es_directivo=es_directivo)

    return render(request, 'staff/comunicado_form.html', {
        'form': form,
        'titulo_pagina': 'Crear comunicado',
        'es_edicion': False,
        'plantillas': PLANTILLAS_COMUNICADO,
        'plantilla_actual': request.GET.get('plantilla', ''),
    })


@staff_required
def comunicado_editar(request, pk):
    comunicado = get_object_or_404(Comunicado, pk=pk)
    if not _puede_editar(request.user, comunicado):
        messages.error(request, 'No tenés permiso para editar este comunicado.')
        return redirect('staff:comunicados_lista')

    perfil = get_perfil_docente(request.user)
    es_directivo = es_directivo_o_preceptor(request.user)

    if request.method == 'POST':
        form = ComunicadoForm(
            request.POST,
            request.FILES,
            instance=comunicado,
            perfil_docente=perfil,
            es_directivo=es_directivo,
        )
        if form.is_valid():
            obj = form.save(commit=False)
            obj.modificado_por = request.user
            obj.save()
            fecha_publicacion = form.cleaned_data.get('fecha_publicacion')
            if fecha_publicacion:
                obj.fecha_publicacion = fecha_publicacion
                obj.save(update_fields=['fecha_publicacion'])
            form.save_m2m()
            _procesar_imagenes(request, obj)

            # Eliminar imagenes marcadas
            ids_eliminar = request.POST.getlist('eliminar_imagen')
            if ids_eliminar:
                ImagenComunicado.objects.filter(id__in=ids_eliminar, comunicado=obj).delete()

            registrar_audit(
                request.user,
                'editar',
                obj,
                cambios={'campos_modificados': list(form.changed_data)},
            )
            messages.success(request, 'Comunicado actualizado.')
            return redirect('staff:comunicado_detalle', pk=obj.pk)
    else:
        form = ComunicadoForm(instance=comunicado, perfil_docente=perfil, es_directivo=es_directivo)

    return render(request, 'staff/comunicado_form.html', {
        'form': form,
        'comunicado': comunicado,
        'titulo_pagina': f'Editar: {comunicado.titulo}',
        'es_edicion': True,
        'plantillas': [],
        'plantilla_actual': '',
    })


# ================================================================
# COMUNICADOS - DETALLE
# ================================================================
@staff_required
def comunicado_detalle(request, pk):
    comunicado = get_object_or_404(Comunicado, pk=pk)
    visibles = _comunicados_visibles(request.user)
    if not visibles.filter(pk=comunicado.pk).exists():
        messages.error(request, 'No tenés acceso a este comunicado.')
        return redirect('staff:comunicados_lista')

    return render(request, 'staff/comunicado_detalle.html', {
        'comunicado': comunicado,
        'puede_editar': _puede_editar(request.user, comunicado),
    })


# ================================================================
# COMUNICADOS - ELIMINAR
# ================================================================
@staff_required
def comunicado_eliminar(request, pk):
    comunicado = get_object_or_404(Comunicado, pk=pk)
    if not _puede_editar(request.user, comunicado):
        messages.error(request, 'No tenés permiso para eliminar este comunicado.')
        return redirect('staff:comunicados_lista')

    if request.method == 'POST':
        titulo = comunicado.titulo
        registrar_audit(request.user, 'eliminar', comunicado)
        comunicado.delete()
        messages.success(request, f'Comunicado "{titulo}" eliminado.')
        return redirect('staff:comunicados_lista')

    return render(request, 'staff/comunicado_eliminar.html', {'comunicado': comunicado})


from comunicacion.models import FotoGaleria
from .forms import GaleriaForm


# ================================================================
# Helper galerias
# ================================================================
def _galerias_visibles(user):
    if user.is_superuser:
        return Galeria.objects.all()
    if es_directivo_o_preceptor(user):
        return Galeria.objects.all()
    return Galeria.objects.filter(autor=user)


def _puede_editar_galeria(user, galeria):
    if user.is_superuser:
        return True
    if es_directivo_o_preceptor(user):
        return True
    return galeria.autor_id == user.id or galeria.creado_por_id == user.id


def _procesar_fotos_galeria(request, galeria):
    archivos = request.FILES.getlist('fotos_nuevas')
    for f in archivos:
        if not f.content_type.startswith('image/'):
            continue
        webp_file = convertir_a_webp(f)
        if webp_file:
            FotoGaleria.objects.create(galeria=galeria, imagen=webp_file)


# ================================================================
# GALERIAS - LISTA
# ================================================================
@staff_required
def galerias_lista(request):
    qs = _galerias_visibles(request.user)
    busqueda = request.GET.get('q', '').strip()
    if busqueda:
        qs = qs.filter(Q(titulo__icontains=busqueda) | Q(descripcion__icontains=busqueda))
    qs = qs.distinct().order_by('-fecha_evento')
    paginator = Paginator(qs, 12)
    page = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'staff/galerias_lista.html', {
        'page': page,
        'busqueda': busqueda,
    })


# ================================================================
# GALERIAS - CREAR / EDITAR
# ================================================================
@staff_required
def galeria_crear(request):
    perfil = get_perfil_docente(request.user)
    es_directivo = es_directivo_o_preceptor(request.user)
    if request.method == 'POST':
        form = GaleriaForm(request.POST, perfil_docente=perfil, es_directivo=es_directivo)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.autor = request.user
            obj.creado_por = request.user
            obj.modificado_por = request.user
            obj.save()
            form.save_m2m()
            _procesar_fotos_galeria(request, obj)
            registrar_audit(request.user, 'crear', obj)
            messages.success(request, f'Galería "{obj.titulo}" creada correctamente.')
            return redirect('staff:galeria_detalle', pk=obj.pk)
    else:
        form = GaleriaForm(perfil_docente=perfil, es_directivo=es_directivo)

    return render(request, 'staff/galeria_form.html', {
        'form': form,
        'titulo_pagina': 'Crear galería',
        'es_edicion': False,
    })


@staff_required
def galeria_editar(request, pk):
    galeria = get_object_or_404(Galeria, pk=pk)
    if not _puede_editar_galeria(request.user, galeria):
        messages.error(request, 'No tenés permiso para editar esta galería.')
        return redirect('staff:galerias_lista')
    perfil = get_perfil_docente(request.user)
    es_directivo = es_directivo_o_preceptor(request.user)

    if request.method == 'POST':
        form = GaleriaForm(request.POST, instance=galeria, perfil_docente=perfil, es_directivo=es_directivo)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.modificado_por = request.user
            obj.save()
            form.save_m2m()
            _procesar_fotos_galeria(request, obj)

            ids_eliminar = request.POST.getlist('eliminar_foto')
            if ids_eliminar:
                FotoGaleria.objects.filter(id__in=ids_eliminar, galeria=obj).delete()

            registrar_audit(request.user, 'editar', obj,
                            cambios={'campos_modificados': list(form.changed_data)})
            messages.success(request, 'Galería actualizada.')
            return redirect('staff:galeria_detalle', pk=obj.pk)
    else:
        form = GaleriaForm(instance=galeria, perfil_docente=perfil, es_directivo=es_directivo)

    return render(request, 'staff/galeria_form.html', {
        'form': form,
        'galeria': galeria,
        'titulo_pagina': f'Editar: {galeria.titulo}',
        'es_edicion': True,
    })


# ================================================================
# GALERIAS - DETALLE / ELIMINAR
# ================================================================
@staff_required
def galeria_detalle(request, pk):
    galeria = get_object_or_404(Galeria, pk=pk)
    visibles = _galerias_visibles(request.user)
    if not visibles.filter(pk=galeria.pk).exists():
        messages.error(request, 'No tenés acceso a esta galería.')
        return redirect('staff:galerias_lista')
    return render(request, 'staff/galeria_detalle.html', {
        'galeria': galeria,
        'puede_editar': _puede_editar_galeria(request.user, galeria),
    })


@staff_required
def galeria_eliminar(request, pk):
    galeria = get_object_or_404(Galeria, pk=pk)
    if not _puede_editar_galeria(request.user, galeria):
        messages.error(request, 'No tenés permiso para eliminar esta galería.')
        return redirect('staff:galerias_lista')
    if request.method == 'POST':
        titulo = galeria.titulo
        registrar_audit(request.user, 'eliminar', galeria)
        galeria.delete()
        messages.success(request, f'Galería "{titulo}" eliminada.')
        return redirect('staff:galerias_lista')

    return render(request, 'staff/galeria_eliminar.html', {'galeria': galeria})


# ================================================================
# MIS ASIGNACIONES
# ================================================================
@staff_required
@staff_required
def mis_asignaciones(request):
    perfil = get_perfil_docente(request.user)

    # Directivos/preceptores/superuser no usan esta vista — los redirigimos al panel de personal
    if request.user.is_superuser or (perfil and perfil.rol in ('directivo', 'preceptor')):
        return redirect('staff:personal_lista')

    if not perfil:
        messages.error(request, 'Tu cuenta no tiene perfil docente asociado.')
        return redirect('staff:dashboard')

    asignaciones = perfil.asignaciones.select_related('grado', 'materia').order_by('grado__orden', 'grado__nombre', 'materia__nombre')

    return render(request, 'staff/mis_asignaciones.html', {
        'asignaciones': asignaciones,
        'perfil': perfil,
    })


# ================================================================
# ESTADISTICAS
# ================================================================
@staff_required
def estadisticas(request):
    from collections import Counter, OrderedDict
    from datetime import timedelta

    qs = _comunicados_visibles(request.user)
    total = qs.count()
    total_vistas = qs.aggregate(total=Sum('vistas'))['total'] or 0
    promedio_vistas = round(total_vistas / total, 1) if total else 0

    # Top 5 comunicados mas vistos
    top_comunicados = qs.order_by('-vistas')[:5]

    # Distribucion por tipo
    por_tipo = Counter(qs.values_list('tipo', flat=True))
    tipos_etiquetas = dict(TIPO_COMUNICADO_CHOICES)
    distribucion = [
        {'codigo': cod, 'etiqueta': tipos_etiquetas.get(cod, cod), 'cuenta': cnt}
        for cod, cnt in por_tipo.most_common()
    ]

    # Evolucion ultimos 6 meses (mes-ano -> cuantos publico)
    hoy = timezone.now()
    meses = OrderedDict()
    for i in range(5, -1, -1):
        mes_dt = (hoy.replace(day=1) - timedelta(days=i * 30))
        clave = mes_dt.strftime('%Y-%m')
        etiqueta = mes_dt.strftime('%b %Y')
        meses[clave] = {'etiqueta': etiqueta, 'cuenta': 0}

    for c in qs.values_list('fecha_publicacion', flat=True):
        clave = c.strftime('%Y-%m')
        if clave in meses:
            meses[clave]['cuenta'] += 1

    evolucion = list(meses.values())
    max_cuenta = max((m['cuenta'] for m in evolucion), default=1) or 1

    return render(request, 'staff/estadisticas.html', {
        'total': total,
        'total_vistas': total_vistas,
        'promedio_vistas': promedio_vistas,
        'top_comunicados': top_comunicados,
        'distribucion': distribucion,
        'evolucion': evolucion,
        'max_cuenta': max_cuenta,
    })


from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash
from django.shortcuts import get_object_or_404
from comunicacion.models import HorarioDocente, PerfilDocente, AsignacionDocente


# ================================================================
# LISTADO Y FICHA DEL DOCENTE
# ================================================================
@staff_required
def docente_ficha(request, pk):
    docente = get_object_or_404(PerfilDocente.objects.select_related('user'), pk=pk)

    # Agrupar asignaciones por grado para mostrar la ficha bonita
    asignaciones = (
        AsignacionDocente.objects
        .filter(docente=docente)
        .select_related('grado', 'materia')
        .prefetch_related('horarios')
        .order_by('grado__orden', 'grado__nombre', 'grado__turno', 'materia__nombre')
    )

    # Agrupar por grado: { grado: [(materia, [horarios]), ...] }
    from collections import OrderedDict
    grupos = OrderedDict()
    for a in asignaciones:
        clave = a.grado
        if clave not in grupos:
            grupos[clave] = []
        grupos[clave].append({
            'asignacion': a,
            'materia': a.materia,
            'horarios': list(a.horarios.all().order_by('dia', 'hora_inicio')),
        })

    # Total de horas semanales (suma de duraciones de todos los horarios)
    total_horas_min = 0
    for a in asignaciones:
        for h in a.horarios.all():
            total_horas_min += h.duracion_minutos

    return render(request, 'staff/docente_ficha.html', {
        'docente': docente,
        'grupos': grupos,
        'cant_asignaciones': asignaciones.count(),
        'cant_grados': len(grupos),
        'total_horas': total_horas_min // 60,
        'total_minutos': total_horas_min % 60,
    })


# ================================================================
# MI PERFIL (el docente edita lo suyo)
# ================================================================
@staff_required
def mi_perfil_view(request):
    perfil = get_perfil_docente(request.user)
    if not perfil:
        messages.error(request, 'Tu cuenta no tiene perfil docente asociado.')
        return redirect('staff:dashboard')

    if request.method == 'POST':
        # Datos del User
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()

        if not first_name or not last_name:
            messages.error(request, 'Nombre y apellido son obligatorios.')
            return redirect('staff:mi_perfil')

        request.user.first_name = first_name
        request.user.last_name = last_name
        request.user.save(update_fields=['first_name', 'last_name'])

        # Datos del PerfilDocente
        perfil.titulo = request.POST.get('titulo', '').strip()[:120]
        perfil.telefono = request.POST.get('telefono', '').strip()[:30]
        perfil.dni = request.POST.get('dni', '').strip()[:20]
        perfil.notif_mensajeria_email = request.POST.get('notif_mensajeria_email') == 'on'

        # Foto nueva
        nueva_foto = request.FILES.get('foto')
        if nueva_foto:
            perfil.foto = nueva_foto  # la señal pre_save la convierte y renombra

        perfil.save()

        # Cambio de contraseña (opcional)
        password_actual = request.POST.get('password_actual', '')
        password_nueva = request.POST.get('password_nueva', '')
        password_repetir = request.POST.get('password_repetir', '')

        if password_nueva or password_repetir or password_actual:
            if not request.user.check_password(password_actual):
                messages.error(request, 'La contraseña actual no es correcta.')
                return redirect('staff:mi_perfil')
            if password_nueva != password_repetir:
                messages.error(request, 'Las contraseñas nuevas no coinciden.')
                return redirect('staff:mi_perfil')
            if len(password_nueva) < 6:
                messages.error(request, 'La nueva contraseña debe tener al menos 6 caracteres.')
                return redirect('staff:mi_perfil')

            request.user.set_password(password_nueva)
            request.user.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, 'Datos y contraseña actualizados correctamente.')
        else:
            messages.success(request, 'Datos actualizados correctamente.')

        return redirect('staff:mi_perfil')

    # GET
    asignaciones = (
        AsignacionDocente.objects
        .filter(docente=perfil)
        .select_related('grado', 'materia')
        .prefetch_related('horarios')
        .order_by('grado__orden', 'grado__nombre')
    )

    return render(request, 'staff/mi_perfil.html', {
        'perfil': perfil,
        'asignaciones': asignaciones,
    })


from comunicacion.models import ConfiguracionPortal


# ================================================================
# CONFIGURACION DEL PORTAL (solo directivo y superuser)
# ================================================================
@permiso_configuracion_required
def configuracion_portal_view(request):
    config, _ = ConfiguracionPortal.objects.get_or_create(pk=1)

    if request.method == 'POST':
        nombre_escuela = request.POST.get('nombre_escuela', '').strip()[:200]
        config.nombre_institucion = nombre_escuela
        config.email_contacto = request.POST.get('email_contacto', '').strip()[:200]
        config.mostrar_portada_grande = request.POST.get('mostrar_portada_grande') == 'on'
        config.mensaje_bienvenida = request.POST.get('mensaje_bienvenida', '').strip()[:200]
        config.mensaje_secundario = request.POST.get('mensaje_secundario', '').strip()[:300]

        nuevo_logo = request.FILES.get('logo')
        if nuevo_logo:
            config.logo = nuevo_logo
        if request.POST.get('logo_clear') == 'on':
            config.logo = None

        nueva_portada = request.FILES.get('portada')
        if nueva_portada:
            config.portada = nueva_portada
        if request.POST.get('portada_clear') == 'on':
            config.portada = None

        config.save()
        messages.success(request, 'Configuración actualizada correctamente.')
        return redirect('staff:configuracion')

    config.nombre_escuela = config.nombre_institucion
    return render(request, 'staff/configuracion.html', {'config': config})


# ================================================================
# AUDITORIA (solo directivo y superuser)
# ================================================================
@permiso_auditoria_required
def auditoria_view(request):
    from comunicacion.models import AuditLog
    logs = AuditLog.objects.select_related('usuario').order_by('-timestamp')[:200]
    return render(request, 'staff/auditoria.html', {'logs': logs})


from .permissions import es_directivo_o_superuser, directivo_o_superuser_required


# ================================================================
# GESTION — solo director y superuser
# ================================================================
@directivo_o_superuser_required
def gestion_dashboard(request):
    """Centro de gestión: links a cada sección administrativa."""
    from comunicacion.models import Grado, Materia, PerfilDocente
    return render(request, 'staff/gestion/dashboard.html', {
        'cant_docentes': PerfilDocente.objects.count(),
        'cant_materias': Materia.objects.count(),
        'cant_grados': Grado.objects.filter(activo=True).count(),
    })


# ----- Materias -----
@permiso_materias_grados_required
def gestion_materias_lista(request):
    from comunicacion.models import Materia
    materias = Materia.objects.all().order_by('nombre')
    return render(request, 'staff/gestion/materias_lista.html', {'materias': materias})


@permiso_materias_grados_required
def gestion_materia_form(request, pk=None):
    from comunicacion.models import Materia
    materia = get_object_or_404(Materia, pk=pk) if pk else None

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()[:100]
        color = request.POST.get('color', '').strip()
        if not nombre:
            messages.error(request, 'El nombre de la materia es obligatorio.')
        else:
            if materia:
                materia.nombre = nombre
                materia.color = color
                materia.save()
                messages.success(request, f'Materia "{nombre}" actualizada.')
            else:
                Materia.objects.create(nombre=nombre, color=color)
                messages.success(request, f'Materia "{nombre}" creada.')
            return redirect('staff:gestion_materias')

    PALETA = [
        ('#ef4444', 'Rojo'), ('#f97316', 'Naranja'), ('#eab308', 'Amarillo'),
        ('#22c55e', 'Verde'), ('#10b981', 'Esmeralda'), ('#06b6d4', 'Cian'),
        ('#3b82f6', 'Azul'), ('#6366f1', 'Índigo'), ('#8b5cf6', 'Violeta'),
        ('#ec4899', 'Rosa'), ('#64748b', 'Gris'), ('#0f172a', 'Negro'),
    ]
    return render(request, 'staff/gestion/materia_form.html', {
        'materia': materia,
        'paleta': PALETA,
    })


@permiso_materias_grados_required
def gestion_materia_eliminar(request, pk):
    from comunicacion.models import Materia
    materia = get_object_or_404(Materia, pk=pk)
    if request.method == 'POST':
        nombre = materia.nombre
        materia.delete()
        messages.success(request, f'Materia "{nombre}" eliminada.')
        return redirect('staff:gestion_materias')
    return render(request, 'staff/gestion/materia_eliminar.html', {'materia': materia})


# ----- Grados -----
@permiso_materias_grados_required
def gestion_grados_lista(request):
    from comunicacion.models import Grado
    grados = Grado.objects.all().order_by('orden', 'nombre', 'turno')
    return render(request, 'staff/gestion/grados_lista.html', {'grados': grados})


@permiso_materias_grados_required
def gestion_grado_form(request, pk=None):
    from comunicacion.models import Grado
    import re
    grado = get_object_or_404(Grado, pk=pk) if pk else None

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()[:50]
        turno = request.POST.get('turno', '').strip()
        activo = request.POST.get('activo') == 'on'

        # Validar turno contra opciones permitidas
        turnos_validos = [t[0] for t in TURNO_CHOICES]
        if turno not in turnos_validos:
            messages.error(request, 'Turno inválido. Elegí Mañana, Tarde o Vespertino.')
            turno = 'manana'

        if not nombre:
            messages.error(request, 'El nombre del grado es obligatorio.')
        else:
            # Orden correlativo: el número del grado pesa más que el turno
            # 1° Mañana = 10, 1° Tarde = 11, 2° Mañana = 20, 2° Tarde = 21, etc.
            numero_grado = 99  # default si no se encuentra número
            match = re.search(r'\d+', nombre)
            if match:
                try:
                    numero_grado = int(match.group())
                except ValueError:
                    numero_grado = 99

            turno_offset = {'manana': 0, 'tarde': 1, 'vespertino': 2}.get(turno, 9)
            orden_calculado = numero_grado * 10 + turno_offset

            if grado:
                grado.nombre = nombre
                grado.turno = turno
                grado.orden = orden_calculado
                grado.activo = activo
                grado.save()
                messages.success(request, f'Grado "{grado}" actualizado.')
            else:
                Grado.objects.create(
                    nombre=nombre,
                    turno=turno,
                    orden=orden_calculado,
                    activo=activo,
                )
                messages.success(request, f'Grado "{nombre}" creado.')
            return redirect('staff:gestion_grados')

    return render(request, 'staff/gestion/grado_form.html', {
        'grado': grado,
        'turnos': TURNO_CHOICES,
    })


@permiso_materias_grados_required
def gestion_grado_eliminar(request, pk):
    from comunicacion.models import Grado
    grado = get_object_or_404(Grado, pk=pk)
    if request.method == 'POST':
        nombre = str(grado)
        grado.delete()
        messages.success(request, f'Grado "{nombre}" eliminado.')
        return redirect('staff:gestion_grados')
    return render(request, 'staff/gestion/grado_eliminar.html', {'grado': grado})


# ----- Docentes (link directo al admin para crear/editar) -----
@directivo_o_superuser_required
def gestion_docentes_admin_link(request):
    """Para crear/editar docentes redirigir al admin Jazzmin (vista rica con foto, password, etc.)."""
    if request.user.is_superuser:
        return redirect('/admin/comunicacion/perfildocente/')
    messages.info(request, 'Para crear o editar docentes con foto y datos completos, pedile al administrador del sistema acceso al admin avanzado.')
    return redirect('staff:personal_lista')


# ================================================================
# COMUNICADO INSTITUCIONAL
# ================================================================
@permiso_institucional_required
def comunicado_institucional_crear(request):
    """Comunicado del director sin materia, dirigido a toda la escuela o grados específicos."""
    from comunicacion.models import Grado

    if request.method == 'POST':
        titulo = request.POST.get('titulo', '').strip()[:200]
        contenido = request.POST.get('contenido', '').strip()
        tipo = request.POST.get('tipo', 'aviso')
        fijado = request.POST.get('fijado') == 'on'
        urgente = request.POST.get('urgente') == 'on'
        grados_ids = request.POST.getlist('grados')
        a_toda_escuela = request.POST.get('toda_escuela') == 'on'

        if not titulo or not contenido:
            messages.error(request, 'Título y contenido son obligatorios.')
        elif not a_toda_escuela and not grados_ids:
            messages.error(request, 'Marcá "Toda la escuela" o seleccioná al menos un grado.')
        else:
            obj = Comunicado.objects.create(
                titulo=titulo,
                contenido=contenido,
                tipo=tipo,
                materia=None,
                autor=request.user,
                creado_por=request.user,
                modificado_por=request.user,
                fijado=fijado,
                urgente=urgente,
                activo=True,
                es_institucional=True,
            )
            if a_toda_escuela:
                obj.grados.set(Grado.objects.filter(activo=True))
            else:
                obj.grados.set(grados_ids)
            registrar_audit(request.user, 'crear', obj)
            from comunicacion.emails import notificar_comunicado_a_padres
            try:
                notificar_comunicado_a_padres(obj)
            except Exception:
                pass
            messages.success(request, f'Comunicado institucional "{titulo}" publicado.')
            return redirect('staff:comunicado_detalle', pk=obj.pk)

    grados = Grado.objects.filter(activo=True).order_by('orden', 'nombre', 'turno')
    return render(request, 'staff/comunicado_institucional_form.html', {
        'grados': grados,
        'tipos': TIPO_COMUNICADO_CHOICES,
    })


from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email

from comunicacion.models import AsignacionDocente, Grado, Materia, PerfilDocente


PASSWORD_RESET_DEFAULT = 'escuela2026'  # Contraseña que se asigna al resetear


# ================================================================
# LISTADO DE PERSONAL (unificado: docentes + preceptores + directivos)
# ================================================================
@staff_required
def gestion_personal_lista(request):
    """
    Listado unificado de personal.
    - Docentes: ven el listado, pueden hacer click para ver la ficha (solo lectura).
    - Directivos/superuser: ven además acciones de gestión (crear, editar, eliminar, matriz, reset password).
    """
    busqueda = request.GET.get('q', '').strip()
    rol_filtro = request.GET.get('rol', '').strip()
    es_gestor = es_directivo_o_superuser(request.user)
    qs = PerfilDocente.objects.select_related('user').order_by('user__last_name', 'user__first_name')
    qs = filtrar_personal_visible(qs, request.user)

    if busqueda:
        qs = qs.filter(
            Q(user__first_name__icontains=busqueda)
            | Q(user__last_name__icontains=busqueda)
            | Q(user__email__icontains=busqueda)
            | Q(user__username__icontains=busqueda)
            | Q(dni__icontains=busqueda)
            | Q(titulo__icontains=busqueda)
        )
    if rol_filtro in ('docente', 'preceptor', 'directivo'):
        qs = qs.filter(rol=rol_filtro)

    # Materializar el queryset y anotar cada perfil con sus permisos para la UI
    personal_lista = list(qs)
    for p in personal_lista:
        p.puede_editar = puede_editar_perfil(request.user, p)
        p.puede_eliminar = puede_eliminar_perfil(request.user, p)
        p.es_uno_mismo = (p.user_id == request.user.id)

    return render(request, 'staff/personal_lista.html', {
        'personal': personal_lista,
        'busqueda': busqueda,
        'rol_filtro': rol_filtro,
        'cant_total': len(personal_lista),
        'es_gestor': es_gestor,
    })


# ================================================================
# CREAR / EDITAR PERSONAL
# ================================================================
@directivo_o_superuser_required
def gestion_personal_form(request, pk=None):
    perfil = None
    if pk:
        perfil = get_object_or_404(PerfilDocente.objects.select_related('user'), pk=pk)
        if not puede_editar_perfil(request.user, perfil):
            messages.error(request, 'No tenés permisos para editar a este usuario.')
            return redirect('staff:personal_lista')

    if request.method == 'POST':
        # ----- Datos del User -----
        email = request.POST.get('email', '').strip().lower()
        nombre = request.POST.get('nombre', '').strip()
        apellido = request.POST.get('apellido', '').strip()
        password_nueva = request.POST.get('password_nueva', '').strip()

        # ----- Datos del PerfilDocente -----
        rol = request.POST.get('rol', 'docente')
        if rol not in ('docente', 'preceptor', 'directivo'):
            rol = 'docente'
        titulo = request.POST.get('titulo', '').strip()[:120]
        dni = request.POST.get('dni', '').strip()[:20]
        telefono = request.POST.get('telefono', '').strip()[:30]
        fecha_ingreso_str = request.POST.get('fecha_ingreso', '').strip()
        observaciones = request.POST.get('observaciones', '').strip()
        nueva_foto = request.FILES.get('foto')
        eliminar_foto = request.POST.get('foto_clear') == 'on'

        # ----- Validaciones -----
        errores = []

        # Email obligatorio y válido
        try:
            validate_email(email)
        except DjangoValidationError:
            errores.append('Ingresá un email válido (será el usuario para iniciar sesión).')

        # Email único (excepto el mismo usuario al editar)
        if email and not errores:
            qs_email = User.objects.filter(username__iexact=email)
            if perfil and perfil.user_id:
                qs_email = qs_email.exclude(pk=perfil.user_id)
            if qs_email.exists():
                errores.append('Ya existe un usuario con ese email.')

        if not nombre:
            errores.append('El nombre es obligatorio.')
        if not apellido:
            errores.append('El apellido es obligatorio.')

        # Password al crear: si está vacío, usa el email como password inicial
        if not perfil and password_nueva:
            try:
                validate_password(password_nueva)
            except DjangoValidationError as e:
                errores.append('Contraseña no válida: ' + ' '.join(e.messages))

        # Password al editar: solo validar si se quiere cambiar
        if perfil and password_nueva:
            try:
                validate_password(password_nueva)
            except DjangoValidationError as e:
                errores.append('Contraseña no válida: ' + ' '.join(e.messages))

        # Fecha de ingreso (opcional)
        fecha_ingreso = None
        if fecha_ingreso_str:
            try:
                from datetime import datetime
                fecha_ingreso = datetime.strptime(fecha_ingreso_str, '%Y-%m-%d').date()
            except ValueError:
                errores.append('Fecha de ingreso inválida.')

        if errores:
            for err in errores:
                messages.error(request, err)
            return render(request, 'staff/gestion/personal_form.html', {
                'perfil': perfil,
                'data': request.POST,
                'es_edicion': bool(perfil),
                'defaults_permisos_por_rol': DEFAULTS_PERMISOS_POR_ROL,
            })

        # ----- Crear o actualizar el User -----
        if perfil and perfil.user_id:
            user = perfil.user
        else:
            user = User()

        user.username = email
        user.email = email
        user.first_name = nombre
        user.last_name = apellido
        user.is_staff = True
        user.is_active = True

        if password_nueva:
            user.set_password(password_nueva)
        elif not user.pk:
            # Crear sin password explícito: usar el email como password inicial
            user.set_password(email)

        user.save()

        # ----- Crear o actualizar el PerfilDocente -----
        es_creacion = not perfil
        rol_anterior = perfil.rol if perfil else None

        if not perfil:
            perfil = PerfilDocente(user=user)
        else:
            perfil.user = user

        perfil.rol = rol
        perfil.titulo = titulo
        perfil.dni = dni
        perfil.telefono = telefono
        perfil.fecha_ingreso = fecha_ingreso
        perfil.observaciones = observaciones

        # Aplicar defaults de permisos por rol:
        # - al crear: siempre.
        # - al editar: solo si cambió el rol respecto a lo que estaba guardado.
        if es_creacion or rol != rol_anterior:
            aplicar_defaults_permisos_por_rol(perfil)

        # Los checkboxes del formulario sobrescriben los defaults aplicados.
        # Si el directivo destildó algo manualmente, respetamos su elección.
        perfil.puede_publicar_institucional = request.POST.get('puede_publicar_institucional') == 'on'
        perfil.puede_administrar_galerias_globales = request.POST.get('puede_administrar_galerias_globales') == 'on'
        perfil.puede_ver_auditoria = request.POST.get('puede_ver_auditoria') == 'on'
        perfil.puede_editar_configuracion_portal = request.POST.get('puede_editar_configuracion_portal') == 'on'
        perfil.puede_administrar_materias_grados = request.POST.get('puede_administrar_materias_grados') == 'on'

        if eliminar_foto:
            perfil.foto = None
        elif nueva_foto:
            perfil.foto = nueva_foto  # la señal pre_save la convierte a webp

        perfil.save()

        es_nuevo = (request.path.endswith('/nuevo/'))
        if es_nuevo:
            messages.success(
                request,
                f'{perfil.get_rol_display()} "{nombre} {apellido}" creado/a. '
                f'Ahora cargale las materias y grados desde la matriz.'
            )
            return redirect('staff:gestion_personal_matriz', pk=perfil.pk)
        else:
            messages.success(request, f'Datos de {nombre} {apellido} actualizados.')
            return redirect('staff:personal_lista')

    return render(request, 'staff/gestion/personal_form.html', {
        'perfil': perfil,
        'data': None,
        'es_edicion': bool(perfil),
        'defaults_permisos_por_rol': DEFAULTS_PERMISOS_POR_ROL,
    })


# ================================================================
# RESETEAR CONTRASEÑA
# ================================================================
@directivo_o_superuser_required
def gestion_personal_reset_password(request, pk):
    perfil = get_object_or_404(PerfilDocente.objects.select_related('user'), pk=pk)
    if not puede_editar_perfil(request.user, perfil):
        messages.error(request, 'No tenés permisos para resetear la contraseña de este usuario.')
        return redirect('staff:personal_lista')
    if request.method == 'POST':
        perfil.user.set_password(PASSWORD_RESET_DEFAULT)
        perfil.user.save(update_fields=['password'])
        registrar_audit(request.user, 'editar', perfil.user, cambios={'accion': 'reset_password'})
        messages.success(
            request,
            f'Contraseña de {perfil.user.first_name} {perfil.user.last_name} reseteada a "{PASSWORD_RESET_DEFAULT}". '
            f'Avisale para que la cambie en su primer ingreso.'
        )
        return redirect('staff:gestion_personal_editar', pk=perfil.pk)

    return render(request, 'staff/gestion/personal_reset_password.html', {
        'perfil': perfil,
        'password_default': PASSWORD_RESET_DEFAULT,
    })


# ================================================================
# ELIMINAR PERSONAL
# ================================================================
@directivo_o_superuser_required
def gestion_personal_eliminar(request, pk):
    perfil = get_object_or_404(PerfilDocente.objects.select_related('user'), pk=pk)
    if not puede_eliminar_perfil(request.user, perfil):
        # Mensaje específico según el caso
        if perfil.user.is_superuser:
            messages.error(request, 'No se puede eliminar al dueño del sistema.')
        elif perfil.user_id == request.user.id:
            messages.error(request, 'No podés eliminarte a vos mismo. Pedile al dueño del sistema que lo haga.')
        else:
            messages.error(request, 'No tenés permisos para eliminar a este usuario.')
        return redirect('staff:personal_lista')

    if request.method == 'POST':
        # Caso especial: el dueño se elimina a sí mismo — exigir confirmación tipeada
        if perfil.user_id == request.user.id and request.user.is_superuser:
            confirmacion = request.POST.get('confirmacion_username', '').strip()
            if confirmacion != request.user.username:
                messages.error(
                    request,
                    'Para auto-eliminarte tenés que escribir tu username exacto en el cuadro de confirmación.'
                )
                return redirect('staff:gestion_personal_eliminar', pk=perfil.pk)

        nombre = f'{perfil.user.first_name} {perfil.user.last_name}'
        # Borrar el User asociado (cascade borra el PerfilDocente y las asignaciones)
        perfil.user.delete()
        messages.success(request, f'{nombre} eliminado/a del sistema.')
        return redirect('staff:personal_lista')

    es_auto_eliminacion = (perfil.user_id == request.user.id and request.user.is_superuser)

    return render(request, 'staff/gestion/personal_eliminar.html', {
        'perfil': perfil,
        'cant_asignaciones': perfil.asignaciones.count(),
        'es_auto_eliminacion': es_auto_eliminacion,
        'username_requerido': request.user.username if es_auto_eliminacion else '',
    })


# ================================================================
# MATRIZ DE ASIGNACIONES (clonada al panel propio)
# ================================================================
@directivo_o_superuser_required
def gestion_personal_matriz(request, pk):
    """Matriz de checkboxes Materias × Grados, igual a la del admin pero en /staff/."""
    perfil = get_object_or_404(PerfilDocente.objects.select_related('user'), pk=pk)
    if not puede_editar_perfil(request.user, perfil):
        messages.error(request, 'No tenés permisos para asignar materias/grados a este usuario.')
        return redirect('staff:personal_lista')
    grados = list(Grado.objects.filter(activo=True).order_by('orden', 'nombre', 'turno'))
    materias = list(Materia.objects.all().order_by('nombre'))
    if request.method == 'POST':
        from django.db import transaction
        seleccionadas = set()
        for clave in request.POST:
            if clave.startswith('cell_g') and '_m' in clave:
                try:
                    resto = clave[len('cell_'):]
                    g_part, m_part = resto.split('_m', 1)
                    grado_id = int(g_part[1:])
                    materia_id = int(m_part)
                    seleccionadas.add((grado_id, materia_id))
                except (ValueError, IndexError):
                    continue

        try:
            with transaction.atomic():
                actuales = set(
                    AsignacionDocente.objects.filter(docente=perfil)
                    .values_list('grado_id', 'materia_id')
                )
                a_crear = seleccionadas - actuales
                a_borrar = actuales - seleccionadas

                cant_b = 0
                for (g, m) in a_borrar:
                    deleted, _ = AsignacionDocente.objects.filter(
                        docente=perfil, grado_id=g, materia_id=m
                    ).delete()
                    cant_b += deleted

                cant_c = 0
                for (g, m) in a_crear:
                    AsignacionDocente.objects.create(docente=perfil, grado_id=g, materia_id=m)
                    cant_c += 1

                total = AsignacionDocente.objects.filter(docente=perfil).count()

            messages.success(
                request,
                f'Asignaciones actualizadas: +{cant_c} · -{cant_b} · Total: {total}'
            )
        except Exception as e:
            messages.error(request, f'Error al guardar: {type(e).__name__}: {e}')

        return redirect('staff:gestion_personal_matriz', pk=pk)

    actuales = set(
        AsignacionDocente.objects.filter(docente=perfil).values_list('grado_id', 'materia_id')
    )
    filas = []
    for grado in grados:
        celdas = []
        for materia in materias:
            celdas.append({
                'materia_id': materia.id,
                'asignada': (grado.id, materia.id) in actuales,
                'clave': f'cell_g{grado.id}_m{materia.id}',
            })
        filas.append({'grado': grado, 'celdas': celdas})

    return render(request, 'staff/gestion/personal_matriz.html', {
        'perfil': perfil,
        'grados': grados,
        'materias': materias,
        'filas': filas,
        'cant_actuales': len(actuales),
    })


# ================================================================
# CONSULTAS DE PADRES (bandeja del docente)
# ================================================================
def _consultas_visibles(user):
    """Queryset de consultas que el usuario puede ver."""
    from comunicacion.models import ConsultaComunicado
    qs = ConsultaComunicado.objects.select_related(
        'comunicado', 'padre'
    ).order_by('-actualizada')
    if user.is_superuser:
        return qs
    return qs.filter(comunicado__autor=user)


@staff_required
def consultas_lista(request):
    """Lista de consultas para el docente (o todas, si es dueño)."""
    perfil = get_perfil_docente(request.user)
    if not request.user.is_superuser and perfil and perfil.rol in ('directivo', 'preceptor'):
        messages.error(request, 'Las consultas las gestiona el docente autor de cada comunicado.')
        return redirect('staff:dashboard')

    consultas = _consultas_visibles(request.user)
    filtro = request.GET.get('estado', '').strip()
    if filtro in ('pendiente', 'respondida'):
        consultas = consultas.filter(estado=filtro)

    consultas = list(consultas)
    for c in consultas:
        c.ultimo_mensaje = c.mensajes.order_by('-creado').first()
        c.cant_mensajes = c.mensajes.count()

    cant_pendientes = _consultas_visibles(request.user).filter(estado='pendiente').count()

    return render(request, 'staff/consultas_lista.html', {
        'consultas': consultas,
        'filtro': filtro,
        'cant_pendientes': cant_pendientes,
        'cant_total': len(consultas),
    })


@staff_required
def consulta_detalle(request, pk):
    """Detalle de un hilo de consulta: responder, cambiar estado, moderar."""
    from comunicacion.models import ConsultaComunicado, MensajeConsulta

    consulta = get_object_or_404(
        ConsultaComunicado.objects.select_related('comunicado', 'padre'),
        pk=pk,
    )

    if not request.user.is_superuser and consulta.comunicado.autor_id != request.user.id:
        messages.error(request, 'No tenés acceso a esta consulta.')
        return redirect('staff:consultas_lista')

    if request.method == 'POST':
        accion = request.POST.get('accion', '')

        if accion == 'responder':
            texto = request.POST.get('texto', '').strip()
            if not texto:
                messages.error(request, 'Escribí una respuesta antes de enviar.')
            else:
                MensajeConsulta.objects.create(
                    consulta=consulta,
                    autor=request.user,
                    es_del_docente=True,
                    texto=texto,
                )
                consulta.estado = 'respondida'
                consulta.save(update_fields=['estado', 'actualizada'])
                # Notificar al padre por email (async, no bloquea)
                from comunicacion.emails import notificar_respuesta_al_padre
                try:
                    notificar_respuesta_al_padre(consulta)
                except Exception:
                    pass
                messages.success(request, 'Respuesta enviada.')
            return redirect('staff:consulta_detalle', pk=pk)

        elif accion == 'cambiar_estado':
            nuevo = request.POST.get('estado', '')
            if nuevo in ('pendiente', 'respondida'):
                consulta.estado = nuevo
                consulta.save(update_fields=['estado', 'actualizada'])
                messages.success(request, f'Estado cambiado a "{nuevo}".')
            return redirect('staff:consulta_detalle', pk=pk)

        elif accion == 'eliminar_mensaje':
            msg_id = request.POST.get('mensaje_id', '')
            MensajeConsulta.objects.filter(id=msg_id, consulta=consulta).update(eliminado=True)
            messages.success(request, 'Mensaje eliminado.')
            return redirect('staff:consulta_detalle', pk=pk)

        elif accion == 'eliminar_hilo':
            consulta.delete()
            messages.success(request, 'Conversación eliminada por completo.')
            return redirect('staff:consultas_lista')

    mensajes_hilo = consulta.mensajes.select_related('autor').order_by('creado')

    # Marcar que el docente leyó este hilo
    from django.utils import timezone
    consulta.docente_leyo = timezone.now()
    consulta.save(update_fields=['docente_leyo'])

    # Hijos del padre en los grados de este comunicado (para que el docente
    # sepa de qué alumno se trata). Solo los que tienen nombre cargado.
    hijos_del_padre = []
    perfil_padre = getattr(consulta.padre, 'perfil_padre', None)
    if perfil_padre is not None:
        grados_ids = list(consulta.comunicado.grados.values_list('id', flat=True))
        if grados_ids:
            hijos_del_padre = list(
                perfil_padre.hijos
                .filter(grado_id__in=grados_ids)
                .exclude(nombre='')
                .select_related('grado')
            )

    return render(request, 'staff/consulta_detalle.html', {
        'consulta': consulta,
        'mensajes_hilo': mensajes_hilo,
        'hijos_del_padre': hijos_del_padre,
    })


# ================================================================
# MENSAJERIA INTERNA DEL STAFF
# ================================================================
def _nombre_conversacion(conversacion, para_usuario):
    """Devuelve el nombre a mostrar: el del grupo, o el del otro participante."""
    if conversacion.tipo == 'grupo':
        return conversacion.nombre or 'Grupo sin nombre'
    otro = (
        conversacion.miembros
        .exclude(usuario=para_usuario)
        .select_related('usuario')
        .first()
    )
    if otro:
        return otro.usuario.get_full_name() or otro.usuario.username
    return 'Conversación'


@staff_required
def mensajes_lista(request):
    """Lista de conversaciones del usuario."""
    from comunicacion.models import MiembroConversacion

    membresias = (
        MiembroConversacion.objects
        .filter(usuario=request.user, activo=True)
        .select_related('conversacion')
        .order_by('-conversacion__actualizada')
    )

    conversaciones = []
    for m in membresias:
        conv = m.conversacion
        ultimo = conv.mensajes.order_by('-creado').first()
        # Contar no leídos: mensajes después de la última lectura, de otros autores
        qs_nuevos = conv.mensajes.exclude(autor=request.user)
        if m.ultima_lectura:
            qs_nuevos = qs_nuevos.filter(creado__gt=m.ultima_lectura)
        no_leidos = qs_nuevos.count()

        conversaciones.append({
            'conv': conv,
            'nombre': _nombre_conversacion(conv, request.user),
            'ultimo': ultimo,
            'no_leidos': no_leidos,
        })

    return render(request, 'staff/mensajes_lista.html', {
        'conversaciones': conversaciones,
    })


@staff_required
def mensaje_conversacion(request, pk):
    """Ver una conversación: hilo de mensajes + escribir."""
    from django.utils import timezone
    from comunicacion.models import Conversacion, MiembroConversacion, MensajeInterno

    conversacion = get_object_or_404(Conversacion, pk=pk)

    # Verificar que el usuario sea miembro activo
    membresia = MiembroConversacion.objects.filter(
        conversacion=conversacion,
        usuario=request.user,
        activo=True,
    ).first()
    if membresia is None:
        messages.error(request, 'No tenés acceso a esta conversación.')
        return redirect('staff:mensajes_lista')

    if request.method == 'POST':
        accion = request.POST.get('accion', 'enviar')

        if accion == 'enviar':
            texto = request.POST.get('texto', '').strip()
            if texto:
                nuevo_msg = MensajeInterno.objects.create(
                    conversacion=conversacion,
                    autor=request.user,
                    texto=texto,
                )
                conversacion.save(update_fields=['actualizada'])
                # Notificar por email a quienes lo tengan activado (async)
                from comunicacion.emails import notificar_mensaje_interno
                try:
                    notificar_mensaje_interno(nuevo_msg)
                except Exception:
                    pass
            return redirect('staff:mensaje_conversacion', pk=pk)

        elif accion == 'eliminar_mensaje':
            msg_id = request.POST.get('mensaje_id', '')
            # Solo puede borrar SUS PROPIOS mensajes
            MensajeInterno.objects.filter(
                id=msg_id,
                conversacion=conversacion,
                autor=request.user,
            ).update(eliminado=True)
            return redirect('staff:mensaje_conversacion', pk=pk)

        elif accion == 'salir_grupo':
            if conversacion.tipo == 'grupo':
                membresia.activo = False
                membresia.save(update_fields=['activo'])
                messages.success(request, 'Saliste del grupo.')
            return redirect('staff:mensajes_lista')

    # Marcar como leído (actualizar ultima_lectura)
    membresia.ultima_lectura = timezone.now()
    membresia.save(update_fields=['ultima_lectura'])

    mensajes_hilo = conversacion.mensajes.select_related('autor').order_by('creado')
    miembros = (
        conversacion.miembros
        .filter(activo=True)
        .select_related('usuario')
    )

    return render(request, 'staff/mensaje_conversacion.html', {
        'conversacion': conversacion,
        'nombre_conv': _nombre_conversacion(conversacion, request.user),
        'mensajes_hilo': mensajes_hilo,
        'miembros': miembros,
        'es_grupo': conversacion.tipo == 'grupo',
        'soy_creador': conversacion.creador_id == request.user.id,
    })


@staff_required
def mensaje_nuevo(request):
    """Crear una conversación nueva: directa (1 a 1) o grupo."""
    from django.contrib.auth.models import User
    from comunicacion.models import Conversacion, MiembroConversacion
    from .permissions import staff_contactable_qs

    contactables = staff_contactable_qs(request.user)

    if request.method == 'POST':
        tipo = request.POST.get('tipo', 'directa')

        if tipo == 'directa':
            otro_id = request.POST.get('usuario', '')
            otro = contactables.filter(pk=otro_id).first()
            if otro is None:
                messages.error(request, 'Elegí una persona válida para conversar.')
                return redirect('staff:mensaje_nuevo')

            # ¿Ya existe una conversación directa entre estos dos?
            existente = (
                Conversacion.objects
                .filter(tipo='directa', miembros__usuario=request.user)
                .filter(miembros__usuario=otro)
                .first()
            )
            if existente:
                return redirect('staff:mensaje_conversacion', pk=existente.pk)

            conv = Conversacion.objects.create(tipo='directa', creador=request.user)
            MiembroConversacion.objects.create(conversacion=conv, usuario=request.user)
            MiembroConversacion.objects.create(conversacion=conv, usuario=otro)
            return redirect('staff:mensaje_conversacion', pk=conv.pk)

        elif tipo == 'grupo':
            nombre = request.POST.get('nombre', '').strip()[:120]
            miembros_ids = request.POST.getlist('miembros')
            if not nombre:
                messages.error(request, 'Poné un nombre al grupo.')
                return redirect('staff:mensaje_nuevo')
            if not miembros_ids:
                messages.error(request, 'Elegí al menos un miembro para el grupo.')
                return redirect('staff:mensaje_nuevo')

            # Filtrar solo los miembros válidos según permisos
            miembros_validos = list(contactables.filter(pk__in=miembros_ids))

            conv = Conversacion.objects.create(
                tipo='grupo',
                nombre=nombre,
                creador=request.user,
            )
            # El creador siempre es miembro
            MiembroConversacion.objects.create(conversacion=conv, usuario=request.user)
            for u in miembros_validos:
                MiembroConversacion.objects.get_or_create(conversacion=conv, usuario=u)
            messages.success(request, f'Grupo "{nombre}" creado.')
            return redirect('staff:mensaje_conversacion', pk=conv.pk)

    return render(request, 'staff/mensaje_nuevo.html', {
        'contactables': contactables,
    })


@staff_required
def mensaje_gestionar_miembros(request, pk):
    """El creador del grupo agrega o saca miembros."""
    from comunicacion.models import Conversacion, MiembroConversacion
    from .permissions import staff_contactable_qs

    conversacion = get_object_or_404(Conversacion, pk=pk, tipo='grupo')

    # Solo el creador gestiona miembros
    if conversacion.creador_id != request.user.id:
        messages.error(request, 'Solo quien creó el grupo puede gestionar los miembros.')
        return redirect('staff:mensaje_conversacion', pk=pk)

    contactables = staff_contactable_qs(request.user)

    if request.method == 'POST':
        accion = request.POST.get('accion', '')

        if accion == 'agregar':
            nuevo_id = request.POST.get('usuario', '')
            nuevo = contactables.filter(pk=nuevo_id).first()
            if nuevo:
                miembro, creado = MiembroConversacion.objects.get_or_create(
                    conversacion=conversacion,
                    usuario=nuevo,
                )
                if not creado and not miembro.activo:
                    miembro.activo = True
                    miembro.save(update_fields=['activo'])
                messages.success(request, 'Miembro agregado al grupo.')
            return redirect('staff:mensaje_gestionar_miembros', pk=pk)

        elif accion == 'sacar':
            sacar_id = request.POST.get('usuario', '')
            # No puede sacarse a sí mismo por acá (para eso está "salir del grupo")
            if str(sacar_id) != str(request.user.id):
                MiembroConversacion.objects.filter(
                    conversacion=conversacion,
                    usuario_id=sacar_id,
                ).update(activo=False)
                messages.success(request, 'Miembro sacado del grupo.')
            return redirect('staff:mensaje_gestionar_miembros', pk=pk)

    miembros_actuales = (
        conversacion.miembros
        .filter(activo=True)
        .select_related('usuario')
    )
    ids_actuales = set(miembros_actuales.values_list('usuario_id', flat=True))
    disponibles = contactables.exclude(pk__in=ids_actuales)

    return render(request, 'staff/mensaje_miembros.html', {
        'conversacion': conversacion,
        'miembros_actuales': miembros_actuales,
        'disponibles': disponibles,
    })


@staff_required
def mensaje_conversacion_json(request, pk):
    """
    Endpoint JSON para polling: devuelve los mensajes de la conversación.
    Acepta ?desde=<id> para devolver solo mensajes con id mayor a ese.
    """
    from django.http import JsonResponse
    from django.utils import timezone
    from comunicacion.models import Conversacion, MiembroConversacion

    conversacion = get_object_or_404(Conversacion, pk=pk)

    membresia = MiembroConversacion.objects.filter(
        conversacion=conversacion,
        usuario=request.user,
        activo=True,
    ).first()
    if membresia is None:
        return JsonResponse({'error': 'sin_acceso'}, status=403)

    qs = conversacion.mensajes.select_related('autor').order_by('creado')
    desde = request.GET.get('desde', '')
    if desde.isdigit():
        qs = qs.filter(id__gt=int(desde))

    es_grupo = conversacion.tipo == 'grupo'
    data = []
    for m in qs:
        data.append({
            'id': m.id,
            'texto': '' if m.eliminado else m.texto,
            'eliminado': m.eliminado,
            'es_mio': m.autor_id == request.user.id,
            'autor': m.autor.get_full_name() or m.autor.username,
            'hora': timezone.localtime(m.creado).strftime('%d/%m %H:%M'),
        })

    # Actualizar última lectura
    membresia.ultima_lectura = timezone.now()
    membresia.save(update_fields=['ultima_lectura'])

    return JsonResponse({'mensajes': data, 'es_grupo': es_grupo})


@staff_required
def notificaciones_json(request):
    """
    Endpoint JSON para la campanita de notificaciones.
    Devuelve dos listas separadas: consultas pendientes y mensajes internos
    no leídos. Lee datos ya existentes, no usa una tabla aparte.
    """
    from django.http import JsonResponse
    from django.utils import timezone
    from comunicacion.models import ConsultaComunicado, MiembroConversacion

    # --- Consultas con mensajes nuevos del padre sin leer por el docente ---
    consultas_qs = ConsultaComunicado.objects.select_related(
        'comunicado', 'padre'
    ).order_by('-actualizada')
    if not request.user.is_superuser:
        consultas_qs = consultas_qs.filter(comunicado__autor=request.user)

    consultas = []
    for c in consultas_qs:
        ultimo_padre = c.mensajes.filter(es_del_docente=False).order_by('-creado').first()
        if ultimo_padre is None:
            continue
        # Solo cuenta si el docente no abrió el hilo después de ese mensaje
        if c.docente_leyo is not None and ultimo_padre.creado <= c.docente_leyo:
            continue
        consultas.append({
            'id': c.id,
            'padre': c.padre.get_full_name() or c.padre.username,
            'comunicado': c.comunicado.titulo,
            'hora': timezone.localtime(ultimo_padre.creado).strftime('%d/%m %H:%M'),
            'url': f'/staff/consultas/{c.id}/',
        })
        if len(consultas) >= 15:
            break

    # --- Mensajes internos no leídos ---
    mensajes = []
    membresias = (
        MiembroConversacion.objects
        .filter(usuario=request.user, activo=True)
        .select_related('conversacion')
    )
    for m in membresias:
        conv = m.conversacion
        nuevos_qs = conv.mensajes.exclude(autor=request.user)
        if m.ultima_lectura:
            nuevos_qs = nuevos_qs.filter(creado__gt=m.ultima_lectura)
        cant = nuevos_qs.count()
        if cant > 0:
            ultimo = nuevos_qs.select_related('autor').order_by('-creado').first()
            if conv.tipo == 'grupo':
                titulo = conv.nombre or 'Grupo'
            else:
                titulo = ultimo.autor.get_full_name() or ultimo.autor.username
            mensajes.append({
                'conv_id': conv.id,
                'titulo': titulo,
                'cantidad': cant,
                'hora': timezone.localtime(ultimo.creado).strftime('%d/%m %H:%M'),
                'url': f'/staff/mensajes/{conv.id}/',
            })

    total = len(consultas) + sum(x['cantidad'] for x in mensajes)

    return JsonResponse({
        'total': total,
        'consultas': consultas,
        'mensajes': mensajes,
    })
