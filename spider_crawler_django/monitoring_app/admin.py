from django.contrib import admin

from monitoring_app.models import Enlace, Pagina
# Register your models here.
admin.site.register(Pagina)
admin.site.register(Enlace)