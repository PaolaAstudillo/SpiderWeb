import asyncio
import logging
from collections import defaultdict
from urllib.parse import urljoin, urlparse
from asgiref.sync import sync_to_async
from django.utils.timezone import now
import requests
from scrapy import signals, Spider, Request
from monitoring_app.models import Pagina, Enlace
import httpx
from django.db.models import Count
import signal
import http.client
import pycurl
from io import BytesIO
from fake_useragent import UserAgent
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger(__name__)

class EstadoHTTPDetector:
    def __init__(self, url):
        self.url = url

    def detectar_estado_http_selenium(self):
        """Detecta el estado HTTP usando requests y Selenium."""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        service = Service('C:/chromedriver/chromedriver.exe')
        driver = None

        try:
            # Verificar el estado HTTP con requests primero
            response = requests.get(self.url, timeout=30, verify=False)
            status_code = response.status_code
            logger.info(f"🌐 Estado HTTP de {self.url}: {status_code}")

            if status_code == 200:
                # Si el estado HTTP es exitoso, usar Selenium para verificar el contenido
                driver = webdriver.Chrome(service=service, options=chrome_options)
                driver.get(self.url)
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

                # Verificar contenido de la página para estados específicos
                page_source = driver.page_source
                if "404" in driver.title or "Page Not Found" in page_source:
                    logger.warning(f"🚫 Página no encontrada (404): {self.url}")
                    return 404
                elif "500" in driver.title or "Server Error" in page_source:
                    logger.error(f"💥 Error del servidor (500): {self.url}")
                    return 500
                else:
                    logger.info(f"✅ Página cargada correctamente: {self.url}")
                    return 200
            else:
                logger.warning(f"⚠️ La solicitud a {self.url} devolvió el código {status_code}")
                return status_code
        except requests.exceptions.Timeout:
            logger.error(f"⏳ Timeout al conectar con {self.url}")
            return 408  # Request Timeout
        except requests.exceptions.ConnectionError:
            logger.error(f"🔌 Error de conexión con {self.url}")
            return 503  # Service Unavailable
        except Exception as e:
            logger.error(f"❌ Error inesperado: {e}")
            return None
        finally:
            if driver:
                driver.quit()   


    async def detectar_estado_http_requests(self):
        """Detecta el estado HTTP usando httpx con manejo avanzado de errores."""
        try:
            headers = {'User-Agent': UserAgent().random}
            async with httpx.AsyncClient(timeout=10, follow_redirects=True, headers=headers, verify=False) as client:
                response = await client.get(self.url)
                return response
        except httpx.TimeoutException:
            logger.error(f"⏳ Timeout en {self.url}")
        except httpx.HTTPStatusError as e:
            logger.error(f"⚠️ Error HTTP en {self.url}: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"❌ Error de conexión en {self.url}: {e}")
        return None

    def detectar_estado_http_http_client(self):
        """Detecta el estado HTTP usando http.client."""
        try:
            # Parsear la URL para extraer esquema, host y ruta
            parsed_url = urlparse(self.url)
            scheme = parsed_url.scheme
            netloc = parsed_url.netloc
            path = parsed_url.path or "/"

            # Verificar que la URL tenga un esquema y un host válidos
            if not scheme or not netloc:
                logger.error(f"❌ URL inválida: {self.url}")
                return None

            # Configurar la conexión según el esquema
            conn = (http.client.HTTPSConnection(netloc) if scheme == "https" 
                    else http.client.HTTPConnection(netloc))

            # Realizar la solicitud HTTP GET
            logger.info(f"🌐 Conectando a {scheme}://{netloc}{path}")
            conn.request("GET", path)
            response = conn.getresponse()
            status_code = response.status
            reason = response.reason

            # Loguear el resultado
            logger.info(f"✅ Respuesta recibida: {status_code} {reason}")
            return status_code
        except http.client.HTTPException as http_err:
            logger.error(f"❌ Error de protocolo HTTP: {http_err}")
            return None
        except Exception as e:
            logger.error(f"❌ Error inesperado: {e}")
            return None
        finally:
            try:
                # Asegurar el cierre de la conexión
                if 'conn' in locals() and conn:
                    conn.close()
                    logger.info("🔒 Conexión cerrada correctamente")
            except Exception as close_err:
                logger.warning(f"⚠️ Error al cerrar la conexión: {close_err}")


    def detectar_estado_http_pycurl(self):
        """Detecta el estado HTTP usando PyCurl"""
        buffer = BytesIO()
        c = pycurl.Curl()

        try:
            # Configuración de PyCurl
            logger.info(f"🌐 Conectando a {self.url} usando PyCurl")
            c.setopt(c.URL, self.url)
            c.setopt(c.WRITEDATA, buffer)  # Donde almacenar la respuesta
            c.setopt(c.FOLLOWLOCATION, True)  # Seguir redirecciones
            c.setopt(c.TIMEOUT, 10)  # Timeout de la conexión
            c.setopt(c.SSL_VERIFYPEER, 0)  # Deshabilitar la verificación SSL (no recomendado en producción)
            c.setopt(c.SSL_VERIFYHOST, 0)  # Deshabilitar la verificación del host

            # Realizar la solicitud
            c.perform()

            # Obtener el código de estado HTTP
            status_code = c.getinfo(c.RESPONSE_CODE)
            logger.info(f"✅ Respuesta recibida: {status_code}")
            return status_code
        except pycurl.error as curl_err:
            logger.error(f"❌ Error de PyCurl: {curl_err}")
            return None
        except Exception as e:
            logger.error(f"❌ Error inesperado: {e}")
            return None
        finally:
            try:
                c.close()
                logger.info("🔒 Conexión cerrada correctamente con PyCurl")
            except Exception as close_err:
                logger.warning(f"⚠️ Error al cerrar la conexión de PyCurl: {close_err}")

    def detectar_estado_http_300(url):
        """
        Detecta el estado HTTP de una URL, manejando específicamente los códigos de redireccionamiento (3xx).
        
        :param url: La URL a la que se desea hacer la solicitud.
        :return: El código de estado HTTP final después de seguir las redirecciones, o None si ocurre un error.
        """
        try:
            # Realizar la solicitud HTTP GET con redirecciones automáticas
            response = requests.get(url, timeout=30, allow_redirects=True)
            
            # Obtener el código de estado HTTP final
            status_code = response.status_code
            logger.info(f"🌐 Estado HTTP final de {url}: {status_code}")
            
            # Si el código de estado es 3xx, loguear la redirección
            if 300 <= status_code < 400:
                logger.info(f"🔀 Redireccionamiento detectado: {status_code}")
                # Obtener la URL final después de las redirecciones
                final_url = response.url
                logger.info(f"🔀 Redireccionado a: {final_url}")
            
            return status_code
        
        except requests.exceptions.Timeout:
            logger.error(f"⏳ Timeout al conectar con {url}")
            return 408  # Request Timeout
        
        except requests.exceptions.ConnectionError:
            logger.error(f"🔌 Error de conexión con {url}")
            return 503  # Service Unavailable
        
        except requests.exceptions.TooManyRedirects:
            logger.error(f"🔀 Demasiadas redirecciones en {url}")
            return 310  # Too Many Redirects (código personalizado para este caso)
        
        except Exception as e:
            logger.error(f"❌ Error inesperado: {e}")
            return None

class HTTPStatusLogger:
    def __init__(self):
        self.http_status_counts = defaultdict(int)
        self.error_links = []

    def log_http_status(self, response):
        """Registra los códigos HTTP y maneja cada estado de manera adecuada."""
        if response is None:
            logger.warning("⚠️ Respuesta sin código HTTP.")
            return

        if hasattr(response, 'status_code'):
            status_code = response.status_code
            url = str(response.url)
        else:
            status_code = response
            url = "URL no disponible"

        self.http_status_counts[status_code] += 1

        status_handlers = {
            200: lambda: logger.info(f"✅ [200] Enlace funcional: {url}"),
            301: lambda: self._handle_redirect(response, "🔄 [301] Redirección permanente"),
            302: lambda: self._handle_redirect(response, "🔄 [302] Redirección temporal"),
            307: lambda: self._handle_redirect(response, "🔄 [307] Redirección temporal"),
            308: lambda: self._handle_redirect(response, "🔄 [308] Redirección permanente"),
            400: lambda: self._handle_error_link(response, "⚠️ Solicitud incorrecta (400)"),
            401: lambda: self._handle_error_link(response, "🔑 Autenticación requerida (401)"),
            403: lambda: self._handle_error_link(response, "🚫 Acceso denegado (403)"),
            404: lambda: self._handle_error_link(response, "🚨 Enlace roto (404)"),
            429: lambda: self._handle_error_link(response, "⏳ Demasiadas solicitudes (429)"),
            500: lambda: self._handle_error_link(response, "🛑 Error interno del servidor (500)"),
            503: lambda: self._handle_error_link(response, "🚧 Servicio no disponible (503)"),
            "4xx": lambda: self._handle_error_link(response, f"⚠️ Error del cliente ({status_code})"),
            "5xx": lambda: self._handle_error_link(response, f"🛑 Error del servidor ({status_code})"),
            "default": lambda: logger.warning(f"🔶 [{status_code}] Código HTTP inesperado en {url}"),
        }

        handler = (
            status_handlers.get(status_code)
            or (status_handlers["4xx"] if 400 <= status_code < 500 else None)
            or (status_handlers["5xx"] if 500 <= status_code < 600 else None)
            or status_handlers["default"]
        )
        handler()

    def _handle_redirect(self, response, message):
        redirect_url = response.headers.get("Location", "desconocida") if hasattr(response, 'headers') else "desconocida"
        logger.info(f"{message} a {redirect_url}")

    def _handle_error_link(self, response, message):
        url = str(response.url) if hasattr(response, 'url') else "URL no disponible"
        status_code = response.status_code if hasattr(response, 'status_code') else response
        self.error_links.append((url, status_code))
        logger.error(f"{message} [{status_code}]: {url}")

class SpiderSitio(Spider):
    name = 'spider_sitio'

    def __init__(self, dominio=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not dominio:
            raise ValueError("❌ Debes especificar un dominio con -a dominio=<dominio>")

        parsed = urlparse(dominio if dominio.startswith("http") else f"https://{dominio}")
        if not parsed.netloc:
            raise ValueError(f"❌ Dominio inválido: {dominio}")

        self.start_urls = [parsed.geturl()]
        self.allowed_domains = [parsed.netloc]
        self.visited = set()
        self.discovered = set()
        self.http_status_logger = HTTPStatusLogger()
        self.tasks = []
        logger.info(f"🚀 Spider inicializado para el dominio: {dominio}")

        signal.signal(signal.SIGINT, self.handle_interrupt)
        signal.signal(signal.SIGTERM, self.handle_interrupt)

    def handle_interrupt(self, signum, frame):
        """Maneja SIGINT  y SIGTERM para cerrar adecuadamente el Spider."""
        logger.warning(f"🛑 Señal de interrupción recibida ({signum}). Deteniendo el Spider...")
        self.crawler.engine.close_spider(self, "interrupted")

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_closed, signal=signals.spider_closed)
        return spider

    async def _save_pagina_data(self, url, status):
        try:
            pagina, created = await sync_to_async(Pagina.objects.get_or_create)(url=url, defaults={"created_at": now()})
            await sync_to_async(pagina.actualizar_ultima_consulta)(status)
            logger.info(f"💾 Página guardada: {url} (creada: {created})")
            return pagina
        except Exception as e:
            logger.error(f"❌ Error al guardar datos de la página {url}: {e}")
            return None

    async def _save_enlace_data(self, origen, destino):
        try:
            _, enlace_creado = await sync_to_async(Enlace.objects.get_or_create)(pagina_origen=origen, pagina_destino=destino)
            if enlace_creado:
                logger.info(f"🔗 Enlace creado: {origen.url} -> {destino.url}")
                await self._check_if_huerfana(destino)
            return enlace_creado
        except Exception as e:
            logger.error(f"❌ Error al guardar enlace entre {origen.url} y {destino.url}: {e}")
            return False

    async def _check_if_huerfana(self, pagina):
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

    async def parse(self, response):
        try:
            if response.url in self.visited:
                return

            self.visited.add(response.url)
            logger.info(f"🔎 Visitando: {response.url}")
            logger.info(f"Visiting {response.url}")  # Log para la vista de Django

            # Detectar código HTTP usando múltiples métodos
            detector = EstadoHTTPDetector(response.url)
            tasks = [
                detector.detectar_estado_http_requests(),
                sync_to_async(detector.detectar_estado_http_selenium)(),
                sync_to_async(detector.detectar_estado_http_http_client)(),
                sync_to_async(detector.detectar_estado_http_pycurl)(),
                sync_to_async(detector.detectar_estado_http_300)()

              
            ]
           
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"❌ Error en una de las tareas: {result}")
                elif result is not None:
                    self.http_status_logger.log_http_status(result)

            # Registrar en la BD
            pagina_actual = await self._save_pagina_data(response.url, response.status)

            # Usar BeautifulSoup para extraer enlaces de páginas dinámicas
            soup = BeautifulSoup(response.text, 'html.parser')
            enlaces = [a['href'] for a in soup.find_all('a', href=True)]
            logger.info(f"🔗 Enlaces encontrados en {response.url}: {len(enlaces)}")

            for enlace in enlaces:
                enlace_completo = urljoin(response.url, enlace)
                parsed_enlace = urlparse(enlace_completo)
                if parsed_enlace.netloc not in self.allowed_domains:
                    logger.info(f"🚫 Enlace fuera del dominio permitido: {enlace_completo}")
                    continue

                if enlace_completo in self.visited or enlace_completo == response.url:
                    continue

                self.discovered.add(enlace_completo)
                logger.info(f"🔗 Nuevo enlace descubierto: {enlace_completo}")
                logger.info(f"Discovered {enlace_completo}")  # Log para la vista de Django

                pagina_destino = await self._save_pagina_data(enlace_completo, None)
                await self._save_enlace_data(pagina_actual, pagina_destino)

                yield Request(enlace_completo, callback=self.parse)

        except Exception as e:
            logger.error(f"❌ Error procesando {response.url}: {e}")

    async def spider_closed(self, reason):
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