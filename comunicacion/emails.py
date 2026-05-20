"""
Helpers de email del Portal de Comunicación Escolar.

- enviar_email_async: dispara el envío en un thread separado para no bloquear la request.
- generar_token_padre / verificar_token_padre: tokens firmados para desuscripción y recuperación.
- contexto_email_base: variables comunes para todas las plantillas de email.
"""

import logging
import threading

from django.conf import settings
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


# ====================================================================
# Envío asíncrono
# ====================================================================
def _enviar_sync(subject, html_body, to_emails, text_body=None, from_email=None):
    """Envío real en background. NO llamar directo, usar enviar_email_async."""
    if not to_emails:
        return
    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body or strip_tags(html_body),
            from_email=from_email or settings.DEFAULT_FROM_EMAIL,
            to=[to_emails] if isinstance(to_emails, str) else list(to_emails),
        )
        msg.attach_alternative(html_body, 'text/html')
        msg.send(fail_silently=False)
        logger.info('Email enviado a %s — asunto: %s', to_emails, subject)
    except Exception as exc:
        logger.error('Fallo enviando email a %s: %s', to_emails, exc)


def enviar_email_async(subject, html_body, to_emails, text_body=None, from_email=None):
    """
    Encola el envío en un thread daemon. La request no espera el envío.
    to_emails: string o lista de strings.
    """
    thread = threading.Thread(
        target=_enviar_sync,
        args=(subject, html_body, to_emails, text_body, from_email),
        daemon=True,
    )
    thread.start()


def enviar_email_template(subject, template_name, contexto, to_emails, from_email=None):
    """
    Atajo: renderiza un template HTML con el contexto + variables comunes
    y lo dispara async.
    """
    ctx = dict(contexto_email_base())
    ctx.update(contexto or {})
    html_body = render_to_string(template_name, ctx)
    enviar_email_async(subject, html_body, to_emails, from_email=from_email)


# ====================================================================
# Contexto común
# ====================================================================
def contexto_email_base():
    """Variables que cualquier plantilla de email puede usar."""
    from .models import ConfiguracionPortal
    config = ConfiguracionPortal.objects.first()
    return {
        'site_url': settings.SITE_URL,
        'config': config,
        'nombre_institucion': config.nombre_institucion if config else 'Portal Escolar',
    }


# ====================================================================
# Tokens firmados (para recuperación de clave y desuscripción)
# ====================================================================
def generar_token_padre(user_id, accion='reset'):
    """
    Genera un token firmado y limitado en el tiempo.
    accion: 'reset' (recuperación de clave) o 'unsub' (desuscripción).
    """
    return signing.dumps({'uid': user_id, 'accion': accion}, salt=f'pce-{accion}')


def verificar_token_padre(token, accion='reset', max_age_seconds=86400):
    """
    Devuelve user_id si el token es válido para esa acción y no expiró.
    Devuelve None si es inválido o expiró.
    Default 24h para reset, llamar con max_age_seconds=None (sin expiración) para unsub.
    """
    try:
        if max_age_seconds is None:
            datos = signing.loads(token, salt=f'pce-{accion}')
        else:
            datos = signing.loads(token, salt=f'pce-{accion}', max_age=max_age_seconds)
        if datos.get('accion') != accion:
            return None
        return datos.get('uid')
    except signing.BadSignature:
        return None
    except signing.SignatureExpired:
        return None


