"""
Helpers de permisos para el panel staff.

es_staff_panel: requiere user.is_staff (todos los docentes lo son)
get_perfil_docente: retorna el PerfilDocente del usuario logueado o None
es_directivo_o_preceptor: True si el rol es preceptor/directivo
"""

from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from comunicacion.models import PerfilDocente


def get_perfil_docente(user):
    if not user.is_authenticated:
        return None
    try:
        return user.perfil_docente
    except PerfilDocente.DoesNotExist:
        return None


def es_directivo_o_preceptor(user):
    perfil = get_perfil_docente(user)
    return perfil is not None and perfil.rol in ('preceptor', 'directivo')


def staff_required(view_func):
    """
    Solo permite acceso a usuarios is_staff.
    - Superusers: acceso libre, no requieren PerfilDocente.
    - Otros: requieren PerfilDocente válido (rol docente/preceptor/directivo).
    """

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('staff:login')
        if not request.user.is_staff:
            messages.error(request, 'Esta sección es solo para personal de la escuela.')
            return redirect('comunicacion:landing')
        # Superusers entran sin PerfilDocente
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        # Resto: requieren PerfilDocente
        if get_perfil_docente(request.user) is None:
            messages.error(request, 'Tu cuenta no tiene un perfil docente asociado. Contactá al director.')
            return redirect('staff:login')
        return view_func(request, *args, **kwargs)

    return _wrapped


def directivo_o_preceptor_required(view_func):
    """Solo permite acceso a preceptores y directivos."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            return redirect('staff:login')
        if not es_directivo_o_preceptor(request.user):
            messages.error(request, 'Esta seccion es solo para preceptores y directivos.')
            return redirect('staff:dashboard')
        return view_func(request, *args, **kwargs)

    return _wrapped


def es_directivo_o_superuser(user):
    """True para superuser, directivo o preceptor con rol asignado."""
    if not user.is_authenticated or not user.is_staff:
        return False
    if user.is_superuser:
        return True
    return es_directivo_o_preceptor(user)


def directivo_o_superuser_required(view_func):
    """Solo directivos, preceptores y superusers."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_staff:
            return redirect('staff:login')
        if not es_directivo_o_superuser(request.user):
            messages.error(request, 'Solo directivos pueden acceder a esta sección.')
            return redirect('staff:dashboard')
        return view_func(request, *args, **kwargs)

    return _wrapped


# ================================================================
# Helpers de jerarquía de roles
# ================================================================

def es_dueno(user):
    """True si el usuario es el dueño del sistema (superuser)."""
    return user.is_authenticated and user.is_superuser


def es_directivo(user):
    """True si tiene rol 'directivo' (independiente del preceptor)."""
    perfil = get_perfil_docente(user)
    return perfil is not None and perfil.rol == 'directivo'


def es_preceptor(user):
    """True si tiene rol 'preceptor'."""
    perfil = get_perfil_docente(user)
    return perfil is not None and perfil.rol == 'preceptor'


def es_docente(user):
    """True si tiene rol 'docente'."""
    perfil = get_perfil_docente(user)
    return perfil is not None and perfil.rol == 'docente'


# ================================================================
# Permisos sobre gestión de personal
# ================================================================

def puede_gestionar_personal(user):
    """
    True si el usuario puede entrar a la sección de gestión de personal.
    Solo dueños y directivos.
    """
    if not user.is_authenticated or not user.is_staff:
        return False
    return es_dueno(user) or es_directivo(user)


def puede_crear_rol(user, rol_objetivo):
    """
    True si 'user' puede crear un personal con el rol 'rol_objetivo'.
    rol_objetivo: 'docente', 'preceptor', 'directivo', 'dueno'
    """
    if not puede_gestionar_personal(user):
        return False
    if rol_objetivo == 'dueno':
        return es_dueno(user)
    # Todos los demás roles los puede crear tanto dueño como directivo
    return rol_objetivo in ('docente', 'preceptor', 'directivo')


