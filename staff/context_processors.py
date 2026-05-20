from .permissions import es_directivo_o_preceptor, get_perfil_docente


def staff_context(request):
    """Contexto global del panel staff: rol del usuario."""
    if not request.user.is_authenticated:
        return {}
    return {
        'es_directivo': es_directivo_o_preceptor(request.user),
        'perfil_actual': get_perfil_docente(request.user),
    }
