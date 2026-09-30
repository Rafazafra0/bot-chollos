from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import time
import csv
import requests
import os

DESCUENTO_MINIMO = 50

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def enviar_telegram(mensaje):
    url_api = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    respuesta = requests.post(url_api, data={"chat_id": TELEGRAM_CHAT_ID, "text": mensaje})
    if not respuesta.json().get("ok"):
        print("⚠️ Telegram rechazó el mensaje:", respuesta.text)

opciones = Options()
opciones.add_argument("--headless=new")
opciones.add_argument("--no-sandbox")
opciones.add_argument("--disable-dev-shm-usage")
opciones.add_argument("--window-size=1920,1080")
navegador = webdriver.Chrome(options=opciones)

url = "https://www.mediamarkt.es/es/category/outlet-1112.html"
navegador.get(url)
time.sleep(5)

try:
    boton_cookies = navegador.find_element(By.XPATH, "//button[contains(text(), 'Aceptar') or contains(text(), 'aceptar')]")
    boton_cookies.click()
    print("Cookies aceptadas")
    time.sleep(1)
except Exception as e:
    print("No até el aviso de cookies:", str(e)[:150])

print("¿Aparece €?:", "€" in navegador.page_source, "| ¿Aparece $?:", "$" in navegador.page_source)

ultimo_conteo = 0
for intento in range(40):
    try:
        boton_mas = navegador.find_element(By.XPATH, "//button[contains(text(), 'Mostrar') and contains(text(), 'más')]")
        navegador.execute_script("arguments[0].scrollIntoView(true);", boton_mas)
        time.sleep(0.5)
        navegador.execute_script("arguments[0].click();", boton_mas)
        time.sleep(4)
    except Exception as e:
        print(f"Paró en el intento {intento + 1}. Motivo: {str(e)[:200]}")
        break

    conteo_actual = len(navegador.find_elements(By.CSS_SELECTOR, "a[data-test='mms-router-link-product-list-item-link']"))
    contador_texto = re.search(r"\d+\s*de\s*\d+", navegador.page_source)
    print(f"   Cargados hasta ahora: {conteo_actual} | Contador de la web: {contador_texto.group() if contador_texto else 'no encontrado'}")

    conteo_actual = len(navegador.find_elements(By.CSS_SELECTOR, "a[data-test='mms-router-link-product-list-item-link']"))
    if conteo_actual == ultimo_conteo:
        break
    ultimo_conteo = conteo_actual

sopa = BeautifulSoup(navegador.page_source, "html.parser")
navegador.quit()

tarjetas = sopa.find_all("a", attrs={"data-test": "mms-router-link-product-list-item-link"})
print(f"Fichas encontradas: {len(tarjetas)}")

chollos_encontrados = []
enlaces_vistos = set()

for tarjeta in tarjetas:
    enlace_completo = urljoin(url, tarjeta.get("href", ""))
    if enlace_completo in enlaces_vistos:
        continue

    div_titulo = tarjeta.find("div", title=True)
    titulo = div_titulo.get("title") if div_titulo else "(sin título)"

    contenedor_precio = None
    ancestro = tarjeta
    for _ in range(6):
        ancestro = ancestro.find_parent()
        if ancestro is None:
            break
        candidato = ancestro.find(attrs={"data-test": re.compile("price", re.IGNORECASE)})
        if candidato:
            contenedor_precio = candidato
            break

    if not contenedor_precio:
        continue

    texto_precio = contenedor_precio.get_text(" ", strip=True)
    descuento_match = re.search(r"-(\d+)%", texto_precio)
    descuento_pct = int(descuento_match.group(1)) if descuento_match else None

    precios_limpios = re.findall(r"(\d+,\d{2})€", texto_precio)
    if len(precios_limpios) >= 2:
        precio_numero = float(precios_limpios[1].replace(",", "."))
    elif len(precios_limpios) == 1:
        precio_numero = float(precios_limpios[0].replace(",", "."))
    else:
        continue

    if descuento_pct is not None and descuento_pct >= DESCUENTO_MINIMO:
        enlaces_vistos.add(enlace_completo)
        print("🚨 ¡CHOLLO!", titulo, precio_numero, f"({descuento_pct}% dto)")
        chollos_encontrados.append((titulo, precio_numero, descuento_pct, enlace_completo))

with open('chollos_mediamarkt.csv', mode='w', newline='', encoding='utf-8-sig') as archivo:
    escritor = csv.writer(archivo, delimiter=';')
    escritor.writerow(['Título', 'Precio (€)', 'Descuento %', 'Enlace'])
    for titulo, precio, descuento, enlace in chollos_encontrados:
        escritor.writerow([titulo, precio, descuento, enlace])

if chollos_encontrados:
    lineas = [f"🚨 {t} — {p}€ ({d}% dto)\n{e}" for t, p, d, e in chollos_encontrados]
    LIMITE_CARACTERES = 3500
    bloque_actual = f"MediaMarkt: {len(chollos_encontrados)} chollo(s):\n\n"
    mensajes_enviados = 0

    for linea in lineas:
        if len(bloque_actual) + len(linea) > LIMITE_CARACTERES:
            enviar_telegram(bloque_actual)
            mensajes_enviados += 1
            bloque_actual = ""
            time.sleep(1.5)
        bloque_actual += linea + "\n\n"

    if bloque_actual.strip():
        enviar_telegram(bloque_actual)
        mensajes_enviados += 1

    print(f"\n📲 Enviados {mensajes_enviados} mensaje(s) con {len(chollos_encontrados)} chollo(s) en total.")
else:
    print("\nSin chollos esta vez, no se envía mensaje.")

print("✅ Terminado. Revisa chollos_mediamarkt.csv.")