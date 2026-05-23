from .permissions import es_directivo_o_preceptor, get_perfil_docente


def staff_context(request):
    """Contexto global del panel staff: rol del usuario y contadores."""
    if not request.user.is_authenticated:
        return {}

    consultas_pendientes_count = 0
    mensajes_no_leidos_count = 0

    if request.user.is_staff and request.path.startswith('/staff/'):
        try:
            from django.db.models import OuterRef, Subquery
            from comunicacion.models import ConsultaComunicado, MensajeConsulta

            qs = ConsultaComunicado.objects.all()
            if not request.user.is_superuser:
                qs = qs.filter(comunicado__autor=request.user)

            ultimo_padre = (
                MensajeConsulta.objects
                .filter(consulta=OuterRef('pk'), es_del_docente=False)
                .order_by('-creado')
            )
            qs = qs.annotate(
                ultimo_padre_creado=Subquery(ultimo_padre.values('creado')[:1])
            )
            total_consultas = 0
            for fecha_ultimo, docente_leyo in qs.values_list('ultimo_padre_creado', 'docente_leyo'):
                if fecha_ultimo is None:
                    continue
                if docente_leyo is not None and fecha_ultimo <= docente_leyo:
                    continue
                total_consultas += 1
            consultas_pendientes_count = total_consultas
        except Exception:
            consultas_pendientes_count = 0

        try:
            from django.db.models import Count, Q, F
            from comunicacion.models import MiembroConversacion

            membresias = (
                MiembroConversacion.objects
                .filter(usuario=request.user, activo=True)
                .annotate(
                    nuevos=Count(
                        'conversacion__mensajes',
                        filter=(
                            ~Q(conversacion__mensajes__autor=request.user)
                            & (
                                Q(ultima_lectura__isnull=True)
                                | Q(conversacion__mensajes__creado__gt=F('ultima_lectura'))
                            )
                        ),
                    )
                )
            )
            mensajes_no_leidos_count = sum(m.nuevos for m in membresias)
        except Exception:
            mensajes_no_leidos_count = 0

    from .permissions import es_directivo_o_preceptor, get_perfil_docente
    return {
        'es_directivo': es_directivo_o_preceptor(request.user),
        'perfil_actual': get_perfil_docente(request.user),
        'consultas_pendientes_count': consultas_pendientes_count,
        'mensajes_no_leidos_count': mensajes_no_leidos_count,
    }
