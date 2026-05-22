from django.urls import path
from . import views

app_name = 'comunicacion'

urlpatterns = [
    path('', views.landing_view, name='landing'),
    path('muro/<slug:grado_slug>/', views.muro_grado_view, name='muro_grado'),
    path('grado/<slug:grado_slug>/galerias/', views.galerias_grado_view, name='galerias_grado'),
    path('galeria/<int:pk>/', views.galeria_detalle_publica_view, name='galeria_detalle_publica'),
    path('comunicado/<int:pk>/', views.comunicado_detalle_view, name='comunicado_detalle'),
    path('comunicado/<int:pk>/consulta/', views.consulta_hilo_view, name='consulta_hilo'),
    path('registro/', views.registro_padre_view, name='registro_padre'),
    path('login/', views.login_padre_view, name='login_padre'),
    path('logout/', views.logout_view, name='logout'),
    path('mis-grados/', views.mis_grados_view, name='mis_grados'),
    path('recuperar-clave/', views.recuperar_clave_solicitar_view, name='recuperar_clave_solicitar'),
    path('recuperar-clave/<str:token>/', views.recuperar_clave_confirmar_view, name='recuperar_clave_confirmar'),
    # Mi cuenta del padre
    path('mi-cuenta/', views.mi_cuenta_padre_view, name='mi_cuenta'),
    path('notificaciones/json/', views.notificaciones_padre_json, name='notificaciones_padre_json'),
    path('mi-cuenta/hijos/nuevo/', views.hijo_crear_view, name='hijo_crear'),
    path('mi-cuenta/hijos/<int:pk>/editar/', views.hijo_editar_view, name='hijo_editar'),
    path('mi-cuenta/hijos/<int:pk>/eliminar/', views.hijo_eliminar_view, name='hijo_eliminar'),
    # Desuscripción pública (desde link de email)
    path('desuscribirme/<str:token>/', views.desuscribirme_view, name='desuscribirme'),
]
