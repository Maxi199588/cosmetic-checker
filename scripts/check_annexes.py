#!/usr/bin/env python3
import os
import re
import json
import requests
import io
import pandas as pd
from bs4 import BeautifulSoup
from github import Github

# —— CONFIGURACIÓN ——
BASE_URL = "https://ec.europa.eu/growth/tools-databases/cosing"
STATIC_BASE_URL = f"{BASE_URL}/assets/data"
ANNEX_PAGES = ["II", "III", "IV", "V", "VI"]
STATE_FILE = "annexes_state.json"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_NAME = "Maxi199588/cosmetic-checker"
BRANCH = "main"
OUTPUT_DIR = "RESTRICCIONES"

# Patrón para extraer fecha "DD/MM/YYYY"
DATE_PATTERNS = [
    re.compile(r"Last update:\s*(\d{2}/\d{2}/\d{4})"),
    re.compile(r"(\d{2}/\d{2}/\d{4})"),
    re.compile(r"Update[d]?:?\s*(\d{2}/\d{2}/\d{4})"),
    re.compile(r"Date:?\s*(\d{2}/\d{2}/\d{4})")
]


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def inspect_html_content(content, annex):
    """Analiza el contenido HTML para buscar enlaces a archivos Excel."""
    print("El contenido descargado es HTML. Analizando...")
    
    # Guardar el HTML para diagnóstico
    with open(f"debug_annex_{annex}.html", "wb") as f:
        f.write(content)
        
    soup = BeautifulSoup(content, 'html.parser')
    
    # Buscar enlaces que podrían apuntar a archivos Excel
    excel_links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '.xls' in href.lower() or '.xlsx' in href.lower():
            excel_links.append(href)
            print(f"Encontrado posible enlace Excel: {href}")
    
    # Buscar posibles redirecciones
    meta_refresh = soup.find('meta', attrs={'http-equiv': 'refresh'})
    if meta_refresh and 'content' in meta_refresh.attrs:
        content = meta_refresh['content']
        url_match = re.search(r'URL=([^"]+)', content, re.IGNORECASE)
        if url_match:
            redirect_url = url_match.group(1)
            print(f"Encontrada redirección a: {redirect_url}")
            return redirect_url
    
    # Si encontramos enlaces a Excel, devolver el primero
    if excel_links:
        # Convertir en URL absoluta si es necesario
        if excel_links[0].startswith('/'):
            return f"{BASE_URL}{excel_links[0]}"
        return excel_links[0]
    
    # Buscar mensajes de error o información útil
    for tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'p']):
        if tag.text and len(tag.text.strip()) > 0:
            print(f"Texto en la página: {tag.text.strip()}")
    
    return None


