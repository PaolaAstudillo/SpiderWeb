import json
import re
import subprocess
import sys
import threading
import time
import logging
from contextlib import contextmanager
from django.shortcuts import render
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
import psutil
from monitoring_app.forms import DominioForm
from monitoring_app.models import Pagina

# Configuración del logger
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# Variables globales para monitoreo
progreso = {
    "estado": "Esperando",
    "porcentaje": 0,
    "mensajes": [],
    "paginas_visitadas": 0,
    "paginas_descubiertas": 0,
    "errores": 0,
}
scrapy_thread = None
scrapy_running = False
scrapy_lock = threading.Lock()
proceso = None  # Declarar 'proceso' como una variable global

@contextmanager
def scrapy_context():
    """Context manager para manejar el estado de Scrapy."""
    global scrapy_running
    scrapy_running = True
    try:
        yield
    finally:
        scrapy_running = False

def ejecutar_scrapy(dominio):
    """
    Ejecuta Scrapy en un proceso separado y captura toda su salida en tiempo real.
    La salida se muestra tanto en la consola de Visual Studio Code como en la interfaz web.
    """
    global progreso, scrapy_running

    with scrapy_context():
        with scrapy_lock:
            progreso["estado"] = "Iniciando Scrapy"
            progreso["porcentaje"] = 0
            progreso["mensajes"] = ["🟢 Iniciando Scrapy..."]
            progreso["paginas_visitadas"] = 0
            progreso["paginas_descubiertas"] = 0
            progreso["errores"] = 0
            cache.set("progreso", progreso)
        logger.info("Iniciando Scrapy...")

        # Ruta del proyecto Scrapy
        scrapy_project_dir = r'C:\Users\paola\OneDrive\Escritorio\TFG2025\spider_crawler_django\spider_crawler'
        logger.info(f"Ejecutando Scrapy en: {scrapy_project_dir}")

        # Comando para ejecutar Scrapy
        comando = ['scrapy', 'crawl', 'spider_sitio', '-a', f'dominio={dominio}']

        try:
            # Iniciar el proceso
            proceso = subprocess.Popen(
                comando,
                cwd=scrapy_project_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line-buffered
                universal_newlines=True
            )

            # Función para leer y redirigir la salida
            def leer_salida(stream, tipo):
                for linea in iter(stream.readline, ''):
                    if linea:
                        with scrapy_lock:
                            #progreso["mensajes"].append(linea.strip())
                            cache.set("progreso", progreso)
                            
                        # Mostrar la salida en la consola
                         # Clasificar y mostrar el log
                        if "ERROR" in linea:
                            logger.error(f"Scrapy {tipo}: {linea.strip()}")
                        elif "WARNING" in linea:
                            logger.warning(f"Scrapy {tipo}: {linea.strip()}")
                        elif "DEBUG" in linea:
                            logger.debug(f"Scrapy {tipo}: {linea.strip()}")
                        else:
                            logger.info(f"Scrapy {tipo}: {linea.strip()}")
                        
                        # Redirigir a la consola

                        sys.stdout.write(linea)  # Redirigir a la consola
                        sys.stdout.flush()

                        if "Crawled" in linea:
                            match = re.search(r"Crawled (\d+) pages", linea)
                            if match:
                                paginas_visitadas = int(match.group(1))
                                progreso["paginas_visitadas"] = paginas_visitadas

                                # Si no hay un total fijo, usar un valor dinámico
                                total_paginas_esperadas = max(paginas_visitadas, 100)  # Mínimo 10 páginas
                                progreso["porcentaje"] = min((paginas_visitadas / total_paginas_esperadas) * 100, 100)
                                progreso["estado"] = f"Progreso: {progreso['porcentaje']}%"

                                # Actualizar el progreso en la caché
                                cache.set("progreso", progreso)


            # Hilos para leer stdout y stderr
            stdout_thread = threading.Thread(target=leer_salida, args=(proceso.stdout, "stdout"))
            stderr_thread = threading.Thread(target=leer_salida, args=(proceso.stderr, "stderr"))
            stdout_thread.start()
            stderr_thread.start()

            # Esperar a que el proceso termine
            proceso.wait()

            # Finalización del proceso
            with scrapy_lock:
                progreso["estado"] = "Terminado"
                progreso["porcentaje"] = 100
                progreso["mensajes"].append("✅ Scrapy ha finalizado.")
                cache.set("progreso", progreso)
            logger.info("Scrapy ha terminado.")

        except subprocess.CalledProcessError as e:
            logger.error(f"Error al ejecutar Scrapy: {e}")
            with scrapy_lock:
                progreso["mensajes"].append(f"❌ Error crítico: {e}")
                progreso["estado"] = "Error"
                cache.set("progreso", progreso)
        except Exception as e:
            logger.error(f"Error inesperado: {e}")
            with scrapy_lock:
                progreso["mensajes"].append(f"❌ Error inesperado: {e}")
                progreso["estado"] = "Error"
                cache.set("progreso", progreso)
        finally:
            scrapy_running = False  # Asegúrate de que scrapy_running sea False al finalizar




