from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import MisGradosForm, RegistroPadreForm
from .models import (
    Comunicado,
    ConfiguracionPortal,
    Galeria,
    Grado,
    HijoPadre,
    Materia,
    NOTIF_PADRE_CHOICES,
    PerfilDocente,
    PerfilPadre,
    TURNO_CHOICES,
)


def landing_view(request):
    """Pagina principal: primero selector de turno, despues los grados de ese turno."""
    config = ConfiguracionPortal.objects.first()
    turno_seleccionado = request.GET.get('turno', '').strip().lower()
    etiquetas_turno = dict(TURNO_CHOICES)
    iconos_turno = {'manana': '☀️', 'tarde': '🌅', 'vespertino': '🌙'}
    descripciones_turno = {
        'manana': 'Aulas del turno mañana',
        'tarde': 'Aulas del turno tarde',
        'vespertino': 'Aulas del turno vespertino',
    }

    todos_grados = list(Grado.objects.filter(activo=True).order_by('orden', 'nombre'))

    # Lista de turnos disponibles con cantidad de grados activos en cada uno
    turnos_disponibles = []
    for cod, etiqueta in TURNO_CHOICES:
        grados_del_turno = [g for g in todos_grados if g.turno == cod]
        if grados_del_turno:
            turnos_disponibles.append({
                'codigo': cod,
                'etiqueta': etiqueta,
                'icono': iconos_turno.get(cod, ''),
                'descripcion': descripciones_turno.get(cod, ''),
                'cantidad': len(grados_del_turno),
            })

    # Si hay un turno seleccionado y existe, filtrar los grados
    grados_filtrados = []
    turno_actual = None
    if turno_seleccionado:
        for t in turnos_disponibles:
            if t['codigo'] == turno_seleccionado:
                turno_actual = t
                grados_filtrados = [g for g in todos_grados if g.turno == turno_seleccionado]
                break

    return render(request, 'comunicacion/landing.html', {
        'config': config,
        'turnos_disponibles': turnos_disponibles,
        'turno_actual': turno_actual,
        'grados_filtrados': grados_filtrados,
    })


def muro_grado_view(request, grado_slug):
    grado = get_object_or_404(Grado, slug=grado_slug, activo=True)

    from django.utils import timezone
    hoy = timezone.localdate()

    qs_base = (Comunicado.objects
               .filter(grados=grado, activo=True)
               .prefetch_related('imagenes')
               .distinct())

    # Excluir vencidos que tienen ocultar_al_vencer=True
    qs_visibles = qs_base.exclude(
        ocultar_al_vencer=True,
        fecha_vencimiento__lt=hoy,
    )

    # Aplicar filtro por chip si vino en GET
    chip = request.GET.get('chip', '').strip()
    if chip == 'urgentes':
        qs_visibles = qs_visibles.filter(urgente=True)
    elif chip == 'tareas':
        qs_visibles = qs_visibles.filter(tipo='tarea')
    elif chip == 'eventos':
        qs_visibles = qs_visibles.filter(tipo='evento')

    # Filtro por materia
    materia_id = request.GET.get('materia', '').strip()
    if materia_id.isdigit():
        qs_visibles = qs_visibles.filter(materia_id=int(materia_id))

    # Búsqueda
    busqueda = request.GET.get('q', '').strip()
    if busqueda:
        qs_visibles = qs_visibles.filter(Q(titulo__icontains=busqueda) | Q(contenido__icontains=busqueda))

    # Separar: vencidos visibles van al final
    activos = qs_visibles.filter(
        Q(fecha_vencimiento__isnull=True) | Q(fecha_vencimiento__gte=hoy)
    ).order_by('-fijado', '-fecha_publicacion')

    vencidos_visibles = qs_visibles.filter(
        fecha_vencimiento__lt=hoy,
        ocultar_al_vencer=False,
    ).order_by('-fecha_publicacion')

    comunicados = list(activos) + list(vencidos_visibles)

    # Materias usadas en este grado (para el filtro)
    materias_grado = Materia.objects.filter(comunicado__grados=grado).distinct().order_by('nombre')

    galerias = (Galeria.objects
                .filter(grados=grado, activa=True)
                .prefetch_related('fotos')
                .order_by('-fecha_evento'))
    cant_galerias = Galeria.objects.filter(grados=grado, activa=True).count()
    return render(request, 'comunicacion/muro.html', {
        'grado': grado,
        'comunicados': comunicados,
        'galerias': galerias,
        'cant_galerias': cant_galerias,
        'chip': chip,
        'materia_id': materia_id,
        'busqueda': busqueda,
        'materias_grado': materias_grado,
    })


