# Generated by Django 5.1.5 on 2025-02-20 00:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('monitoring_app', '0002_enlaceroto'),
    ]

    operations = [
        migrations.AddField(
            model_name='enlaceroto',
            name='tipo_contenido',
            field=models.CharField(blank=True, help_text='Tipo de contenido del enlace roto (si está disponible).', max_length=255, null=True, verbose_name='Tipo de Contenido'),
        ),
    ]
