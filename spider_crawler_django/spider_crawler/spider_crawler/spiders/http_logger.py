# http_logger.py
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

class HTTPStatusLogger:
    def __init__(self):
        """
        Inicializa el logger de estados HTTP.
        """
        self.http_status_counts = defaultdict(int)  # Conteo de códigos HTTP
        self.error_links = []  # Lista de enlaces con errores

    def log_http_status(self, response, url=None):
        """
        Registra los códigos HTTP y maneja cada estado según corresponda.

        :param response: Objeto de respuesta HTTP o código de estado.
        :param url: URL asociada al estado (si no está en la respuesta).
        """
        # Validar si se recibió una respuesta válida
        if response is None:
            logger.warning("⚠️ Respuesta sin código HTTP. URL no especificada.")
            return

        # Determinar el código de estado y la URL
        status_code = getattr(response, "status_code", response)
        url = str(getattr(response, "url", url)) or "URL no disponible"

        # Incrementar el conteo del código de estado
        self.http_status_counts[status_code] += 1

        # Mapeo de códigos de estado a manejadores específicos
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

        # Seleccionar el manejador adecuado
        handler = (
            status_handlers.get(status_code)
            or (status_handlers["4xx"] if 400 <= status_code < 500 else None)
            or (status_handlers["5xx"] if 500 <= status_code < 600 else None)
            or status_handlers["default"]
        )
        handler()

    def _handle_redirect(self, response, message):
        """
        Maneja los códigos de redirección.

        :param response: Respuesta HTTP.
        :param message: Mensaje de redirección.
        """
        redirect_url = response.headers.get("Location", "desconocida") if hasattr(response, "headers") else "desconocida"
        logger.info(f"{message} a {redirect_url}")

    def _handle_error_link(self, response, message):
        """
        Registra un enlace con error.

        :param response: Respuesta HTTP o código de estado.
        :param message: Mensaje de error.
        """
        url = str(getattr(response, "url", "URL no disponible"))
        status_code = getattr(response, "status_code", response)
        self.error_links.append((url, status_code))
        logger.error(f"{message} [{status_code}]: {url}")

    def summarize_logs(self):
        """
        Imprime un resumen de los códigos de estado HTTP registrados.
        """
        logger.info("📊 Resumen de códigos HTTP:")
        for status, count in sorted(self.http_status_counts.items()):
            logger.info(f" - {status}: {count} ocurrencias")

        if self.error_links:
            logger.info("🚨 Enlaces con errores:")
            for url, status in self.error_links:
                logger.info(f" - {status}: {url}")

    def clear_logs(self):
        """
        Limpia los registros de códigos HTTP y enlaces con errores.
        """
        self.http_status_counts.clear()
        self.error_links.clear()
        logger.info("🧹 Registros de códigos HTTP y enlaces con errores limpiados.")

    def get_error_links(self):
        """
        Devuelve la lista de enlaces con errores.

        :return: Lista de tuplas (URL, código de estado).
        """
        return self.error_links

    def get_status_counts(self):
        """
        Devuelve el conteo de códigos de estado HTTP.

        :return: Diccionario con el conteo de códigos de estado.
        """
        return dict(self.http_status_counts)