def find_correct_excel_url(annex):
    """Intenta encontrar la URL correcta para el archivo Excel del anexo."""
    print(f"\n--- Buscando URL correcta para Annex {annex} ---")
    
    # Primero, intentar la página principal de COSING
    main_url = f"{BASE_URL}/ref_data/annexes/Annex_{annex}.cfm"
    try:
        print(f"Consultando página principal: {main_url}")
        r = requests.get(main_url, timeout=30)
        r.raise_for_status()
        
        # Analizar HTML para encontrar enlaces a archivos Excel
        soup = BeautifulSoup(r.content, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = a['href']
            if ('.xls' in href.lower() or '.xlsx' in href.lower()) and 'annex' in href.lower():
                print(f"Encontrado enlace Excel en página principal: {href}")
                if href.startswith('/') or href.startswith('./'):
                    full_url = f"{BASE_URL}{href.replace('./', '/')}"
                elif not href.startswith('http'):
                    full_url = f"{BASE_URL}/{href}"
                else:
                    full_url = href
                print(f"URL completa: {full_url}")
                return full_url
    except Exception as e:
        print(f"Error al consultar página principal: {e}")
    
    # Si no encontramos en la página principal, intentar patrones alternativos
    alternative_patterns = [
        f"{STATIC_BASE_URL}/Annex_{annex}.xlsx",
        f"{STATIC_BASE_URL}/Annex_{annex}.xls",
        f"{STATIC_BASE_URL}/COSING_Annex_{annex}.xlsx",
        f"{STATIC_BASE_URL}/COSING_Annex_{annex}.xls",
        f"{BASE_URL}/assets/data/Annex_{annex}.xlsx",
        f"{BASE_URL}/assets/data/Annex_{annex}.xls",
        f"{BASE_URL}/assets/data/COSING_Annex_{annex}.xlsx",
        f"{BASE_URL}/assets/data/COSING_Annex_{annex}.xls"
    ]
    
    for url in alternative_patterns:
        try:
            print(f"Probando URL alternativa: {url}")
            r = requests.head(url, timeout=10)
            if r.status_code == 200:
                content_type = r.headers.get('content-type', '')
                if 'excel' in content_type.lower() or 'application/vnd.ms-excel' in content_type.lower():
                    print(f"¡Encontrado archivo Excel válido!: {url}")
                    return url
        except Exception as e:
            print(f"Error al probar {url}: {e}")
    
    # Última opción: buscar en la página de descarga de COSING
    try:
        download_url = f"{BASE_URL}/index.cfm?fuseaction=search.annexes"
        print(f"Consultando página de anexos: {download_url}")
        r = requests.get(download_url, timeout=30)
        r.raise_for_status()
        
        soup = BeautifulSoup(r.content, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = a['href']
            annex_text = f"annex {annex}"
            if ('.xls' in href.lower() or '.xlsx' in href.lower()) and annex_text.lower() in a.text.lower():
                print(f"Encontrado enlace para Annex {annex}: {href}")
                if href.startswith('/') or href.startswith('./'):
                    full_url = f"{BASE_URL}{href.replace('./', '/')}"
                elif not href.startswith('http'):
                    full_url = f"{BASE_URL}/{href}"
                else:
                    full_url = href
                print(f"URL completa: {full_url}")
                return full_url
    except Exception as e:
        print(f"Error al consultar página de anexos: {e}")
    
    return None


def fetch_and_parse_date(url, annex):
    """
    Descarga el archivo y busca la fecha de actualización.
    """
    print(f"Descargando {url}...")
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        
        # Verificar el tipo de contenido
        content_type = r.headers.get('content-type', '')
        print(f"Tipo de contenido: {content_type}")
        
        if 'text/html' in content_type:
            # Si recibimos HTML, intentar encontrar la URL real del Excel
            new_url = inspect_html_content(r.content, annex)
            if new_url:
                print(f"Intentando con nueva URL: {new_url}")
                return fetch_and_parse_date(new_url, annex)
            else:
                # Si no encontramos ninguna URL en el HTML, intentar buscar en la web
                correct_url = find_correct_excel_url(annex)
                if correct_url:
                    print(f"Encontrada URL correcta: {correct_url}")
                    return fetch_and_parse_date(correct_url, annex)
                return None
        
        # Guardar temporalmente el archivo para inspeccionarlo
        temp_file = f"temp_annex_{annex}.xls"
        with open(temp_file, 'wb') as f:
            f.write(r.content)
        
        print(f"Archivo descargado, tamaño: {len(r.content)} bytes")
        
        # Verificar que sea un archivo Excel válido
        with open(temp_file, 'rb') as f:
            header = f.read(8)
            if header[:2] != b'\xD0\xCF' and header[:5] != b'PK\x03\x04\x14':  # Firmas de XLS y XLSX
                print("¡El archivo no tiene la firma de un Excel válido!")
                # Guardar para inspección
                with open(f"invalid_excel_{annex}.bin", 'wb') as debug_f:
                    with open(temp_file, 'rb') as src_f:
                        debug_f.write(src_f.read())
                os.remove(temp_file)
                return None
        
        # Intentar leer con el motor adecuado
        if url.endswith('.xlsx'):
            engine = 'openpyxl'
        else:
            engine = 'xlrd'
            
        try:
            print(f"Intentando leer con {engine}...")
            df = pd.read_excel(temp_file, engine=engine, header=None)
            print(f"¡Éxito! Leído con {engine}. Filas: {len(df)}")
        except Exception as e:
            print(f"Error con {engine}: {e}")
            # Intentar con el otro motor
            try:
                alternate_engine = 'openpyxl' if engine == 'xlrd' else 'xlrd'
                print(f"Intentando con {alternate_engine}...")
                df = pd.read_excel(temp_file, engine=alternate_engine, header=None)
                print(f"¡Éxito! Leído con {alternate_engine}. Filas: {len(df)}")
            except Exception as e2:
                print(f"Error con {alternate_engine}: {e2}")
                os.remove(temp_file)
                return None
        
        # Buscar la fecha en las primeras 15 filas
        for idx in range(min(15, len(df))):
            for col in range(min(5, len(df.columns))):
                val = df.iloc[idx, col]
                if isinstance(val, str):
                    print(f"Fila {idx+1}, Col {col+1}: {val}")
                    # Probar todos los patrones de fecha
                    for pattern in DATE_PATTERNS:
                        m = pattern.search(val)
                        if m:
                            date = m.group(1)
                            print(f"¡Fecha encontrada!: {date} en fila {idx+1}, columna {col+1}")
                            os.remove(temp_file)
                            return (date, url)  # Devolver también la URL correcta
        
        os.remove(temp_file)
        print("No se encontró ninguna fecha en el formato esperado.")
        return None
        
    except Exception as e:
        print(f"Error general al procesar {url}: {e}")
        if os.path.exists(f"temp_annex_{annex}.xls"):
            os.remove(f"temp_annex_{annex}.xls")
        return None


def download_file(url, dest_path):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, 'wb') as f:
        f.write(r.content)
    return dest_path


def convert_xls_to_xlsx(xls_path, xlsx_path):
    """Convierte archivo .xls a .xlsx con manejo de errores específico."""
    try:
        # Leer con xlrd explícitamente para .xls
        df = pd.read_excel(xls_path, engine='xlrd')
        df.to_excel(xlsx_path, index=False)
        print(f"Convertido {xls_path} a {xlsx_path}")
        return True
    except Exception as e:
        print(f"Error al convertir {xls_path} a {xlsx_path}: {e}")
        return False


def commit_and_push(files, message):
    if not GITHUB_TOKEN:
        print("⚠️ No se ha proporcionado GITHUB_TOKEN. No se realizará el commit.")
        return
        
    gh = Github(GITHUB_TOKEN)
    repo = gh.get_repo(REPO_NAME)
    for file_path in files:
        content = open(file_path, 'rb').read()
        try:
            existing = repo.get_contents(file_path, ref=BRANCH)
            repo.update_file(file_path, message, content, existing.sha, branch=BRANCH)
        except Exception:
            repo.create_file(file_path, message, content, branch=BRANCH)


def main():
    state = load_state()
    new_state = {}
    to_commit = []

    # Verificar dependencias necesarias
    try:
        import xlrd
        print(f"xlrd version: {xlrd.__version__}")
    except ImportError:
        print("⚠️ xlrd no está instalado. Instalando...")
        import subprocess
        subprocess.check_call(["pip", "install", "xlrd"])
    
    try:
        import openpyxl
        print(f"openpyxl version: {openpyxl.__version__}")
    except ImportError:
        print("⚠️ openpyxl no está instalado. Instalando...")
        import subprocess
        subprocess.check_call(["pip", "install", "openpyxl"])
    
    try:
        import bs4
        print(f"BeautifulSoup version: {bs4.__version__}")
    except ImportError:
        print("⚠️ BeautifulSoup no está instalado. Instalando...")
        import subprocess
        subprocess.check_call(["pip", "install", "beautifulsoup4"])

    for annex in ANNEX_PAGES:
        print(f"\n{'='*50}")
        print(f"Procesando ANNEX {annex}")
        print(f"{'='*50}")
        
        # Buscar la URL correcta directamente
        correct_url = find_correct_excel_url(annex)
        
        if correct_url:
            result = fetch_and_parse_date(correct_url, annex)
            if result:
                date, final_url = result
                print(f"Fecha encontrada: {date} en {final_url}")
                
                new_state[annex] = date
                if state.get(annex) != date:
                    print(f"[CHANGE] Annex {annex}: {state.get(annex)} -> {date}")
                    # descarga y añade al commit
                    filename = f"COSING_Annex_{annex}_v2.xlsx"
                    dest = os.path.join(OUTPUT_DIR, filename)
                    
                    if final_url.endswith('.xls'):
                        tmp = download_file(final_url, os.path.join(OUTPUT_DIR, f"COSING_Annex_{annex}_v2.xls"))
                        # Conversión 
                        success = convert_xls_to_xlsx(tmp, dest)
                        if not success:
                            print(f"⚠️ No se pudo convertir {tmp} a .xlsx. Usaremos el .xls original.")
                            dest = tmp
                        else:
                            os.remove(tmp)
                    else:
                        download_file(final_url, dest)
                        
                    to_commit.append(dest)
            else:
                print(f"[WARN] No pude leer la fecha en Annex {annex}")
                new_state[annex] = state.get(annex)
        else:
            print(f"[WARN] No pude encontrar la URL correcta para Annex {annex}")
            new_state[annex] = state.get(annex)

    save_state(new_state)

    if to_commit:
        commit_and_push(to_commit, "🔄 Auto-update COSING Anexos")
        print(f"✅ Committed {len(to_commit)} archivos.")
    else:
        print("✅ Sin cambios detectados.")


if __name__ == '__main__':
    main()