def limpiar_paginas_anteriores(dominio):
    """Marca las páginas del dominio anterior como inactivas."""
    Pagina.objects.filter(url__icontains=dominio).update(activa=False)
    logger.info(f"Páginas del dominio {dominio} marcadas como inactivas.")

def tablero(request):
    """
    Renderiza el tablero principal para controlar Scrapy.
    """
    if request.method == 'POST':
        form = DominioForm(request.POST)
        if form.is_valid():
            dominio = form.cleaned_data['dominio']

            # Limpiar registros anteriores para el nuevo dominio
            limpiar_paginas_anteriores(dominio)

            # Iniciar Scrapy en un hilo separado
            global scrapy_thread, scrapy_running
            if scrapy_thread is None or not scrapy_thread.is_alive():
                scrapy_thread = threading.Thread(target=ejecutar_scrapy, args=(dominio,))
                scrapy_thread.start()
                scrapy_running = True  # Asegúrate de que scrapy_running sea True
                return render(request, 'monitoring_app/tablero.html', {
                    'result': "⚡ Scrapy está corriendo en segundo plano",
                    'paginas': Pagina.objects.filter(url__icontains=dominio),
                    'progreso': cache.get("progreso", {})
                })
            else:
                return render(request, 'monitoring_app/tablero.html', {
                    'result': "⚠️ Scrapy ya está en ejecución",
                    'paginas': Pagina.objects.filter(url__icontains=dominio),
                    'progreso': cache.get("progreso", {})
                })

    elif request.method == 'GET' and request.GET.get('detener') == 'true':
        detener_scrapy()
        return render(request, 'monitoring_app/tablero.html', {
            'result': "🛑 Scrapy ha sido detenido",
            'paginas': Pagina.objects.all(),
            'progreso': cache.get("progreso", {})
        })

    else:
        form = DominioForm()

    return render(request, 'monitoring_app/tablero.html', {
        'form': form,
        'progreso': cache.get("progreso", {})
    })

def stream_progreso(request):
    """Stream de actualizaciones de progreso usando Server-Sent Events (SSE)."""
    def event_stream():
        while True:
            with scrapy_lock:
                progreso_data = cache.get("progreso", {})
                yield f"data: {json.dumps(progreso_data)}\n\n"
            time.sleep(1)  # Esperar 1 segundo antes de la siguiente actualización

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response['Cache-Control'] = 'no-cache'
    return response