def registro_padre_view(request):
    """Registro público de padres."""
    if request.user.is_authenticated:
        return redirect('comunicacion:landing')

    if request.method == 'POST':
        form = RegistroPadreForm(request.POST)
        if form.is_valid():
            user, perfil = form.save()
            # Auto-login
            user_auth = authenticate(
                request,
                username=user.username,
                password=form.cleaned_data['password1']
            )
            if user_auth is not None:
                auth_login(request, user_auth)
                grados_lista = ', '.join(str(g) for g in perfil.hijos_grados.all())
                messages.success(
                    request,
                    f'¡Bienvenido/a, {user.first_name}! Ahora seguís: {grados_lista}'
                )
                return redirect('comunicacion:landing')
    else:
        form = RegistroPadreForm()

    return render(request, 'comunicacion/registro.html', {'form': form})


def login_padre_view(request):
    """Login para padres (también funciona para docentes/staff)."""
    if request.user.is_authenticated:
        return redirect('comunicacion:landing')

    error = None
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')

        # Buscar el usuario por email (case-insensitive)
        user_obj = User.objects.filter(email__iexact=email).first()
        if user_obj:
            user_auth = authenticate(request, username=user_obj.username, password=password)
            if user_auth is not None:
                auth_login(request, user_auth)
                if user_auth.is_staff:
                    messages.success(
                        request,
                        f'¡Hola, {user_auth.first_name or user_auth.username}! Te llevamos al panel del personal.'
                    )
                    return redirect('staff:dashboard')
                messages.success(request, f'¡Hola, {user_auth.first_name or user_auth.username}!')
                return redirect('comunicacion:landing')
            else:
                error = 'Contraseña incorrecta.'
        else:
            error = 'No existe una cuenta con ese correo.'

    return render(request, 'comunicacion/login.html', {'error': error})


def logout_view(request):
    """Cierra sesión y vuelve a la landing."""
    auth_logout(request)
    messages.info(request, 'Sesión cerrada. ¡Hasta pronto!')
    return redirect('comunicacion:landing')


@login_required(login_url='comunicacion:login_padre')
def mis_grados_view(request):
    """Permite al padre cambiar los grados que sigue."""
    try:
        perfil = request.user.perfil_padre
    except PerfilPadre.DoesNotExist:
        messages.error(request, 'Esta sección es solo para padres registrados.')
        return redirect('comunicacion:landing')

    if request.method == 'POST':
        form = MisGradosForm(request.POST)
        if form.is_valid():
            grados_nuevos = form.cleaned_data['grados']
            perfil.hijos_grados.set(grados_nuevos)
            # Sincronizar HijoPadre con los grados elegidos
            from .models import HijoPadre
            HijoPadre.objects.filter(padre=perfil).exclude(grado__in=grados_nuevos).delete()
            for g in grados_nuevos:
                HijoPadre.objects.get_or_create(padre=perfil, grado=g, defaults={'nombre': 'Hijo/a'})
            messages.success(request, 'Grados actualizados correctamente.')
            return redirect('comunicacion:mis_grados')
    else:
        form = MisGradosForm(initial={'grados': perfil.hijos_grados.values_list('pk', flat=True)})

    return render(request, 'comunicacion/mis_grados.html', {'form': form, 'perfil': perfil})


# ====================================================================
# RECUPERACIÓN DE CONTRASEÑA (unificada para padres y staff)
# ====================================================================
from .emails import (
    enviar_email_template,
    generar_token_padre,
    verificar_token_padre,
)


def recuperar_clave_solicitar_view(request):
    """
    Pantalla 1: el usuario ingresa su email.
    Si existe un User con ese email, le mandamos un link con token.
    Mostramos siempre el mismo mensaje, exista o no, por seguridad.
    """
    if request.user.is_authenticated:
        return redirect('comunicacion:landing')

    enviado = False
    error = None

    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        if not email or '@' not in email:
            error = 'Ingresá un email válido.'
        else:
            user_obj = User.objects.filter(email__iexact=email, is_active=True).first()
            if user_obj:
                token = generar_token_padre(user_obj.id, accion='reset')
                link = request.build_absolute_uri(
                    reverse('comunicacion:recuperar_clave_confirmar', args=[token])
                )
                nombre = user_obj.first_name or user_obj.username
                enviar_email_template(
                    subject='Recuperá tu contraseña — Portal Escolar',
                    template_name='emails/recuperar_clave.html',
                    contexto={
                        'nombre': nombre,
                        'link_recuperacion': link,
                        'user': user_obj,
                    },
                    to_emails=user_obj.email,
                )
            # Mensaje genérico SIEMPRE (no revelamos si existe o no)
            enviado = True

    return render(request, 'comunicacion/recuperar_clave_solicitar.html', {
        'enviado': enviado,
        'error': error,
    })


