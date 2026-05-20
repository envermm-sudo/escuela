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