@csrf_exempt
def obtener_progreso(request):
    """Devuelve el estado actual del proceso en formato JSON."""
    try:
        with scrapy_lock:
            progreso = cache.get("progreso", {})
            estado_actual = {
                "estado": progreso.get("estado", "Esperando"),
                "porcentaje": progreso.get("porcentaje", 0),
                "mensajes": progreso.get("mensajes", []),
                "ultimo_mensaje": progreso.get("mensajes", [""])[-1],
                "total_mensajes": len(progreso.get("mensajes", [])),
                "scrapy_running": scrapy_running,  # Usar la variable global scrapy_running
                "paginas_visitadas": progreso.get("paginas_visitadas", 0),
                "paginas_descubiertas": progreso.get("paginas_descubiertas", 0),
                "errores": progreso.get("errores", 0),
            }
        logger.info(f"Estado actual del progreso: {estado_actual}")
        return JsonResponse(estado_actual, safe=False)
    except Exception as e:
        logger.error(f"❌ Error en obtener_progreso: {e}")
        return JsonResponse({"estado": "Error", "mensaje": f"Error al obtener el progreso: {str(e)}"}, status=500)
    
   
def detener_scrapy():
    """
    Detiene el proceso de Scrapy de manera segura y robusta.
    Asegura que todos los recursos se liberen y que el spider se cierre correctamente.
    """
    global scrapy_thread, scrapy_running, proceso

    with scrapy_lock:
        if scrapy_thread and scrapy_thread.is_alive():
            try:
                # Detener el proceso de Scrapy
                logger.info("Deteniendo Scrapy...")

                # Verificar si el proceso de Scrapy está en ejecución
                if proceso and proceso.poll() is None:
                    # Enviar señal de terminación al proceso
                    proceso.terminate()  # Envía SIGTERM
                    logger.info("Señal SIGTERM enviada al proceso de Scrapy.")

                    # Esperar un tiempo para que el proceso termine
                    try:
                        proceso.wait(timeout=5)  # Esperar hasta 5 segundos
                    except subprocess.TimeoutExpired:
                        logger.warning("El proceso de Scrapy no respondió a SIGTERM. Forzando terminación con SIGKILL...")

                        # Forzar la terminación con SIGKILL
                        if sys.platform == "win32":
                            # Usar taskkill en Windows
                            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proceso.pid)], check=True)
                            logger.warning(f"Proceso Scrapy (PID: {proceso.pid}) terminado con taskkill.")
                        else:
                            proceso.kill()  # SIGKILL en sistemas UNIX
                            logger.warning("Proceso Scrapy terminado con SIGKILL.")
                        proceso.wait(timeout=1)  # Esperar un poco más

                # Asegurarse de que no queden procesos huérfanos
                for proc in psutil.process_iter(['pid', 'name']):
                    if proc.info['name'] == 'scrapy.exe':
                        try:
                            proc.terminate()
                            proc.wait(timeout=5)
                        except (psutil.NoSuchProcess, psutil.TimeoutExpired):
                            pass

                # Actualizar el estado y los mensajes
                progreso["estado"] = "Detenido por el usuario"
                progreso["mensajes"].append("🛑 Scrapy ha sido detenido por el usuario.")
                progreso["porcentaje"] = 0  # Reiniciar el progreso
                cache.set("progreso", progreso)

                # Ejecutar el método closed si es necesario
                if hasattr(scrapy_thread, 'spider'):
                    scrapy_thread.spider.close(reason='Detenido por el usuario')
                    logger.info("Método closed ejecutado correctamente.")

                logger.info("Proceso Scrapy detenido correctamente.")

            except Exception as e:
                logger.error(f"❌ Error al detener Scrapy: {e}")
                progreso["mensajes"].append(f"❌ Error al detener Scrapy: {e}")
                progreso["estado"] = "Error"
                cache.set("progreso", progreso)

            finally:
                # Reiniciar variables globales
                scrapy_running = False
                scrapy_thread = None
                proceso = None
        else:
            logger.info("Scrapy no está en ejecución.")
            progreso["mensajes"].append("⚠️ Scrapy no está en ejecución.")
            cache.set("progreso", progreso)

        return JsonResponse(progreso)

@csrf_exempt
def detener_scrapy_view(request):
    if request.method == 'GET':
        response = detener_scrapy()
        return response
    else:
        return JsonResponse({"error": "Método no permitido"}, status=405)