def recuperar_clave_confirmar_view(request, token):
    """
    Pantalla 2: el usuario llega desde el link del email.
    Verificamos token, dejamos que ponga nueva clave, lo logueamos.
    """
    user_id = verificar_token_padre(token, accion='reset', max_age_seconds=86400)
    if not user_id:
        return render(request, 'comunicacion/recuperar_clave_invalido.html')

    try:
        user_obj = User.objects.get(pk=user_id, is_active=True)
    except User.DoesNotExist:
        return render(request, 'comunicacion/recuperar_clave_invalido.html')

    error = None

    if request.method == 'POST':
        nueva = request.POST.get('password_nueva', '')
        repetir = request.POST.get('password_repetir', '')

        if len(nueva) < 6:
            error = 'La contraseña debe tener al menos 6 caracteres.'
        elif nueva != repetir:
            error = 'Las contraseñas no coinciden.'
        else:
            user_obj.set_password(nueva)
            user_obj.save()
            # Auto-login después del cambio
            user_auth = authenticate(
                request,
                username=user_obj.username,
                password=nueva,
            )
            if user_auth is not None:
                auth_login(request, user_auth)
                messages.success(request, 'Contraseña actualizada. ¡Bienvenido/a!')
                # Redirigir según rol
                if user_auth.is_staff:
                    return redirect('staff:dashboard')
                return redirect('comunicacion:landing')
            else:
                error = 'No pudimos iniciar sesión. Probá ingresar manualmente.'

    return render(request, 'comunicacion/recuperar_clave_confirmar.html', {
        'user_obj': user_obj,
        'token': token,
        'error': error,
    })


def comunicado_detalle_view(request, pk):
    """Detalle público de un comunicado activo."""
    comunicado = get_object_or_404(
        Comunicado.objects.select_related('autor', 'materia').prefetch_related('imagenes', 'grados'),
        pk=pk,
        activo=True,
    )

    # Incremento de vistas sin condiciones para mantenerlo simple y consistente con el muro publico.
    Comunicado.objects.filter(pk=comunicado.pk).update(vistas=F('vistas') + 1)
    comunicado.refresh_from_db(fields=['vistas'])

    # Grado de referencia para ofrecer boton de volver al muro.
    grado_muro = comunicado.grados.order_by('orden', 'nombre').first()

    return render(request, 'comunicacion/comunicado_detalle.html', {
        'comunicado': comunicado,
        'grado_muro': grado_muro,
    })


def _padre_tiene_acceso_a_grado(user, grado):
    """True si el user es padre registrado y tiene hijos en ese grado."""
    if not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    try:
        perfil_padre = getattr(user, 'perfil_padre', None) or getattr(user, 'perfilpadre', None)
        if perfil_padre is None:
            return False
        return perfil_padre.hijos_grados.filter(pk=grado.pk).exists()
    except Exception:
        return False


def galerias_grado_view(request, grado_slug):
    """Listado de galerías de un grado. Solo accesible para padres del grado o staff."""
    grado = get_object_or_404(Grado, slug=grado_slug, activo=True)

    if not request.user.is_authenticated:
        return render(request, 'comunicacion/galerias_acceso_restringido.html', {
            'grado': grado,
            'motivo': 'no_logueado',
        })

    if not _padre_tiene_acceso_a_grado(request.user, grado):
        return render(request, 'comunicacion/galerias_acceso_restringido.html', {
            'grado': grado,
            'motivo': 'sin_hijo_en_grado',
        })

    galerias = (
        Galeria.objects
        .filter(grados=grado, activa=True)
        .prefetch_related('fotos')
        .order_by('-fecha_evento')
    )

    return render(request, 'comunicacion/galerias_grado.html', {
        'grado': grado,
        'galerias': galerias,
    })