def puede_ver_perfil(user, perfil):
    """
    True si 'user' puede ver al 'perfil' en los listados de personal.
    Regla principal: los directivos NO ven a los dueños.
    """
    if not user.is_authenticated or not user.is_staff:
        return False
    if es_dueno(user):
        return True
    # Directivo no ve al dueño
    if perfil.user.is_superuser:
        return False
    return puede_gestionar_personal(user)


def puede_editar_perfil(user, perfil):
    """
    True si 'user' puede editar al 'perfil' dado.
    - Dueño edita a cualquiera.
    - Directivo edita a directivos, preceptores y docentes (no a dueños).
    - Cualquiera puede editar su propio perfil vía 'mi perfil' (esto NO es ahí).
    """
    if not puede_gestionar_personal(user):
        return False
    if es_dueno(user):
        return True
    # Directivo: no puede editar a un dueño
    if perfil.user.is_superuser:
        return False
    return True


def puede_eliminar_perfil(user, perfil):
    """
    True si 'user' puede eliminar al 'perfil' dado.
    - Dueño elimina a cualquiera (con confirmación reforzada si es a sí mismo o a otro dueño).
    - Directivo elimina a directivos, preceptores, docentes — NUNCA a dueños.
    - Nadie puede eliminarse a sí mismo si es directivo (regla de seguridad: solo el dueño puede).
    """
    if not puede_gestionar_personal(user):
        return False
    # Nadie puede eliminar a un dueño excepto otro dueño
    if perfil.user.is_superuser:
        return es_dueno(user) and perfil.user_id != user.id
    if es_dueno(user):
        return True
    # Directivo no puede eliminarse a sí mismo (debe pedírselo al dueño)
    if perfil.user_id == user.id:
        return False
    return True


def filtrar_personal_visible(queryset, user):
    """
    Filtra un queryset de PerfilDocente para que el usuario solo vea lo que
    le corresponde según las reglas.
    Para directivos: excluye a los usuarios superuser.
    Para dueños: muestra todo.
    """
    if es_dueno(user):
        return queryset
    # Directivos: ocultar dueños
    return queryset.exclude(user__is_superuser=True)


# ================================================================
# Permisos extra opcionales
# ================================================================

# Defaults por rol — qué permisos vienen tildados al crear o al cambiar de rol.
DEFAULTS_PERMISOS_POR_ROL = {
    'directivo': {
        'puede_publicar_institucional': True,
        'puede_administrar_galerias_globales': True,
        'puede_ver_auditoria': True,
        'puede_editar_configuracion_portal': True,
        'puede_administrar_materias_grados': True,
    },
    'preceptor': {
        'puede_publicar_institucional': False,
        'puede_administrar_galerias_globales': True,
        'puede_ver_auditoria': False,
        'puede_editar_configuracion_portal': False,
        'puede_administrar_materias_grados': False,
    },
    'docente': {
        'puede_publicar_institucional': False,
        'puede_administrar_galerias_globales': False,
        'puede_ver_auditoria': False,
        'puede_editar_configuracion_portal': False,
        'puede_administrar_materias_grados': False,
    },
}


def aplicar_defaults_permisos_por_rol(perfil):
    """
    Aplica los defaults de permisos extra según el rol del perfil.
    Sobrescribe los valores actuales. Útil al crear o al cambiar de rol.
    NO guarda el perfil — el caller debe hacer perfil.save().
    """
    defaults = DEFAULTS_PERMISOS_POR_ROL.get(perfil.rol, {})
    for campo, valor in defaults.items():
        setattr(perfil, campo, valor)


