"""
Middleware que restringe acceso al admin de Jazzmin solo a superusers.
Cualquier otro usuario autenticado es redirigido al panel /staff/ con un mensaje.
"""

from django.contrib import messages
from django.shortcuts import redirect


class AdminSoloSuperuserMiddleware:
    """
    Bloquea acceso a /admin/ para usuarios que NO son superuser.
    Excepciones:
    - /admin/login/ (para que puedan loguearse)
    - /admin/logout/
    - Si la URL no empieza con /admin/, no toca nada.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        # Solo nos importan rutas que empiezan con /admin/
        if not path.startswith('/admin/'):
            return self.get_response(request)

        # Permitir el login y logout del admin (no podemos bloquearlos sin loop)
        if path.startswith('/admin/login') or path.startswith('/admin/logout') or path.startswith('/admin/jsi18n'):
            return self.get_response(request)

        # Si no está autenticado, dejamos que el admin maneje el redirect a login
        if not request.user.is_authenticated:
            return self.get_response(request)

        # Solo superusers pueden seguir
        if request.user.is_superuser:
            return self.get_response(request)

        # Cualquier otro: bloquear con mensaje y redirigir al panel staff
        messages.warning(
            request,
            'El panel de administración avanzado es solo para el administrador del sistema. '
            'Usá el panel del staff para gestionar comunicados, galerías y tu perfil.'
        )
        return redirect('staff:dashboard')
