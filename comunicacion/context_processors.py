from .models import ConfiguracionPortal


def configuracion_portal(request):
    """Expose ConfiguracionPortal singleton as `config` for all templates."""
    config = None

    try:
        config = ConfiguracionPortal.objects.first()
    except Exception:
        config = None

    return {
        "config": config
    }
