"""
Plantillas rápidas para crear comunicados.
Cada plantilla pre-llena tipo + título + contenido base.
"""

PLANTILLAS_COMUNICADO = [
    {
        'codigo': 'tarea',
        'etiqueta': '📚 Tarea',
        'color': 'bg-blue-50 border-blue-200 hover:bg-blue-100 text-blue-900',
        'tipo': 'tarea',
        'titulo': 'Tarea para [día]',
        'contenido': 'Resolver:\n- Página XX\n- Ejercicios 1 al X\n\nFecha de entrega: ...',
    },
    {
        'codigo': 'aviso',
        'etiqueta': '📢 Aviso',
        'color': 'bg-gray-50 border-gray-200 hover:bg-gray-100 text-gray-900',
        'tipo': 'aviso',
        'titulo': 'Aviso importante',
        'contenido': 'Estimadas familias,\n\n...\n\nMuchas gracias.',
    },
    {
        'codigo': 'material',
        'etiqueta': '📎 Recordatorio material',
        'color': 'bg-emerald-50 border-emerald-200 hover:bg-emerald-100 text-emerald-900',
        'tipo': 'material',
        'titulo': 'Materiales para [día]',
        'contenido': 'Recordamos traer para la clase:\n- ...\n- ...\n- ...',
    },
    {
        'codigo': 'suspension',
        'etiqueta': '🚨 Suspensión',
        'color': 'bg-red-50 border-red-200 hover:bg-red-100 text-red-900',
        'tipo': 'urgente',
        'titulo': 'Suspensión de clases [día]',
        'contenido': 'Comunicamos que el día ... no habrá clases debido a ...\n\nLas clases se retomarán el día ...',
    },
]


def get_plantilla(codigo):
    for p in PLANTILLAS_COMUNICADO:
        if p['codigo'] == codigo:
            return p
    return None
