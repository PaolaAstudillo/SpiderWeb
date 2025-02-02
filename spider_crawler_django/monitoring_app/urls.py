from django.urls import path
from . import views


urlpatterns = [
    path('', views.tablero, name='tablero'),  # Define la raíz como la vista tablero
    path('obtener_progreso/', views.obtener_progreso, name='obtener_progreso'),
    path('stream-progreso/', views.stream_progreso, name='stream_progreso'),  # Ruta para SSE
    path('detener_scrapy/', views.detener_scrapy_view, name='detener_scrapy'),

]