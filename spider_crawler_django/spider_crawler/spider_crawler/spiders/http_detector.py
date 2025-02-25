import logging
import re
from urllib.parse import urljoin, urlparse, unquote
from arrow import now
import requests
import httpx
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

from monitoring_app.models import EnlaceRoto, Pagina
from webdriver_manager.chrome import ChromeDriverManager

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
                #uso etiquetas para incluier contenido 
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
                return response.status_code  # Devuelve el código de estado HTTP
        except httpx.TimeoutException:
            logger.error(f"⏳ Timeout en {self.url}")
            return 408  # Request Timeout
        except httpx.HTTPStatusError as e:
            logger.error(f"⚠️ Error HTTP en {self.url}: {e.response.status_code}")
            return e.response.status_code
        except httpx.RequestError as e:
            logger.error(f"❌ Error de conexión en {self.url}: {e}")
            return 503  # Service Unavailable

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

    async def detectar_estado_http_300(self):
        """
        Detecta el estado HTTP de una URL, manejando específicamente los códigos de redireccionamiento (3xx).
        Además, detecta redirecciones que involucran cambios en la codificación de la URL.

        :return: El código de estado HTTP final después de seguir las redirecciones, o None si ocurre un error.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.url, follow_redirects=True, timeout=30)
            
            status_code = response.status_code
            logger.info(f"🌐 Estado HTTP final de {self.url}: {status_code}")
            
            if 300 <= status_code < 400:
                logger.info(f"🔀 Redireccionamiento detectado: {status_code}")
                final_url = str(response.url)
                logger.info(f"🔀 Redireccionado a: {final_url}")
                
                original_parsed = urlparse(self.url)
                final_parsed = urlparse(final_url)
                
                original_path = unquote(original_parsed.path)
                final_path = unquote(final_parsed.path)
                
                if original_path != final_path:
                    logger.info(f"🔀 Cambio en la codificación de la URL detectado: {original_path} -> {final_path}")
            
            return status_code
        
        except httpx.TimeoutException:
            logger.error(f"⏳ Timeout al conectar con {self.url}")
            return 408  # Request Timeout
        
        except httpx.RequestError as e:
            logger.error(f"🔌 Error de conexión con {self.url}: {e}")
            return 503  # Service Unavailable
        
        except Exception as e:
            logger.error(f"❌ Error inesperado: {e}")
            return None

    async def detectar_redireccionamientos_complejos(self):
        """
        Detecta redireccionamientos complejos, incluyendo cambios en la codificación de la URL.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.url, follow_redirects=False, timeout=30)
                
                if response.status_code in (301, 302, 307, 308):
                    location = response.headers.get('Location')
                    if location:
                        new_url = urljoin(self.url, location)
                        logger.info(f"🔀 Redireccionamiento detectado: {self.url} -> {new_url}")
                        
                        # Verificar si hay cambios en la codificación de la URL
                        original_parsed = urlparse(self.url)
                        new_parsed = urlparse(new_url)
                        
                        original_path = unquote(original_parsed.path)
                        new_path = unquote(new_parsed.path)
                        
                        if original_path != new_path:
                            logger.info(f"🔀 Cambio en la codificación de la URL detectado: {original_path} -> {new_path}")
                        
                        return await self.detectar_estado_http_300()
                    else:
                        logger.warning(f"⚠️ Redireccionamiento sin cabecera 'Location': {self.url}")
                        return response.status_code
                else:
                    return response.status_code
        except httpx.TimeoutException:
            logger.error(f"⏳ Timeout al conectar con {self.url}")
            return 408  # Request Timeout
        except httpx.RequestError as e:
            logger.error(f"🔌 Error de conexión con {self.url}: {e}")
            return 503  # Service Unavailable
        except Exception as e:
            logger.error(f"❌ Error inesperado: {e}")
            return None



    async def detectar_estado_403(self):
        """
        Detecta si una página devuelve un error 403, ya sea en páginas dinámicas o estáticas.
        
        :return: El código de estado HTTP (403 si se detecta, None si no).
        """
        try:
            # 1. Verificación inicial con httpx (para páginas estáticas)
            async with httpx.AsyncClient() as client:
                response = await client.get(self.url, timeout=30)
            
            # Verificar el código de estado HTTP
            if response.status_code == 403:
                logger.warning(f"🚫 Acceso prohibido (403) detectado en {self.url} (HTTPX)")
                return 403
            
            # Analizar el contenido HTML para buscar indicadores comunes de 403
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Verificar el título y el contenido HTML estático
            if self._buscar_indicadores_403(soup):
                logger.warning(f"🚫 Acceso prohibido (403) detectado en el contenido estático de la página: {self.url}")
                return 403
            
            # 2. Verificación con Selenium (para páginas dinámicas con JavaScript)
            chrome_options = Options()
            chrome_options.add_argument("--headless")  # Ejecutar en modo sin cabeza (headless)
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            
            # Configurar el WebDriver de Selenium
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
            driver.get(self.url)
            
            # Obtener el HTML renderizado después de ejecutar JavaScript
            content = driver.page_source
            soup_dynamic = BeautifulSoup(content, 'html.parser')
            
            # Verificar el título y el contenido dinámico
            if self._buscar_indicadores_403(soup_dynamic):
                logger.warning(f"🚫 Acceso prohibido (403) detectado en el contenido dinámico de la página: {self.url}")
                driver.quit()
                return 403
            
            logger.info(f"✅ No se detectó ningún error 403 en la página dinámica: {self.url}")
            driver.quit()
            return None
        
        except httpx.TimeoutException:
            logger.error(f"⏳ Timeout al conectar con {self.url} (HTTPX)")
            return 408  # Request Timeout
        
        except httpx.RequestError as e:
            logger.error(f"🔌 Error de conexión con {self.url} (HTTPX): {e}")
            return 503  # Service Unavailable
        
        except Exception as e:
            logger.error(f"❌ Error inesperado en {self.url}: {e}")
            return None

    def _buscar_indicadores_403(self, soup):
        """
        Busca indicadores de error 403 en el contenido HTML de una página.
        
        :param soup: Objeto BeautifulSoup con el contenido HTML de la página.
        :return: True si se detecta un error 403, False en caso contrario.
        """
        # Buscar en el título
        title = soup.find('title')
        if title and re.search(r'403|access denied|forbidden', title.text, re.IGNORECASE):
            return True
        
        # Buscar en elementos de texto comunes
        error_messages = soup.find_all(text=re.compile(r'403|access denied|forbidden', re.IGNORECASE))
        if error_messages:
            return True
        
        return False



    async def detectar_estado_404(self):
        """
        Detecta si una página devuelve un error 404, ya sea por código de estado o por contenido.
        
        :return: El código de estado HTTP (404 si se detecta, None si no).
        """
        try:
            # Realizar la solicitud HTTP
            async with httpx.AsyncClient() as client:
                response = await client.get(self.url, timeout=30)
            
            # Verificar el código de estado HTTP
            if response.status_code == 404:
                logger.warning(f"🚫 404 detectado por código de estado en {self.url}")
                return 404
            
            # Analizar el contenido HTML para buscar indicadores comunes de 404
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Buscar en el título
            title = soup.find('title')
            if title and re.search(r'404|not found|page not found', title.text, re.IGNORECASE):
                logger.warning(f"🚫 404 detectado en el título de la página: {self.url}")
                return 404
            
            # Buscar en elementos span u otros que puedan contener mensajes de error
            error_messages = soup.find_all(text=re.compile(r'404|not found|page not found', re.IGNORECASE))
            if error_messages:
                logger.warning(f"🚫 404 detectado en el contenido de la página: {self.url}")
                return 404
            
            # Si no se encuentra ningún indicador de 404
            logger.info(f"✅ No se detectó ningún error 404 en {self.url}")
            return None
        
        except httpx.TimeoutException:
            logger.error(f"⏳ Timeout al conectar con {self.url}")
            return 408  # Request Timeout
        
        except httpx.RequestError as e:
            logger.error(f"🔌 Error de conexión con {self.url}: {e}")
            return 503  # Service Unavailable
        
        except Exception as e:
            logger.error(f"❌ Error inesperado en {self.url}: {e}")
            return None






    async def detectar_estado_500(self):
        """
        Detecta si una página devuelve un error 500, ya sea por código de estado o por contenido.
        
        :return: El código de estado HTTP (500 si se detecta, None si no).
        """
        try:
            # Realizar la solicitud HTTP
            async with httpx.AsyncClient() as client:
                response = await client.get(self.url, timeout=30)
            
            # Verificar el código de estado HTTP
            if response.status_code == 500:
                logger.error(f"💥 Error del servidor (500): {self.url}")
                return 500
            
            # Analizar el contenido HTML para buscar indicadores comunes de 500
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Buscar en el título
            title = soup.find('title')
            if title and re.search(r'500|server error', title.text, re.IGNORECASE):
                logger.error(f"💥 Error del servidor (500) detectado en el título de la página: {self.url}")
                return 500
            
            # Buscar en elementos span u otros que puedan contener mensajes de error
            error_messages = soup.find_all(text=re.compile(r'500|server error', re.IGNORECASE))
            if error_messages:
                logger.error(f"💥 Error del servidor (500) detectado en el contenido de la página: {self.url}")
                return 500
            
            # Si no se encuentra ningún indicador de 500
            logger.info(f"✅ No se detectó ningún error 500 en {self.url}")
            return None
        
        except httpx.TimeoutException:
            logger.error(f"⏳ Timeout al conectar con {self.url}")
            return 408  # Request Timeout
        
        except httpx.RequestError as e:
            logger.error(f"🔌 Error de conexión con {self.url}: {e}")
            return 503  # Service Unavailable
        
        except Exception as e:
            logger.error(f"❌ Error inesperado en {self.url}: {e}")
            return None

    async def detectar_estado_http_completo(self):
        """
        Detecta el estado HTTP completo de una URL, manejando todos los códigos de estado posibles.
        
        :return: El código de estado HTTP final, o None si ocurre un error.
        """
        try:
            # Primero, verificar el estado HTTP básico
            status_code = await self.detectar_estado_http_requests()
            
            if status_code is None:
                return None
            
            # Manejar redireccionamientos
            if 300 <= status_code < 400:
                status_code = await self.detectar_estado_http_300()
            
            # Manejar errores específicos
            if status_code == 404:
                return await self.detectar_estado_404()
            elif status_code == 500:
                return await self.detectar_estado_500()
            
            return status_code
        
        except Exception as e:
            logger.error(f"❌ Error inesperado en {self.url}: {e}")
            return None
        


    async def detectar_estado_http_robusto(self):
        """
        Detecta el estado HTTP de una URL de manera robusta, manejando todos los posibles errores,
        redireccionamientos y códigos de estado específicos como 403, 404, 500, etc.
        Es compatible con páginas estáticas y dinámicas (JavaScript).
        
        :return: El código de estado HTTP final, o None si ocurre un error.
        """
        try:
            # 1. Verificación inicial con httpx (para páginas estáticas)
            status_code = await self.detectar_estado_http_requests()
            
            if status_code is None:
                logger.error(f"❌ No se pudo obtener el estado HTTP para {self.url}")
                return None
            
            # 2. Manejar redireccionamientos (códigos 3xx)
            if 300 <= status_code < 400:
                logger.info(f"🔀 Redireccionamiento detectado para {self.url}")
                status_code = await self.detectar_estado_http_300()
            
            # 3. Manejar errores específicos
            if status_code == 403:
                logger.warning(f"🚫 Acceso prohibido (403) detectado en {self.url}")
                return 403
            elif status_code == 404:
                logger.warning(f"🚫 Página no encontrada (404) detectada en {self.url}")
                return 404
            elif status_code == 500:
                logger.error(f"💥 Error del servidor (500) detectado en {self.url}")
                return 500
            elif status_code == 408:
                logger.error(f"⏳ Timeout al conectar con {self.url}")
                return 408
            elif status_code == 503:
                logger.error(f"🔌 Servicio no disponible (503) detectado en {self.url}")
                return 503
            
            # 4. Si el código de estado es 200, verificamos el contenido para asegurarnos de que no hay errores ocultos
            if status_code == 200:
                logger.info(f"✅ Página cargada correctamente: {self.url}")
                
                # Verificar errores ocultos en el contenido (p.ej., 404 o 500 en el título o contenido)
                if await self.detectar_estado_404():
                    return 404
                if await self.detectar_estado_500():
                    return 500
                
                # Verificar contenido dinámico con Selenium si es necesario
                if await self._es_pagina_dinamica():
                    logger.info(f"🌐 La página parece ser dinámica, usando Selenium para verificar el contenido.")
                    status_code_dinamico = await self._verificar_contenido_dinamico()
                    if status_code_dinamico is not None:
                        return status_code_dinamico
            
            # 5. Si no se detectaron errores específicos, devolvemos el código de estado
            return status_code
        
        except httpx.TimeoutException:
            logger.error(f"⏳ Timeout al conectar con {self.url}")
            return 408  # Request Timeout
        
        except httpx.RequestError as e:
            logger.error(f"🔌 Error de conexión con {self.url}: {e}")
            return 503  # Service Unavailable
        
        except Exception as e:
            logger.error(f"❌ Error inesperado en {self.url}: {e}")
            return None

    async def _es_pagina_dinamica(self):
        """
        Determina si una página es dinámica (usa JavaScript) analizando el contenido inicial.
        
        :return: True si la página es dinámica, False en caso contrario.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.url, timeout=30)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Buscar scripts o elementos que indiquen que la página es dinámica
                scripts = soup.find_all('script')
                if scripts:
                    logger.info(f"📜 Se detectaron scripts en {self.url}, la página puede ser dinámica.")
                    return True
                return False
        except Exception as e:
            logger.error(f"❌ Error al verificar si la página es dinámica: {e}")
            return False

    async def _verificar_contenido_dinamico(self):
        """
        Verifica el contenido de una página dinámica usando Selenium.
        
        :return: El código de estado HTTP detectado, o None si no se encontraron errores.
        """
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Ejecutar en modo sin cabeza (headless)
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        driver = None
        try:
            # Configurar el WebDriver de Selenium
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
            driver.get(self.url)
            
            # Esperar a que la página se cargue completamente
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            
            # Obtener el HTML renderizado después de ejecutar JavaScript
            content = driver.page_source
            soup = BeautifulSoup(content, 'html.parser')
            
            # Verificar errores en el contenido dinámico
            if self._buscar_indicadores_404(soup):
                logger.warning(f"🚫 404 detectado en el contenido dinámico de la página: {self.url}")
                return 404
            elif self._buscar_indicadores_500(soup):
                logger.error(f"💥 Error del servidor (500) detectado en el contenido dinámico de la página: {self.url}")
                return 500
            
            logger.info(f"✅ No se detectaron errores en el contenido dinámico de la página: {self.url}")
            return None
        except Exception as e:
            logger.error(f"❌ Error al verificar el contenido dinámico: {e}")
            return None
        finally:
            if driver:
                driver.quit()
                logger.info("🔒 WebDriver de Selenium cerrado correctamente.")

    def _buscar_indicadores_404(self, soup):
        """
        Busca indicadores de error 404 en el contenido HTML de una página.
        
        :param soup: Objeto BeautifulSoup con el contenido HTML de la página.
        :return: True si se detecta un error 404, False en caso contrario.
        """
        title = soup.find('title')
        if title and re.search(r'404|not found|page not found', title.text, re.IGNORECASE):
            return True
        
        error_messages = soup.find_all(text=re.compile(r'404|not found|page not found', re.IGNORECASE))
        if error_messages:
            return True
        
        return False

    def _buscar_indicadores_500(self, soup):
        """
        Busca indicadores de error 500 en el contenido HTML de una página.
        
        :param soup: Objeto BeautifulSoup con el contenido HTML de la página.
        :return: True si se detecta un error 500, False en caso contrario.
        """
        title = soup.find('title')
        if title and re.search(r'500|server error', title.text, re.IGNORECASE):
            return True
        
        error_messages = soup.find_all(text=re.compile(r'500|server error', re.IGNORECASE))
        if error_messages:
            return True
        
        return False