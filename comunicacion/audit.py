"""
Helpers para registrar acciones en AuditLog y setear creado_por/modificado_por.
"""

from .models import AuditLog


def registrar_audit(usuario, accion, instancia, cambios=None):
    """
    Crea una entrada en AuditLog para instancia.
    accion debe ser uno de: 'crear', 'editar', 'eliminar', 'publicar'.
    """
    if usuario is None or not usuario.is_authenticated:
        return None

    try:
        repr_str = str(instancia)[:200]
    except Exception:
        repr_str = f'{instancia.__class__.__name__} #{getattr(instancia, "pk", "?")}'

    return AuditLog.objects.create(
        usuario=usuario,
        accion=accion,
        modelo=instancia.__class__.__name__,
        objeto_id=getattr(instancia, 'pk', None),
        objeto_repr=repr_str,
        cambios=cambios or None,
    )
