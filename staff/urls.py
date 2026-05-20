from django.urls import path
from . import views

app_name = 'staff'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('', views.dashboard_view, name='dashboard'),

    # Comunicados
    path('comunicados/', views.comunicados_lista, name='comunicados_lista'),
    path('comunicados/nuevo/', views.comunicado_crear, name='comunicado_crear'),
    path('comunicados/<int:pk>/', views.comunicado_detalle, name='comunicado_detalle'),
    path('comunicados/<int:pk>/editar/', views.comunicado_editar, name='comunicado_editar'),
    path('comunicados/<int:pk>/eliminar/', views.comunicado_eliminar, name='comunicado_eliminar'),

    # Galerías
    path('galerias/', views.galerias_lista, name='galerias_lista'),
    path('galerias/nuevo/', views.galeria_crear, name='galeria_crear'),
    path('galerias/<int:pk>/', views.galeria_detalle, name='galeria_detalle'),
    path('galerias/<int:pk>/editar/', views.galeria_editar, name='galeria_editar'),
    path('galerias/<int:pk>/eliminar/', views.galeria_eliminar, name='galeria_eliminar'),

    # Otros
    path('asignaciones/', views.mis_asignaciones, name='mis_asignaciones'),
    path('estadisticas/', views.estadisticas, name='estadisticas'),

    path('personal/', views.gestion_personal_lista, name='personal_lista'),
    path('personal/<int:pk>/ficha/', views.docente_ficha, name='docente_ficha'),
    path('docentes/<int:pk>/', views.docente_ficha, name='docente_ficha_alias'),

    # NUEVO — Mi perfil
    path('mi-perfil/', views.mi_perfil_view, name='mi_perfil'),
    path('configuracion/', views.configuracion_portal_view, name='configuracion'),
    path('auditoria/', views.auditoria_view, name='auditoria'),

    # Consultas de padres
    path('consultas/', views.consultas_lista, name='consultas_lista'),
    path('consultas/<int:pk>/', views.consulta_detalle, name='consulta_detalle'),

    # Mensajería interna
    path('mensajes/', views.mensajes_lista, name='mensajes_lista'),
    path('mensajes/nuevo/', views.mensaje_nuevo, name='mensaje_nuevo'),
    path('mensajes/<int:pk>/', views.mensaje_conversacion, name='mensaje_conversacion'),
    path('mensajes/<int:pk>/miembros/', views.mensaje_gestionar_miembros, name='mensaje_gestionar_miembros'),
    path('mensajes/<int:pk>/json/', views.mensaje_conversacion_json, name='mensaje_conversacion_json'),

    # Gestión (director/superuser)
    path('gestion/', views.gestion_dashboard, name='gestion_dashboard'),

    # Alias para compatibilidad con links antiguos
    path('gestion/personal/', views.gestion_personal_lista, name='gestion_personal_lista'),
    path('gestion/personal/nuevo/', views.gestion_personal_form, name='gestion_personal_nuevo'),
    path('gestion/personal/<int:pk>/', views.gestion_personal_form, name='gestion_personal_editar'),
    path('gestion/personal/<int:pk>/eliminar/', views.gestion_personal_eliminar, name='gestion_personal_eliminar'),
    path('gestion/personal/<int:pk>/reset-password/', views.gestion_personal_reset_password, name='gestion_personal_reset_password'),
    path('gestion/personal/<int:pk>/matriz/', views.gestion_personal_matriz, name='gestion_personal_matriz'),

    path('gestion/materias/', views.gestion_materias_lista, name='gestion_materias'),
    path('gestion/materias/nueva/', views.gestion_materia_form, name='gestion_materia_nueva'),
    path('gestion/materias/<int:pk>/', views.gestion_materia_form, name='gestion_materia_editar'),
    path('gestion/materias/<int:pk>/eliminar/', views.gestion_materia_eliminar, name='gestion_materia_eliminar'),
    path('gestion/grados/', views.gestion_grados_lista, name='gestion_grados'),
    path('gestion/grados/nuevo/', views.gestion_grado_form, name='gestion_grado_nuevo'),
    path('gestion/grados/<int:pk>/', views.gestion_grado_form, name='gestion_grado_editar'),
    path('gestion/grados/<int:pk>/eliminar/', views.gestion_grado_eliminar, name='gestion_grado_eliminar'),
    path('gestion/docentes/', views.gestion_docentes_admin_link, name='gestion_docentes_link'),

    # Comunicado institucional
    path('comunicados/institucional/nuevo/', views.comunicado_institucional_crear, name='comunicado_institucional_nuevo'),
]
