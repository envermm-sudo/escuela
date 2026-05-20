from .permissions import es_directivo_o_preceptor, get_perfil_docente


def staff_context(request):
    """Contexto global del panel staff: rol del usuario y contadores."""
    if not request.user.is_authenticated:
        return {}

    consultas_pendientes_count = 0
    mensajes_no_leidos_count = 0

    if request.user.is_staff and request.path.startswith('/staff/'):
        try:
            from comunicacion.models import ConsultaComunicado
            qs = ConsultaComunicado.objects.filter(estado='pendiente')
            if not request.user.is_superuser:
                qs = qs.filter(comunicado__autor=request.user)
            consultas_pendientes_count = qs.count()
        except Exception:
            consultas_pendientes_count = 0

        try:
            from comunicacion.models import MiembroConversacion
            total = 0
            membresias = (
                MiembroConversacion.objects
                .filter(usuario=request.user, activo=True)
                .select_related('conversacion')
            )
            for m in membresias:
                nuevos = m.conversacion.mensajes.exclude(autor=request.user)
                if m.ultima_lectura:
                    nuevos = nuevos.filter(creado__gt=m.ultima_lectura)
                total += nuevos.count()
            mensajes_no_leidos_count = total
        except Exception:
            mensajes_no_leidos_count = 0

    return {
        'es_directivo': es_directivo_o_preceptor(request.user),
        'perfil_actual': get_perfil_docente(request.user),
        'consultas_pendientes_count': consultas_pendientes_count,
        'mensajes_no_leidos_count': mensajes_no_leidos_count,
    }
