#!/usr/bin/env python3
import os
import re
import json
import time
import requests
import io
import pandas as pd
from github import Github

# —— CONFIGURACIÓN ——
BASE_URL = "https://ec.europa.eu/growth/tools-databases/cosing"
API_URL = "https://ec.europa.eu/growth/tools-databases/cosing/api"
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


def download_annex_direct(annex):
    """
    Descarga directamente un anexo utilizando la API de COSING.
    Intenta varios endpoints posibles para encontrar el correcto.
    """
    print(f"\n--- Descargando Annex {annex} directamente ---")
    
    # Definir posibles endpoints y patrones
    endpoints = [
        f"{API_URL}/annex/{annex}/download",
        f"{API_URL}/annexes/{annex}/download",
        f"{API_URL}/annex/download/{annex}",
        f"{API_URL}/annexes/download/{annex}",
        f"{BASE_URL}/reference/annexes/download/{annex}",
        f"{BASE_URL}/reference/annexes/list/{annex}/download"
    ]
    
    # Definir cabeceras comunes para simular un navegador
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": f"{BASE_URL}/reference/annexes/list/{annex}",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0"
    }
    
    # Intentar cada endpoint
    for url in endpoints:
        try:
            print(f"Intentando URL: {url}")
            
            # Realizar una solicitud GET para intentar la descarga directa
            r = requests.get(url, headers=headers, stream=True, timeout=30)
            
            # Verificar si la respuesta es exitosa y parece ser un archivo Excel
            if r.status_code == 200:
                content_type = r.headers.get('Content-Type', '')
                content_disp = r.headers.get('Content-Disposition', '')
                
                print(f"Respuesta exitosa. Content-Type: {content_type}")
                print(f"Content-Disposition: {content_disp}")
                
                # Verificar si parece ser un Excel por el tipo de contenido o la disposición
                if ('excel' in content_type.lower() or 
                    'application/vnd.ms-excel' in content_type.lower() or
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' in content_type.lower() or
                    '.xls' in content_disp.lower()):
                    
                    # Guardar el archivo
                    filename = f"temp_annex_{annex}.xlsx"
                    if '.xls' in content_disp.lower() and '.xlsx' not in content_disp.lower():
                        filename = f"temp_annex_{annex}.xls"
                    
                    with open(filename, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    print(f"Archivo descargado como {filename}")
                    return filename
                
                # Si no es un Excel pero obtenemos respuesta, guardamos para diagnóstico
                with open(f"response_annex_{annex}.bin", 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                print(f"Respuesta guardada en response_annex_{annex}.bin para diagnóstico")
        
        except Exception as e:
            print(f"Error al intentar descargar desde {url}: {e}")
    
    print("Intentando método alternativo: solicitud POST")
    
    # Intentar con una solicitud POST
    post_url = f"{API_URL}/annex/download"
    post_data = {"annex": annex, "format": "excel"}
    
    try:
        r = requests.post(post_url, json=post_data, headers=headers, stream=True, timeout=30)
        
        if r.status_code == 200:
            content_type = r.headers.get('Content-Type', '')
            content_disp = r.headers.get('Content-Disposition', '')
            
            print(f"Respuesta POST exitosa. Content-Type: {content_type}")
            print(f"Content-Disposition: {content_disp}")
            
            if ('excel' in content_type.lower() or 
                'application/vnd.ms-excel' in content_type.lower() or
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' in content_type.lower() or
                '.xls' in content_disp.lower()):
                
                filename = f"temp_annex_{annex}.xlsx"
                if '.xls' in content_disp.lower() and '.xlsx' not in content_disp.lower():
                    filename = f"temp_annex_{annex}.xls"
                
                with open(filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                print(f"Archivo descargado como {filename}")
                return filename
    
    except Exception as e:
        print(f"Error en la solicitud POST: {e}")
    
    # Si todo falla, intentar la URL directa basada en la observación de la página
    try:
        # Intentar con la URL exacta del documento
        direct_url = f"https://ec.europa.eu/growth/tools-databases/cosing/assets/data/Annex_{annex.upper()}_OFFICIAL.xlsx"
        print(f"Intentando URL directa: {direct_url}")
        
        r = requests.get(direct_url, headers=headers, stream=True, timeout=30)
        
        if r.status_code == 200:
            filename = f"temp_annex_{annex}.xlsx"
            with open(filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"Archivo descargado como {filename}")
            return filename
    
    except Exception as e:
        print(f"Error con URL directa: {e}")
    
    return None


def extract_date_from_excel(file_path):
    """Extrae la fecha de actualización de un archivo Excel."""
    try:
        # Detectar el tipo de archivo por la extensión
        if file_path.endswith('.xlsx'):
            engine = 'openpyxl'
        else:
            engine = 'xlrd'
            
        print(f"Leyendo {file_path} con {engine}...")
        df = pd.read_excel(file_path, engine=engine, header=None)
        print(f"Archivo leído con éxito. Filas: {len(df)}")
        
        # Buscar la fecha en las primeras 15 filas
        for idx in range(min(15, len(df))):
            for col in range(min(5, len(df.columns))):
                try:
                    val = df.iloc[idx, col]
                    if isinstance(val, str):
                        print(f"Fila {idx+1}, Col {col+1}: {val}")
                        # Probar todos los patrones de fecha
                        for pattern in DATE_PATTERNS:
                            m = pattern.search(val)
                            if m:
                                date = m.group(1)
                                print(f"¡Fecha encontrada!: {date} en fila {idx+1}, columna {col+1}")
                                return date
                except Exception as e:
                    print(f"Error al leer celda ({idx}, {col}): {e}")
        
        print("No se encontró ninguna fecha en el formato esperado.")
        
        # Último intento: buscar cualquier celda que parezca una fecha
        for idx in range(min(15, len(df))):
            for col in range(min(5, len(df.columns))):
                try:
                    val = df.iloc[idx, col]
                    if isinstance(val, pd.Timestamp):
                        date_str = val.strftime('%d/%m/%Y')
                        print(f"¡Fecha encontrada (Timestamp)!: {date_str} en fila {idx+1}, columna {col+1}")
                        return date_str
                except Exception as e:
                    pass
        
        return None
    
    except Exception as e:
        print(f"Error al procesar el archivo Excel: {e}")
        return None


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


def try_inspect_webpage(annex):
    """Intenta inspeccionar la página web para encontrar pistas sobre la URL de descarga."""
    url = f"{BASE_URL}/reference/annexes/list/{annex}"
    
    try:
        print(f"Inspeccionando página web: {url}")
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        
        # Guardar HTML para inspección manual
        with open(f"page_annex_{annex}.html", "wb") as f:
            f.write(r.content)
        
        # Buscar scripts JavaScript que podrían contener URLs o endpoints
        script_pattern = re.compile(r'<script[^>]*>(.*?)</script>', re.DOTALL)
        scripts = script_pattern.findall(r.text)
        
        # Buscar posibles endpoints de API o URLs de descarga
        api_pattern = re.compile(r'(["\'](\/api\/[^"\']*|\/assets\/data\/[^"\']*)["\'])', re.DOTALL)
        download_pattern = re.compile(r'(["\'](download|excel|xls|xlsx)["\'])', re.IGNORECASE | re.DOTALL)
        
        print("Buscando posibles endpoints de API o URLs de descarga en scripts...")
        for script in scripts:
            api_matches = api_pattern.findall(script)
            download_matches = download_pattern.findall(script)
            
            if api_matches:
                print(f"Posibles endpoints de API encontrados: {api_matches}")
            
            if download_matches:
                print(f"Posibles referencias de descarga encontradas: {download_matches}")
        
        return True
    
    except Exception as e:
        print(f"Error al inspeccionar página: {e}")
        return False


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

    for annex in ANNEX_PAGES:
        print(f"\n{'='*50}")
        print(f"Procesando ANNEX {annex}")
        print(f"{'='*50}")
        
        # Primero intentamos inspeccionar la página para obtener pistas
        try_inspect_webpage(annex)
        
        # Descargar archivo directamente
        downloaded_file = download_annex_direct(annex)
        
        if downloaded_file:
            # Extraer fecha del archivo
            date = extract_date_from_excel(downloaded_file)
            
            if date:
                print(f"Fecha encontrada: {date}")
                
                new_state[annex] = date
                if state.get(annex) != date:
                    print(f"[CHANGE] Annex {annex}: {state.get(annex)} -> {date}")
                    # Preparar archivo para commit
                    filename = f"COSING_Annex_{annex}_v2.xlsx"
                    dest = os.path.join(OUTPUT_DIR, filename)
                    
                    if downloaded_file.endswith('.xls'):
                        # Conversión a .xlsx
                        success = convert_xls_to_xlsx(downloaded_file, dest)
                        if not success:
                            print(f"⚠️ No se pudo convertir a .xlsx. Usaremos el .xls original.")
                            # Copiar el archivo tal cual
                            import shutil
                            os.makedirs(os.path.dirname(dest), exist_ok=True)
                            shutil.copy2(downloaded_file, dest.replace('.xlsx', '.xls'))
                            dest = dest.replace('.xlsx', '.xls')
                    else:
                        # Copiar el archivo tal cual
                        import shutil
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        shutil.copy2(downloaded_file, dest)
                    
                    to_commit.append(dest)
                
                # Limpiar archivo temporal
                try:
                    os.remove(downloaded_file)
                except:
                    pass
            else:
                print(f"[WARN] No pude leer la fecha en Annex {annex}")
                new_state[annex] = state.get(annex)
        else:
            print(f"[WARN] No pude descargar el archivo para Annex {annex}")
            new_state[annex] = state.get(annex)

    save_state(new_state)

    if to_commit:
        commit_and_push(to_commit, "🔄 Auto-update COSING Anexos")
        print(f"✅ Committed {len(to_commit)} archivos.")
    else:
        print("✅ Sin cambios detectados.")


if __name__ == '__main__':
    main()