def _chequear_flag_o_dueno(user, nombre_flag):
    """
    Helper interno: True si user es dueño, o si su PerfilDocente tiene el flag
    indicado en True.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    perfil = get_perfil_docente(user)
    if perfil is None:
        return False
    return getattr(perfil, nombre_flag, False)


def puede_publicar_institucional(user):
    """True si el usuario puede publicar avisos institucionales."""
    return _chequear_flag_o_dueno(user, 'puede_publicar_institucional')


def puede_administrar_galerias_globales(user):
    """True si el usuario puede administrar galerías no atadas a un aula."""
    return _chequear_flag_o_dueno(user, 'puede_administrar_galerias_globales')


def puede_ver_auditoria(user):
    """True si el usuario puede acceder al log de auditoría."""
    return _chequear_flag_o_dueno(user, 'puede_ver_auditoria')


def puede_editar_configuracion_portal(user):
    """True si el usuario puede editar la configuración del portal."""
    return _chequear_flag_o_dueno(user, 'puede_editar_configuracion_portal')


def puede_administrar_materias_grados(user):
    """True si el usuario puede crear/editar materias y grados."""
    return _chequear_flag_o_dueno(user, 'puede_administrar_materias_grados')


# ================================================================
# Decoradores basados en permisos extra
# ================================================================

def _decorador_permiso(funcion_chequeo, mensaje_error):
    """
    Fabrica un decorador que solo deja pasar si funcion_chequeo(user) es True.
    Si no, redirige al dashboard con un mensaje.
    """
    def decorador(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('staff:login')
            if not request.user.is_staff:
                messages.error(request, 'Esta sección es solo para personal de la escuela.')
                return redirect('comunicacion:landing')
            if not funcion_chequeo(request.user):
                messages.error(request, mensaje_error)
                return redirect('staff:dashboard')
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorador


def permiso_institucional_required(view_func):
    """Requiere permiso para publicar avisos institucionales."""
    return _decorador_permiso(
        puede_publicar_institucional,
        'No tenés permiso para publicar avisos institucionales.'
    )(view_func)


def permiso_galerias_globales_required(view_func):
    """Requiere permiso para administrar galerías globales."""
    return _decorador_permiso(
        puede_administrar_galerias_globales,
        'No tenés permiso para administrar galerías globales.'
    )(view_func)


def permiso_auditoria_required(view_func):
    """Requiere permiso para ver la auditoría."""
    return _decorador_permiso(
        puede_ver_auditoria,
        'No tenés permiso para ver el registro de auditoría.'
    )(view_func)


def permiso_configuracion_required(view_func):
    """Requiere permiso para editar la configuración del portal."""
    return _decorador_permiso(
        puede_editar_configuracion_portal,
        'No tenés permiso para editar la configuración del portal.'
    )(view_func)


def permiso_materias_grados_required(view_func):
    """Requiere permiso para administrar materias y grados."""
    return _decorador_permiso(
        puede_administrar_materias_grados,
        'No tenés permiso para administrar materias y grados.'
    )(view_func)


# ================================================================
# Mensajería interna: con quién puede hablar cada rol
# ================================================================
def roles_contactables(user):
    """
    Devuelve la lista de roles con los que 'user' puede iniciar conversaciones.
    - Dueño y directivos: todos.
    - Preceptores: preceptores y docentes.
    - Docentes: solo docentes.
    """
    if es_dueno(user) or es_directivo(user):
        return ['directivo', 'preceptor', 'docente']
    if es_preceptor(user):
        return ['preceptor', 'docente']
    if es_docente(user):
        return ['docente']
    return []


def staff_contactable_qs(user):
    """
    Queryset de Users del staff con los que 'user' puede iniciar conversaciones.
    Excluye al propio usuario. Aplica las reglas de roles_contactables.
    El dueño puede contactar a cualquier staff (incluido otros superusers).
    """
    from django.contrib.auth.models import User
    from comunicacion.models import PerfilDocente

    roles = roles_contactables(user)
    qs = User.objects.filter(is_staff=True, is_active=True).exclude(pk=user.pk)

    if es_dueno(user):
        # El dueño contacta a cualquiera
        return qs.order_by('first_name', 'last_name')

    # Resto: filtrar por roles permitidos vía PerfilDocente
    ids_permitidos = PerfilDocente.objects.filter(
        rol__in=roles
    ).values_list('user_id', flat=True)
    return qs.filter(pk__in=ids_permitidos).order_by('first_name', 'last_name')
