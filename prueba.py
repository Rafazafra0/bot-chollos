import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import csv
import time
import os

PRECIO_OBJETIVO = 20.00
DESCUENTO_MINIMO = 70

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

cabeceras = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
}

def enviar_telegram(mensaje):
    url_api = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    respuesta = requests.post(url_api, data={"chat_id": TELEGRAM_CHAT_ID, "text": mensaje})
    if not respuesta.json().get("ok"):
        print("⚠️ Telegram rechazó el mensaje:", respuesta.text)

def a_numero(texto_precio):
    limpio = texto_precio.replace("€", "").strip().replace(",", ".")
    try:
        return float(limpio)
    except ValueError:
        return None

def buscar_contenedor_texto(tarjeta):
    ancestro = tarjeta
    for _ in range(5):
        ancestro = ancestro.find_parent()
        if ancestro is None:
            return None
        candidato = ancestro.find(class_="listado-txt")
        if candidato:
            return candidato
    return None

print("🔎 Buscando marcas en oferta en la portada...")
respuesta_portada = requests.get("https://www.tradeinn.com/outletinn/es", headers=cabeceras)
respuesta_portada.encoding = "utf-8"
sopa_portada = BeautifulSoup(respuesta_portada.text, "html.parser")

patron_marca = re.compile(r"/[\w\-]+/\d+-\d+/m$")
URLS_A_REVISAR = set()
for enlace in sopa_portada.find_all("a", href=True):
    if patron_marca.search(enlace["href"]):
        URLS_A_REVISAR.add(urljoin(respuesta_portada.url, enlace["href"]))

print(f"✅ {len(URLS_A_REVISAR)} marcas encontradas. Empezando a revisarlas...\n")

chollos_encontrados = []
contador_ok = 0
contador_sin_precio = 0

opciones = Options()
opciones.add_argument("--headless=new")
opciones.add_argument("--no-sandbox")
opciones.add_argument("--disable-dev-shm-usage")
navegador = webdriver.Chrome(options=opciones)

with open('mis_chollos.csv', mode='w', newline='', encoding='utf-8-sig') as archivo:
    escritor = csv.writer(archivo, delimiter=';')
    escritor.writerow(['Título', 'Precio (€)', 'Precio anterior (€)', 'Descuento %', 'Enlace', 'Categoría'])

    for url in URLS_A_REVISAR:
        navegador.get(url)
        time.sleep(3)

        try:
            boton_cookies = navegador.find_element(By.XPATH, "//button[contains(text(), 'Aceptar todas las cookies')]")
            boton_cookies.click()
        except Exception:
            pass

        time.sleep(5)

        html = navegador.page_source
        sopa = BeautifulSoup(html, "html.parser")
        tarjetas = sopa.find_all("a", class_="js-href_list_products")
        print(f"Revisando: {url}")
        print(f"   -> {len(tarjetas)} fichas encontradas")

        for tarjeta in tarjetas:
            titulo = tarjeta.get("title", "").strip()
            enlace_completo = urljoin(url, tarjeta["href"])

            contenedor_texto = buscar_contenedor_texto(tarjeta)
            if not contenedor_texto:
                contador_sin_precio += 1
                continue

            precio_tag = contenedor_texto.find("p", class_="js-precio_producto")
            if not precio_tag:
                contador_sin_precio += 1
                continue
            precio_numero = a_numero(precio_tag.text)
            if precio_numero is None:
                contador_sin_precio += 1
                continue
            contador_ok += 1

            descuento_pct = None
            precio_anterior_numero = None
            precio_anterior_tag = contenedor_texto.find("p", class_="js-precio_producto_anterior")
            if precio_anterior_tag:
                precio_anterior_numero = a_numero(precio_anterior_tag.text)
                if precio_anterior_numero and precio_anterior_numero > 0:
                    descuento_pct = round((precio_anterior_numero - precio_numero) / precio_anterior_numero * 100)

            es_chollo = precio_numero < PRECIO_OBJETIVO or (descuento_pct is not None and descuento_pct >= DESCUENTO_MINIMO)

            if es_chollo:
                print("🚨 ¡CHOLLO!", titulo, precio_numero)
                escritor.writerow([titulo, precio_numero, precio_anterior_numero if descuento_pct else "", descuento_pct or "", enlace_completo, url])
                chollos_encontrados.append((titulo, precio_numero, descuento_pct, enlace_completo))

print(f"\nResumen: {contador_ok} precios leídos correctamente, {contador_sin_precio} descartados.")
navegador.quit()

if chollos_encontrados:
    lineas = []
    for titulo, precio, descuento, enlace in chollos_encontrados:
        extra = f" ({descuento}% dto)" if descuento else ""
        lineas.append(f"🚨 {titulo} — {precio}€{extra}\n{enlace}")

    LIMITE_CARACTERES = 3500
    bloque_actual = f"He encontrado {len(chollos_encontrados)} chollo(s):\n\n"
    mensajes_enviados = 0

    for linea in lineas:
        if len(bloque_actual) + len(linea) > LIMITE_CARACTERES:
            enviar_telegram(bloque_actual)
            mensajes_enviados += 1
            bloque_actual = ""
        bloque_actual += linea + "\n\n"

    if bloque_actual.strip():
        enviar_telegram(bloque_actual)
        mensajes_enviados += 1

    print(f"\n📲 Enviados {mensajes_enviados} mensaje(s) de Telegram con {len(chollos_encontrados)} chollo(s) en total.")
else:
    print("\nSin chollos esta vez, no se envía mensaje.")

print("✅ Terminado. Revisa mis_chollos.csv.")