def galeria_detalle_publica_view(request, pk):
    """Detalle de una galería con todas las fotos en grilla + lightbox."""
    galeria = get_object_or_404(Galeria, pk=pk, activa=True)

    if not request.user.is_authenticated:
        return render(request, 'comunicacion/galerias_acceso_restringido.html', {
            'galeria': galeria,
            'motivo': 'no_logueado',
        })

    if not request.user.is_staff:
        try:
            perfil_padre = getattr(request.user, 'perfil_padre', None) or getattr(request.user, 'perfilpadre', None)
            tiene_acceso = bool(perfil_padre and perfil_padre.hijos_grados.filter(
                pk__in=galeria.grados.values_list('pk', flat=True)
            ).exists())
        except Exception:
            tiene_acceso = False

        if not tiene_acceso:
            return render(request, 'comunicacion/galerias_acceso_restringido.html', {
                'galeria': galeria,
                'motivo': 'sin_hijo_en_grado',
            })

    fotos = galeria.fotos.all().order_by('orden', 'id')
    return render(request, 'comunicacion/galeria_detalle_publica.html', {
        'galeria': galeria,
        'fotos': fotos,
    })


# ====================================================================
# MI CUENTA DEL PADRE
# ====================================================================
@login_required(login_url='comunicacion:login_padre')
def mi_cuenta_padre_view(request):
    """Página principal donde el padre edita sus datos, hijos y notificaciones."""
    try:
        perfil = request.user.perfil_padre
    except PerfilPadre.DoesNotExist:
        messages.error(request, 'Esta sección es solo para padres registrados.')
        return redirect('comunicacion:landing')

    if request.method == 'POST':
        # Datos personales
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        if not first_name or not last_name:
            messages.error(request, 'Nombre y apellido son obligatorios.')
            return redirect('comunicacion:mi_cuenta')

        request.user.first_name = first_name
        request.user.last_name = last_name
        request.user.save(update_fields=['first_name', 'last_name'])

        # Datos del perfil
        perfil.telefono = request.POST.get('telefono', '').strip()[:30]
        perfil.dni = request.POST.get('dni', '').strip()[:20]

        tipo_notif = request.POST.get('tipo_notificacion', 'todos')
        if tipo_notif in dict(NOTIF_PADRE_CHOICES):
            perfil.tipo_notificacion = tipo_notif

        nueva_foto = request.FILES.get('foto')
        if nueva_foto:
            perfil.foto = nueva_foto

        perfil.save()
        messages.success(request, 'Datos actualizados correctamente.')
        return redirect('comunicacion:mi_cuenta')

    hijos = perfil.hijos.select_related('grado').order_by('nombre')
    return render(request, 'comunicacion/mi_cuenta.html', {
        'perfil': perfil,
        'hijos': hijos,
        'opciones_notif': NOTIF_PADRE_CHOICES,
    })


@login_required(login_url='comunicacion:login_padre')
def hijo_crear_view(request):
    """Alta de un hijo del padre logueado."""
    try:
        perfil = request.user.perfil_padre
    except PerfilPadre.DoesNotExist:
        return redirect('comunicacion:landing')

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()[:100]
        grado_id = request.POST.get('grado', '').strip()
        if not nombre or not grado_id.isdigit():
            messages.error(request, 'Nombre y grado son obligatorios.')
        else:
            try:
                grado = Grado.objects.get(pk=int(grado_id), activo=True)
                HijoPadre.objects.create(padre=perfil, nombre=nombre, grado=grado)
                messages.success(request, f'{nombre} agregado correctamente.')
                return redirect('comunicacion:mi_cuenta')
            except Grado.DoesNotExist:
                messages.error(request, 'El grado seleccionado no existe.')

    grados = Grado.objects.filter(activo=True).order_by('orden', 'nombre')
    return render(request, 'comunicacion/hijo_form.html', {
        'grados': grados,
        'es_edicion': False,
    })


@login_required(login_url='comunicacion:login_padre')
def hijo_editar_view(request, pk):
    """Edición de un hijo (solo si pertenece al padre logueado)."""
    try:
        perfil = request.user.perfil_padre
    except PerfilPadre.DoesNotExist:
        return redirect('comunicacion:landing')

    hijo = get_object_or_404(HijoPadre, pk=pk, padre=perfil)

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()[:100]
        grado_id = request.POST.get('grado', '').strip()
        if not nombre or not grado_id.isdigit():
            messages.error(request, 'Nombre y grado son obligatorios.')
        else:
            try:
                grado = Grado.objects.get(pk=int(grado_id), activo=True)
                hijo.nombre = nombre
                hijo.grado = grado
                hijo.save()
                messages.success(request, 'Datos actualizados.')
                return redirect('comunicacion:mi_cuenta')
            except Grado.DoesNotExist:
                messages.error(request, 'El grado seleccionado no existe.')

    grados = Grado.objects.filter(activo=True).order_by('orden', 'nombre')
    return render(request, 'comunicacion/hijo_form.html', {
        'hijo': hijo,
        'grados': grados,
        'es_edicion': True,
    })


