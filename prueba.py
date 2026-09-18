import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import csv
import time
import os

PRECIO_OBJETIVO = 50.00
DESCUENTO_MINIMO = 20

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
opciones.add_argument("--window-size=1920,1080")
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

        try:
            WebDriverWait(navegador, 20).until(
                EC.presence_of_element_located((By.CLASS_NAME, "js-precio_producto"))
            )
        except Exception:
            print("   ⚠️ El precio no apareció tras 20 segundos de espera")

        html = navegador.page_source
        sopa = BeautifulSoup(html, "html.parser")

        if not locals().get("ya_volque_bloque") and bloques:
            print("\n===== CONTENIDO REAL DEL PRIMER BLOQUE =====")
            print(bloques[0].prettify())
            print("===== FIN =====\n")
            ya_volque_bloque = True

        for bloque in bloques:
            precio_tag = bloque.find("p", class_="js-precio_producto")
            if not precio_tag:
                contador_sin_precio += 1
                continue
            precio_numero = a_numero(precio_tag.text)
            if precio_numero is None:
                contador_sin_precio += 1
                continue
            contador_ok += 1

            nombre_tag = bloque.find("p", class_="js-nombre_producto_listado")
            titulo = nombre_tag.get_text(strip=True) if nombre_tag else "(sin título)"

            enlace_completo = ""
            contenedor = bloque
            for _ in range(5):
                contenedor = contenedor.find_parent()
                if contenedor is None:
                    break
                enlace_tag = contenedor.find("a", class_="js-href_list_products")
                if enlace_tag and enlace_tag.get("href"):
                    enlace_completo = urljoin(url, enlace_tag["href"])
                    break

            descuento_pct = None
            precio_anterior_numero = None
            precio_anterior_tag = bloque.find("p", class_="js-precio_producto_anterior")
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
