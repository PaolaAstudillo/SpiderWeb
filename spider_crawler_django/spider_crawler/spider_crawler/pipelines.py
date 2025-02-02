from asgiref.sync import sync_to_async
from urllib.parse import urlparse
from monitoring_app.models import Enlace, Pagina
import logging

logger = logging.getLogger(__name__)

def is_valid_url(url):
    parsed = urlparse(url)
    return bool(parsed.netloc) and bool(parsed.scheme)

@sync_to_async
def process_pagina(url, codigo_estado):
    try:
        if not is_valid_url(url):
            logger.warning(f"URL no válida: {url}")
            return None
        pagina, created = Pagina.objects.get_or_create(url=url)
        pagina.codigo_estado = codigo_estado
        pagina.save()
        return pagina
    except Exception as e:
        logger.error(f"Error al procesar la página {url}: {e}")
        return None

@sync_to_async
def process_enlaces(enlaces, pagina_origen):
    try:
        paginas_enlazadas = []
        enlaces_creados = []

        for enlace in enlaces:
            if is_valid_url(enlace):
                pagina_enlazada, created = Pagina.objects.get_or_create(url=enlace)
                paginas_enlazadas.append(pagina_enlazada)
                enlaces_creados.append(Enlace(pagina_origen=pagina_origen, pagina_destino=pagina_enlazada))

        # Crear todos los enlaces en un solo paso
        Enlace.objects.bulk_create(enlaces_creados, ignore_conflicts=True)
    except Exception as e:
        logger.error(f"Error al procesar enlaces: {e}")

class PipelineDjango:
    async def process_item(self, item, spider):
        # Process Pagina
        pagina = await process_pagina(item['url'], item['codigo_estado'])

        # Process Enlaces (if any)
        if 'enlaces' in item and pagina:
            await process_enlaces(item['enlaces'], pagina)

        return item
