from django.db import models
from django.utils.timezone import now
from django.core.exceptions import ValidationError


class Pagina(models.Model):
    url = models.URLField(
        unique=True,
        verbose_name="URL",
        help_text="La URL única de la página.",
    )
    ultima_consulta = models.DateTimeField(
        null=True, blank=True, verbose_name="Última Consulta", help_text="Fecha de la última consulta realizada a la página."
    )
    codigo_estado = models.IntegerField(
        null=True, blank=True, verbose_name="Código de Estado", help_text="Código HTTP devuelto en la última consulta."
    )
    es_huerfana = models.BooleanField(
        default=False, verbose_name="¿Es Huérfana?", help_text="Indica si la página es huérfana (sin enlaces entrantes)."
    )
    activa = models.BooleanField(
        default=True, verbose_name="¿Está activa?", help_text="Indica si la página está activa y debe mostrarse en la interfaz."
    )
    created_at = models.DateTimeField(
        default=now, verbose_name="Fecha de Creación", help_text="Fecha en la que se creó el registro de la página."
    )

    class Meta:
        verbose_name = "Página"
        verbose_name_plural = "Páginas"
        ordering = ['-ultima_consulta']
        indexes = [
            models.Index(fields=['url']),
        ]

    def __str__(self):
        return self.url

    def actualizar_ultima_consulta(self, codigo_estado):
        """
        Actualiza la última consulta y el código de estado HTTP asociado.
        """
        self.ultima_consulta = now()
        self.codigo_estado = codigo_estado
        self.save(update_fields=["ultima_consulta", "codigo_estado"])

    def marcar_huerfana(self):
        """
        Marca la página como huérfana.
        """
        if not self.es_huerfana:  # Evita actualizaciones innecesarias
            self.es_huerfana = True
            self.save(update_fields=["es_huerfana"])

    def marcar_no_huerfana(self):
        """
        Marca la página como no huérfana.
        """
        if self.es_huerfana:  # Evita actualizaciones innecesarias
            self.es_huerfana = False
            self.save(update_fields=["es_huerfana"])

    def marcar_inactiva(self):
        """
        Marca la página como inactiva.
        """
        if self.activa:  # Evita actualizaciones innecesarias
            self.activa = False
            self.save(update_fields=["activa"])

    def marcar_activa(self):
        """
        Marca la página como activa.
        """
        if not self.activa:  # Evita actualizaciones innecesarias
            self.activa = True
            self.save(update_fields=["activa"])

class Enlace(models.Model):
    pagina_origen = models.ForeignKey(
        Pagina,
        related_name='enlaces_salientes',
        on_delete=models.CASCADE,
        verbose_name="Página de Origen",
        help_text="La página desde la que se origina el enlace.",
    )
    pagina_destino = models.ForeignKey(
        Pagina,
        related_name='enlaces_entrantes',
        on_delete=models.CASCADE,
        verbose_name="Página de Destino",
        help_text="La página a la que apunta el enlace.",
    )

    class Meta:
        verbose_name = "Enlace"
        verbose_name_plural = "Enlaces"
        constraints = [
            models.UniqueConstraint(
                fields=['pagina_origen', 'pagina_destino'], name='unique_enlace'
            )
        ]
        indexes = [
            models.Index(fields=['pagina_origen', 'pagina_destino']),
        ]

    def clean(self):
        """
        Valida que una página no pueda enlazarse a sí misma.
        """
        if self.pagina_origen == self.pagina_destino:
            raise ValidationError("Una página no puede enlazarse a sí misma.")

    def save(self, *args, **kwargs):
        """
        Limpia y guarda el modelo, actualizando el estado de huérfana de la página destino si es necesario.
        """
        self.clean()
        super().save(*args, **kwargs)

        # Actualizar el estado de huérfana para la página destino
        if self.pagina_destino.es_huerfana:
            self.pagina_destino.marcar_no_huerfana()

    def __str__(self):
        return f"{self.pagina_origen} -> {self.pagina_destino}"


class EnlaceRoto(models.Model):
    pagina = models.ForeignKey(
        Pagina,
        related_name='enlaces_rotos',
        on_delete=models.CASCADE,
        verbose_name="Página",
        help_text="La página que contiene el enlace roto.",
    )
    url_enlace_roto = models.URLField(
        verbose_name="URL del Enlace Roto",
        help_text="La URL del enlace roto encontrado en la página.",
    )
    codigo_estado = models.IntegerField(
        verbose_name="Código de Estado",
        help_text="Código HTTP devuelto por el enlace roto.",
    )
    tipo_contenido = models.CharField(
        max_length=255,
        verbose_name="Tipo de Contenido",
        help_text="Tipo de contenido del enlace roto (si está disponible).",
        blank=True,
        null=True,
    )
    detectado_en = models.DateTimeField(
        default=now,
        verbose_name="Detectado en",
        help_text="Fecha en la que se detectó el enlace roto.",
    )

    class Meta:
        verbose_name = "Enlace Roto"
        verbose_name_plural = "Enlaces Rotos"
        ordering = ['-detectado_en']
        indexes = [
            models.Index(fields=['pagina', 'url_enlace_roto']),
        ]

    def __str__(self):
        return f"Enlace roto en {self.pagina.url} -> {self.url_enlace_roto} (Código: {self.codigo_estado})"