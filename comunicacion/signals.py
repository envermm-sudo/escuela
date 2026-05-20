"""Señales de la app comunicacion."""

from django.contrib.auth.models import Group
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import ConfiguracionPortal, PerfilDocente, PerfilPadre

# ====================================================================
# Auto-staff: cuando se crea un PerfilDocente, su User queda como staff
# ====================================================================
@receiver(post_save, sender=PerfilDocente)
def docente_es_staff(sender, instance, created, **kwargs):
    user = instance.user
    cambios = False
    if not user.is_staff:
        user.is_staff = True
        cambios = True
    if not user.is_active:
        user.is_active = True
        cambios = True
    if cambios:
        user.save(update_fields=['is_staff', 'is_active'])
    try:
        grupo_docentes = Group.objects.get(name='Docentes')
        if not user.groups.filter(pk=grupo_docentes.pk).exists():
            user.groups.add(grupo_docentes)
    except Group.DoesNotExist:
        pass


# ====================================================================
# Compresión automática de foto del docente
# ====================================================================
@receiver(pre_save, sender=PerfilDocente)
def comprimir_foto_docente(sender, instance, **kwargs):
    """
    Antes de guardar:
    - Si hay una foto NUEVA (distinta a la de la DB), convertirla a webp 600x600.
    - Renombrarla a 'docente_<username_o_pk>.webp'.
    """
    if not instance.foto:
        return

    nombre_actual = instance.foto.name or ''

    # Si ya es webp Y tiene nombre tipo "docente_*.webp", no reprocesar
    if nombre_actual.lower().endswith('.webp') and 'docente_' in nombre_actual.lower():
        return

    # Si la instancia ya existe y la foto NO cambió, no reprocesar
    if instance.pk:
        try:
            anterior = PerfilDocente.objects.get(pk=instance.pk)
            if anterior.foto and anterior.foto.name == instance.foto.name:
                return
        except PerfilDocente.DoesNotExist:
            pass

    from .utils import convertir_a_webp
    webp_file = convertir_a_webp(instance.foto, max_size=(600, 600), calidad=85)
    if webp_file:
        # Renombrar a algo simple basado en el username (sin caracteres raros)
        import re
        username_limpio = re.sub(r'[^a-zA-Z0-9]', '_', instance.user.username)[:40]
        webp_file.name = f'docente_{username_limpio}.webp'
        instance.foto = webp_file


# ====================================================================
# Compresión automática del logo y portada de la escuela
# ====================================================================
@receiver(pre_save, sender=ConfiguracionPortal)
def comprimir_logo_portada(sender, instance, **kwargs):
    """
    Convierte logo y portada a webp con tamaños razonables al guardar.
    """
    from .utils import convertir_a_webp

    # Logo: máximo 400x400, calidad 90 (es chico, importa la nitidez)
    if instance.logo:
        nombre = instance.logo.name or ''
        if not (nombre.lower().endswith('.webp') and 'logo_escuela' in nombre.lower()):
            necesita_convertir = True
            if instance.pk:
                try:
                    anterior = ConfiguracionPortal.objects.get(pk=instance.pk)
                    if anterior.logo and anterior.logo.name == instance.logo.name:
                        necesita_convertir = False
                except ConfiguracionPortal.DoesNotExist:
                    pass
            if necesita_convertir:
                webp = convertir_a_webp(instance.logo, max_size=(400, 400), calidad=90)
                if webp:
                    webp.name = 'logo_escuela.webp'
                    instance.logo = webp

    # Portada: máximo 1920x800, calidad 78 (puede ser grande, prioridad peso)
    if instance.portada:
        nombre = instance.portada.name or ''
        if not (nombre.lower().endswith('.webp') and 'portada_escuela' in nombre.lower()):
            necesita_convertir = True
            if instance.pk:
                try:
                    anterior = ConfiguracionPortal.objects.get(pk=instance.pk)
                    if anterior.portada and anterior.portada.name == instance.portada.name:
                        necesita_convertir = False
                except ConfiguracionPortal.DoesNotExist:
                    pass
            if necesita_convertir:
                webp = convertir_a_webp(instance.portada, max_size=(1920, 800), calidad=78)
                if webp:
                    webp.name = 'portada_escuela.webp'
                    instance.portada = webp


# ====================================================================
# Compresión automática de foto del padre
# ====================================================================
@receiver(pre_save, sender=PerfilPadre)
def comprimir_foto_padre(sender, instance, **kwargs):
    """Convierte la foto del padre a webp 600x600 cuando hay foto nueva."""
    if not instance.foto:
        return

    nombre_actual = instance.foto.name or ''
    if nombre_actual.lower().endswith('.webp') and 'padre_' in nombre_actual.lower():
        return

    if instance.pk:
        try:
            anterior = PerfilPadre.objects.get(pk=instance.pk)
            if anterior.foto and anterior.foto.name == instance.foto.name:
                return
        except PerfilPadre.DoesNotExist:
            pass

    from .utils import convertir_a_webp
    import re
    webp_file = convertir_a_webp(instance.foto, max_size=(600, 600), calidad=85)
    if webp_file:
        username_limpio = re.sub(r'[^a-zA-Z0-9]', '_', instance.user.username)[:40]
        webp_file.name = f'padre_{username_limpio}.webp'
        instance.foto = webp_file