@login_required(login_url='comunicacion:login_padre')
def hijo_eliminar_view(request, pk):
    """Baja de un hijo (con confirmación)."""
    try:
        perfil = request.user.perfil_padre
    except PerfilPadre.DoesNotExist:
        return redirect('comunicacion:landing')

    hijo = get_object_or_404(HijoPadre, pk=pk, padre=perfil)

    if request.method == 'POST':
        nombre = hijo.nombre
        hijo.delete()
        messages.success(request, f'{nombre} fue eliminado.')
        return redirect('comunicacion:mi_cuenta')

    return render(request, 'comunicacion/hijo_eliminar.html', {'hijo': hijo})


# ====================================================================
# DESUSCRIPCIÓN POR EMAIL (sin login)
# ====================================================================
def desuscribirme_view(request, token):
    """
    Link público desde el footer del email. Apaga las notificaciones
    del padre sin pedirle login. Token NO expira (max_age_seconds=None).
    """
    user_id = verificar_token_padre(token, accion='unsub', max_age_seconds=None)
    if not user_id:
        return render(request, 'comunicacion/desuscribirme_invalido.html')

    try:
        user_obj = User.objects.get(pk=user_id, is_active=True)
        perfil = user_obj.perfil_padre
    except (User.DoesNotExist, PerfilPadre.DoesNotExist):
        return render(request, 'comunicacion/desuscribirme_invalido.html')

    if request.method == 'POST':
        perfil.tipo_notificacion = 'ninguno'
        perfil.notif_email = False
        perfil.save(update_fields=['tipo_notificacion', 'notif_email'])
        return render(request, 'comunicacion/desuscribirme_ok.html', {
            'perfil': perfil,
        })

    return render(request, 'comunicacion/desuscribirme_confirmar.html', {
        'perfil': perfil,
        'token': token,
    })


# ====================================================================
# CONSULTAS DE PADRES SOBRE COMUNICADOS
# ====================================================================
@login_required(login_url='comunicacion:login_padre')
def consulta_hilo_view(request, pk):
    """
    Hilo de consulta de un padre sobre un comunicado.
    - Si el padre no tiene hilo aun sobre este comunicado, lo crea al primer mensaje.
    - Muestra el hilo completo y permite agregar mensajes.
    - Solo accesible para padres registrados (con perfil_padre).
    """
    from .models import ConsultaComunicado, MensajeConsulta

    comunicado = get_object_or_404(Comunicado, pk=pk, activo=True, archivado=False)

    # Verificar que sea un padre registrado
    perfil_padre = getattr(request.user, 'perfil_padre', None)
    if perfil_padre is None:
        messages.error(request, 'Las consultas son solo para familias registradas.')
        return redirect('comunicacion:comunicado_detalle', pk=pk)

    # Buscar el hilo existente de este padre sobre este comunicado
    consulta = ConsultaComunicado.objects.filter(
        comunicado=comunicado,
        padre=request.user,
    ).first()

    if request.method == 'POST':
        texto = request.POST.get('texto', '').strip()
        if not texto:
            messages.error(request, 'Escribi tu consulta antes de enviar.')
        else:
            # Crear el hilo si todavia no existe
            if consulta is None:
                consulta = ConsultaComunicado.objects.create(
                    comunicado=comunicado,
                    padre=request.user,
                    estado='pendiente',
                )
            # Si el hilo estaba archivado, no permitir escribir
            if consulta.archivada:
                messages.error(request, 'Esta consulta esta archivada. No se pueden enviar mas mensajes.')
                return redirect('comunicacion:consulta_hilo', pk=pk)

            MensajeConsulta.objects.create(
                consulta=consulta,
                autor=request.user,
                es_del_docente=False,
                texto=texto,
            )
            # Al escribir el padre, el hilo vuelve a pendiente
            consulta.estado = 'pendiente'
            consulta.save(update_fields=['estado', 'actualizada'])
            messages.success(request, 'Tu consulta fue enviada al docente.')
            return redirect('comunicacion:consulta_hilo', pk=pk)

    mensajes_hilo = []
    if consulta is not None:
        mensajes_hilo = consulta.mensajes.select_related('autor').order_by('creado')

    return render(request, 'comunicacion/consulta_hilo.html', {
        'comunicado': comunicado,
        'consulta': consulta,
        'mensajes_hilo': mensajes_hilo,
    })