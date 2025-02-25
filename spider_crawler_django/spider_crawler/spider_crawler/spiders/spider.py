import asyncio
import logging
import signal
from urllib.parse import urljoin, urlparse
from asgiref.sync import sync_to_async
from django.utils.timezone import now
import requests
from scrapy import signals, Spider, Request
from monitoring_app.models import EnlaceRoto, Pagina, Enlace
from django.db.models import Count
from bs4 import BeautifulSoup
from .http_detector import EstadoHTTPDetector
from .http_logger import HTTPStatusLogger

logger = logging.getLogger(__name__)

class SpiderSitio(Spider):
    name = 'spider_sitio'

    def __init__(self, dominio=None, *args, **kwargs):
        """
        Inicializa el spider con el dominio especificado.
        :param dominio: Dominio a rastrear.
        """
        super().__init__(*args, **kwargs)
        if not dominio:
            raise ValueError("❌ Debes especificar un dominio con -a dominio=<dominio>")

        # Parsear el dominio para asegurar que sea válido
        parsed = urlparse(dominio if dominio.startswith("http") else f"https://{dominio}")
        if not parsed.netloc:
            raise ValueError(f"❌ Dominio inválido: {dominio}")

        # Configurar URLs iniciales y dominios permitidos
        self.start_urls = [parsed.geturl()]
        self.allowed_domains = [parsed.netloc]
        self.visited = set()  # URLs ya visitadas
        self.discovered = set()  # URLs descubiertas pero no visitadas
        self.http_status_logger = HTTPStatusLogger()  # Logger para códigos HTTP
        self.tasks = []  # Tareas asíncronas pendientes
        logger.info(f"🚀 Spider inicializado para el dominio: {dominio}")

        # Manejar señales de interrupción (Ctrl+C o terminación)
        signal.signal(signal.SIGINT, self.handle_interrupt)
        signal.signal(signal.SIGTERM, self.handle_interrupt)

    def handle_interrupt(self, signum, frame):
        """
        Maneja señales de interrupción (SIGINT y SIGTERM) para cerrar el spider de manera segura.
        """
        logger.warning(f"🛑 Señal de interrupción recibida ({signum}). Deteniendo el Spider...")
        self.crawler.engine.close_spider(self, "interrupted")

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        """
        Método de clase para crear una instancia del spider y conectar señales.
        """
        spider = super().from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_closed, signal=signals.spider_closed)
        return spider

    async def _save_pagina_data(self, url, status):
        """
        Guarda los datos de una página en la base de datos.
        :param url: URL de la página.
        :param status: Código de estado HTTP.
        :return: Instancia de la página guardada.
        """
        try:
            pagina, created = await sync_to_async(Pagina.objects.update_or_create)(
                url=url,
                defaults={
                    "created_at": now(),
                    "codigo_estado": status,
                }
            )
            if not created:
                await sync_to_async(pagina.actualizar_ultima_consulta)(status)
            logger.info(f"💾 Página guardada: {url} (creada: {created})")
            return pagina
        except Exception as e:
            logger.error(f"❌ Error al guardar datos de la página {url}: {e}")
            return None

    async def _save_enlace_data(self, origen, destino):
        """
        Guarda un enlace entre dos páginas en la base de datos.
        :param origen: Página de origen.
        :param destino: Página de destino.
        :return: True si el enlace fue creado, False si ya existía.
        """
        try:
            _, enlace_creado = await sync_to_async(Enlace.objects.update_or_create)(
            #_, enlace_creado = await sync_to_async(Enlace.objects.get_or_create)(
                pagina_origen=origen,
                pagina_destino=destino
            )
            if enlace_creado:
                logger.info(f"🔗 Enlace creado: {origen.url} -> {destino.url}")
                await self._check_if_huerfana(destino)
            return enlace_creado
        except Exception as e:
            logger.error(f"❌ Error al guardar enlace entre {origen.url} y {destino.url}: {e}")
            return False

    async def _check_if_huerfana(self, pagina):
        """
        Verifica si una página es huérfana (sin enlaces entrantes).
        :param pagina: Página a verificar.
        """
        try:
            is_huerfana = await sync_to_async(
                lambda: Pagina.objects.filter(id=pagina.id, enlaces_entrantes__isnull=True).exists()
            )()
            if is_huerfana:
                await sync_to_async(pagina.marcar_huerfana)()
                logger.warning(f"👀 Página huérfana detectada: {pagina.url}")
        except Exception as e:
            logger.error(f"❌ Error comprobando si la página es huérfana: {e}")


    async def _detect_huerfanas(self):
        try:
            paginas_huerfanas = await sync_to_async(lambda: list(
                Pagina.objects.annotate(num_enlaces=Count('enlaces_entrantes'))
                              .filter(num_enlaces=0)
                              .exclude(url__in=self.start_urls)
                              .only("url")
            ))()
            for pagina in paginas_huerfanas:
                await sync_to_async(pagina.marcar_huerfana)()
                logger.warning(f"👀 Página huérfana detectada: {pagina.url}")
        except Exception as e:
            logger.error(f"❌ Error detectando páginas huérfanas: {e}")




    async def guardar_enlace_roto(self, pagina, url_enlace_roto, codigo_estado):
        """
        Guarda un enlace roto en la base de datos.
        :param pagina: Página donde se encontró el enlace roto.
        :param url_enlace_roto: URL del enlace roto.
        :param codigo_estado: Código de estado HTTP del enlace roto.
        :return: Instancia del enlace roto guardado.
        """
        try:
            enlace_roto, created = await sync_to_async(EnlaceRoto.objects.get_or_create)(
                pagina=pagina,
                url_enlace_roto=url_enlace_roto,
                defaults={
                    "codigo_estado": codigo_estado,
                    "detectado_en": now(),
                }
            )
            if created:
                logger.info(f"🚫 Enlace roto guardado: {url_enlace_roto} (Código: {codigo_estado}) en {pagina.url}")
            return enlace_roto
        except Exception as e:
            logger.error(f"❌ Error al guardar enlace roto {url_enlace_roto} en {pagina.url}: {e}")
            return None

    async def detectar_enlaces_rotos(self, url_base):
        """Detecta enlaces rotos en una página y recopila información detallada."""
        try:
            logger.info(f"🔍 Analizando enlaces en {url_base}")
            response = requests.get(url_base, timeout=30)
            if response.status_code != 200:
                logger.warning(f"⚠️ Página principal no accesible: {url_base} (Código {response.status_code})")
                return []

            soup = BeautifulSoup(response.text, 'html.parser')
            enlaces = soup.find_all('a', href=True)
            logger.info(f"🌐 Total de enlaces encontrados: {len(enlaces)}")

            # Obtener o crear la página en la base de datos
            pagina, created = await sync_to_async(Pagina.objects.get_or_create)(url=url_base)

            enlaces_rotos = []
            for enlace in enlaces:
                url = urljoin(url_base, enlace['href'])
                enlace_texto = enlace.get_text(strip=True) or "(Sin texto)"

                try:
                    
                    enlace_response = requests.head(url, timeout=10, allow_redirects=True)
                    if enlace_response.status_code >= 400:
                        logger.warning(f"🚨 Enlace roto detectado: {url} (Código {enlace_response.status_code})")
                        tipo_contenido = enlace_response.headers.get('Content-Type', 'Desconocido')
                        
                        # Guardar el enlace roto en la base de datos
                        await sync_to_async(EnlaceRoto.objects.create)(
                            pagina=pagina,
                            url_enlace_roto=url,
                            codigo_estado=enlace_response.status_code,
                            tipo_contenido=tipo_contenido,
                            detectado_en=now(),
                        )
                        
                        enlaces_rotos.append({
                            "pagina": url_base,
                            "url_enlace_roto": url,
                            "codigo_estado": enlace_response.status_code,
                            "tipo_contenido": tipo_contenido,
                            "contenido_enlace": enlace_texto,
                        })
                except requests.exceptions.RequestException as e:
                    logger.error(f"❌ Error al verificar {url}: {e}")
                    await sync_to_async(EnlaceRoto.objects.create)(
                        pagina=pagina,
                        url_enlace_roto=url,
                        codigo_estado=0,
                        tipo_contenido="Desconocido",
                        detectado_en=now(),
                    )
                    enlaces_rotos.append({
                        "pagina": url_base,
                        "url_enlace_roto": url,
                        "codigo_estado": 0,
                        "tipo_contenido": "Desconocido",
                        "contenido_enlace": enlace_texto,
                    })

            logger.info(f"✅ Total de enlaces rotos detectados: {len(enlaces_rotos)}")
            return enlaces_rotos

        except Exception as e:
            logger.error(f"❌ Error al analizar {url_base}: {e}")
            return []

    async def parse(self, response):
        """
        Procesa una respuesta del spider.
        :param response: Respuesta HTTP recibida.
        """
        try:
            if response.url in self.visited:
                return

            self.visited.add(response.url)
            logger.info(f"🔎 Visitando: {response.url}")

            # Detectar estado HTTP usando múltiples métodos
            detector = EstadoHTTPDetector(response.url)
            tasks = [
                detector.detectar_estado_http_requests(),
                sync_to_async(detector.detectar_estado_http_selenium)(),
                sync_to_async(detector.detectar_estado_http_http_client)(),
                sync_to_async(detector.detectar_estado_http_pycurl)(),
                detector.detectar_estado_http_300(),
                detector.detectar_redireccionamientos_complejos(),
                detector.detectar_estado_http_completo(),
                detector.detectar_estado_403(),
                detector.detectar_estado_404(),
                detector.detectar_estado_http_robusto(),
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            estado_http = None
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"❌ Error en una de las tareas: {result}")
                elif result is not None:
                    estado_http = result
                    self.http_status_logger.log_http_status(estado_http, url=response.url)
                    break  
                
            # Guardar página actual
            pagina_actual = await self._save_pagina_data(response.url, estado_http)

            # Detectar enlaces rotos en la página actual
            await self.detectar_enlaces_rotos(response.url)
            
            # Extraer enlaces de la página
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Excluir header y footer
            for element in soup.find_all(['header', 'footer']):  
                element.decompose()


            enlaces = [a['href'] for a in soup.find_all('a', href=True)]
            logger.info(f"🔗 Enlaces encontrados en {response.url}: {len(enlaces)}")

            for enlace in enlaces:
                enlace_completo = urljoin(response.url, enlace)
                parsed_enlace = urlparse(enlace_completo)

                # Filtrar enlaces fuera del dominio permitido
                if parsed_enlace.netloc not in self.allowed_domains:
                    logger.info(f"🚫 Enlace fuera del dominio permitido: {enlace_completo}")
                    continue

                # Evitar visitar enlaces ya visitados o la misma página
                if enlace_completo in self.visited or enlace_completo == response.url:
                    continue

                self.discovered.add(enlace_completo)
                logger.info(f"🔗 Nuevo enlace descubierto: {enlace_completo}")


                # Detectar el estado HTTP de la página de destino antes de guardarla
                detector_destino = EstadoHTTPDetector(enlace_completo)
                estado_http_destino = await detector_destino.detectar_estado_http_robusto()

                # Guardar página de destino y enlace
                pagina_destino = await self._save_pagina_data(enlace_completo, estado_http_destino)

                await self._save_enlace_data(pagina_actual, pagina_destino)

                # Continuar rastreando el enlace
                yield Request(enlace_completo, callback=self.parse)

        except Exception as e:
            logger.error(f"❌ Error procesando {response.url}: {e}")

    async def spider_closed(self, reason):
        """
        Método ejecutado cuando el spider se cierra.
        :param reason: Razón del cierre.
        """
        logger.info("🏁 Spider finalizado.")
        logger.info(f"📊 Total de páginas visitadas: {len(self.visited)}")
        logger.info(f"📈 Resumen de códigos HTTP: {dict(self.http_status_logger.http_status_counts)}")

        if self.http_status_logger.error_links:
            logger.error(f"🔴 Errores en {len(self.http_status_logger.error_links)} enlaces:")
            for url, status in self.http_status_logger.error_links:
                logger.error(f"❌ [{status}] {url}")

        unvisited = self.discovered - self.visited
        if unvisited:
            logger.info(f"🔍 Enlaces descubiertos pero no visitados: {len(unvisited)}")
            for url in unvisited:
                logger.info(f"🔗 {url}")

        if self.tasks:
            await asyncio.wait(self.tasks)
            logger.info("✅ Todas las tareas de guardado han finalizado.")

        await self._detect_huerfanas()  # Detectar páginas huérfanas antes de cerrar