# ====================================================================
# Notificación masiva: comunicado nuevo
# ====================================================================
def notificar_comunicado_a_padres(comunicado):
    """
    Dispara emails a los padres de los grados destinatarios del comunicado.
    Cubre AMBAS fuentes de hijos:
      - HijoPadre (modelo nuevo, fuente de verdad)
      - PerfilPadre.hijos_grados (M2M legacy, padres registrados antes)
    Respeta tipo_notificacion ('todos'|'urgentes'|'ninguno') y notif_email.
    """
    from django.db.models import Q
    from django.urls import reverse

    from .models import PerfilPadre

    grados_ids = list(comunicado.grados.values_list('pk', flat=True))
    if not grados_ids:
        logger.info('Comunicado %s sin grados destinatarios — no se notifica', comunicado.pk)
        return 0

    # Padres con hijos en alguno de los grados (modelo nuevo O legacy)
    padres_qs = (
        PerfilPadre.objects
        .filter(
            Q(hijos__grado_id__in=grados_ids) |
            Q(hijos_grados__id__in=grados_ids)
        )
        .exclude(tipo_notificacion='ninguno')
        .exclude(notif_email=False)
        .exclude(user__email='')
        .exclude(user__is_active=False)
        .select_related('user')
        .distinct()
    )

    # Si NO es urgente, excluir a los que solo quieren urgentes
    if not comunicado.urgente:
        padres_qs = padres_qs.exclude(tipo_notificacion='urgentes')

    total_padres = padres_qs.count()
    logger.info(
        'Comunicado %s (urgente=%s) — grados=%s — padres candidatos=%s',
        comunicado.pk, comunicado.urgente, grados_ids, total_padres,
    )

    if total_padres == 0:
        return 0

    # Snippet (primeros 200 caracteres)
    contenido = comunicado.contenido or ''
    snippet = contenido[:200]
    truncado = len(contenido) > 200

    # Link al detalle público
    link_comunicado = (
        settings.SITE_URL.rstrip('/')
        + reverse('comunicacion:comunicado_detalle', args=[comunicado.pk])
    )

    grado_principal = comunicado.grados.order_by('orden', 'nombre').first()
    asunto = f'{"🚨 URGENTE - " if comunicado.urgente else ""}{comunicado.titulo}'
    base_ctx = dict(contexto_email_base())

    enviados = 0
    for perfil in padres_qs:
        if not perfil.user.email:
            continue

        token_unsub = generar_token_padre(perfil.user_id, accion='unsub')
        link_unsub = (
            settings.SITE_URL.rstrip('/')
            + reverse('comunicacion:desuscribirme', args=[token_unsub])
        )

        ctx = dict(base_ctx)
        ctx.update({
            'comunicado': comunicado,
            'snippet': snippet,
            'truncado': truncado,
            'link_comunicado': link_comunicado,
            'link_desuscripcion': link_unsub,
            'grado_principal': str(grado_principal) if grado_principal else '',
            'perfil': perfil,
        })

        html_body = render_to_string('emails/notificacion_comunicado.html', ctx)
        enviar_email_async(
            subject=asunto,
            html_body=html_body,
            to_emails=perfil.user.email,
        )
        enviados += 1

    logger.info('Notificación de comunicado %s disparada a %s padres', comunicado.pk, enviados)
    return enviados


# ====================================================================
# Notificaciones de consultas de padres
# ====================================================================
def notificar_consulta_al_docente(consulta):
    """Avisa al docente autor del comunicado que un padre escribió una consulta."""
    from django.urls import reverse

    docente = consulta.comunicado.autor
    if not docente or not docente.email:
        return
    if not docente.is_active:
        return

    link = (
        settings.SITE_URL.rstrip('/')
        + reverse('staff:consulta_detalle', args=[consulta.pk])
    )
    ctx = dict(contexto_email_base())
    ctx.update({
        'consulta': consulta,
        'comunicado': consulta.comunicado,
        'padre': consulta.padre,
        'link': link,
    })
    html_body = render_to_string('emails/consulta_nueva_docente.html', ctx)
    enviar_email_async(
        subject=f'Nueva consulta sobre "{consulta.comunicado.titulo}"',
        html_body=html_body,
        to_emails=docente.email,
    )


def notificar_respuesta_al_padre(consulta):
    """Avisa al padre que el docente respondió su consulta. Respeta sus preferencias."""
    from django.urls import reverse

    padre = consulta.padre
    if not padre or not padre.email or not padre.is_active:
        return

    perfil_padre = getattr(padre, 'perfil_padre', None)
    if perfil_padre is not None:
        if not perfil_padre.notif_email:
            return
        if perfil_padre.tipo_notificacion == 'ninguno':
            return

    link = (
        settings.SITE_URL.rstrip('/')
        + reverse('comunicacion:consulta_hilo', args=[consulta.comunicado.pk])
    )
    ctx = dict(contexto_email_base())
    ctx.update({
        'consulta': consulta,
        'comunicado': consulta.comunicado,
        'link': link,
    })
    html_body = render_to_string('emails/consulta_respuesta_padre.html', ctx)
    enviar_email_async(
        subject=f'El docente respondió tu consulta sobre "{consulta.comunicado.titulo}"',
        html_body=html_body,
        to_emails=padre.email,
    )
