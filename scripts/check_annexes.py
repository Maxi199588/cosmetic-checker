#!/usr/bin/env python3
import os
import re
import json
import time
import requests
import io
import hashlib
import subprocess
from github import Github

# —— CONFIGURACIÓN ——
API_BASE_URL = "https://api.tech.ec.europa.eu/cosing20/1.0/api/annexes"
ANNEX_PAGES = ["II", "III", "IV", "V", "VI"]
STATE_FILE = "annexes_state.json"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_NAME = "Maxi199588/cosmetic-checker"
BRANCH = "main"
OUTPUT_DIR = "RESTRICCIONES"

# Configuración de Smartsheet
SMARTSHEET_TOKEN = "3VcjriNrxtWU2psT9rY6b8ospMR7URgzJGWiC"
SMARTSHEET_SHEET_ID = "1835353259331460"
SMARTSHEET_COLUMN_ID = "1459699263950724"
SMARTSHEET_API_URL = "https://api.smartsheet.com/2.0"

# Patrón para extraer fecha "DD/MM/YYYY"
DATE_PATTERNS = [
    re.compile(r"Last update:\s*(\d{2}/\d{2}/\d{4})"),
    re.compile(r"(\d{2}/\d{2}/\d{4})"),
    re.compile(r"Update[d]?:?\s*(\d{2}/\d{2}/\d{4})"),
    re.compile(r"Date:?\s*(\d{2}/\d{2}/\d{4})")
]


def load_state():
    """Carga el estado anterior del archivo STATE_FILE."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}


def save_state(state):
    """Guarda el estado actual en el archivo STATE_FILE."""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def download_annex(annex):
    """Descarga un anexo usando la URL de API directa."""
    url = f"{API_BASE_URL}/{annex}/export-xls"
    print(f"\n--- Descargando Annex {annex} ---")
    print(f"URL: {url}")
    
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "*/*"
        }
        
        response = requests.get(url, headers=headers, stream=True, timeout=60)
        response.raise_for_status()
        
        # Extraer información importante de las cabeceras
        content_type = response.headers.get('Content-Type', '')
        content_disp = response.headers.get('Content-Disposition', '')
        last_modified = response.headers.get('Last-Modified', '')
        
        print(f"Respuesta exitosa. Status: {response.status_code}")
        print(f"Content-Type: {content_type}")
        print(f"Content-Disposition: {content_disp}")
        print(f"Last-Modified: {last_modified}")
        
        # Verificar que es un archivo Excel
        if 'application/vnd.ms-excel' in content_type or 'excel' in content_type.lower():
            # Guardar el archivo
            temp_file = f"temp_annex_{annex}.xls"
            
            with open(temp_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            print(f"Archivo descargado como {temp_file}")
            
            # Extraer fecha de last-modified si está disponible
            if last_modified:
                try:
                    from email.utils import parsedate_to_datetime
                    dt = parsedate_to_datetime(last_modified)
                    last_mod_date = dt.strftime('%d/%m/%Y')
                    print(f"Fecha de última modificación: {last_mod_date} (del encabezado HTTP)")
                    return temp_file, last_mod_date
                except Exception as e:
                    print(f"Error al parsear fecha Last-Modified: {e}")
            
            # Si no pudimos extraer fecha del encabezado, usamos un hash
            file_hash = calculate_file_hash(temp_file)
            print(f"No se pudo determinar fecha. Usando hash como identificador: {file_hash[:8]}")
            return temp_file, f"hash-{file_hash[:8]}"
        
        else:
            print(f"¡El contenido descargado no es un archivo Excel! Tipo: {content_type}")
            # Guardar el contenido para diagnóstico
            with open(f"invalid_content_{annex}.bin", 'wb') as f:
                f.write(response.content)
            print(f"Contenido guardado para diagnóstico en invalid_content_{annex}.bin")
            return None, None
    
    except Exception as e:
        print(f"Error al descargar anexo {annex}: {e}")
        return None, None


def calculate_file_hash(file_path):
    """Calcula un hash MD5 del contenido del archivo."""
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()


def create_empty_xlsx(output_path, title, description):
    """Crea un archivo XLSX vacío con información básica."""
    try:
        # Verificar si openpyxl está instalado
        try:
            from openpyxl import Workbook
        except ImportError:
            import subprocess
            subprocess.check_call(["pip", "install", "openpyxl"])
            from openpyxl import Workbook
        
        # Crear un nuevo libro
        wb = Workbook()
        ws = wb.active
        ws.title = "Información"
        
        # Añadir encabezados
        ws['A1'] = title
        ws['A2'] = description
        ws['A3'] = f"Generado el {time.strftime('%Y-%m-%d %H:%M:%S')}"
        
        # Guardar el archivo
        wb.save(output_path)
        print(f"Archivo XLSX creado correctamente: {output_path}")
        return True
    except Exception as e:
        print(f"Error al crear archivo XLSX: {e}")
        return False


def prepare_file_for_commit(downloaded_file, annex, output_dir):
    """Prepara el archivo para commit."""
    try:
        # Crear directorios si no existen
        os.makedirs(output_dir, exist_ok=True)
        
        # Crear archivo XLSX
        xlsx_path = os.path.join(output_dir, f"COSING_Annex_{annex}_v2.xlsx")
        success = create_empty_xlsx(
            xlsx_path,
            f"Annex {annex} Data",
            "Este archivo XLSX contiene los datos del Anexo descargado de la base de datos CosIng"
        )
        
        # Siempre guardar también el archivo XLS original
        xls_path = os.path.join(output_dir, f"COSING_Annex_{annex}_v2.xls")
        import shutil
        shutil.copy2(downloaded_file, xls_path)
        print(f"Archivo XLS original copiado a {xls_path}")
        
        return [xlsx_path, xls_path] if success else [xls_path]
    
    except Exception as e:
        print(f"Error al preparar archivos para commit: {e}")
        return []


def commit_files_with_github_api(files, message):
    """Realiza un commit usando la API de GitHub directamente."""
    if not GITHUB_TOKEN:
        print("⚠️ No se ha proporcionado GITHUB_TOKEN. No se realizará el commit.")
        return False
    
    try:
        print(f"Realizando commit con GitHub API para {len(files)} archivos...")
        
        gh = Github(GITHUB_TOKEN)
        repo = gh.get_repo(REPO_NAME)
        
        # Obtener la referencia actual
        ref = repo.get_git_ref(f"heads/{BRANCH}")
        latest_commit = repo.get_commit(ref.object.sha)
        base_tree = latest_commit.commit.tree
        
        # Crear blobs para cada archivo
        blobs = []
        for file_path in files:
            if not os.path.exists(file_path):
                print(f"⚠️ Archivo no encontrado: {file_path}")
                continue
            
            with open(file_path, 'rb') as f:
                content = f.read()
            
            blob = repo.create_git_blob(content.hex(), 'base64')
            print(f"Blob creado para {file_path}")
            
            # Añadir el elemento al árbol
            blobs.append({
                'path': file_path,
                'mode': '100644',  # modo para archivo regular
                'type': 'blob',
                'sha': blob.sha
            })
        
        # Crear un nuevo árbol con los archivos nuevos/modificados
        new_tree = repo.create_git_tree(blobs, base_tree)
        
        # Crear un nuevo commit
        new_commit = repo.create_git_commit(message, new_tree, [latest_commit])
        
        # Actualizar la referencia
        ref.edit(new_commit.sha)
        
        print("✅ Commit realizado correctamente con GitHub API")
        return True
    
    except Exception as e:
        print(f"❌ Error al hacer commit con GitHub API: {e}")
        
        # Intentar un método alternativo
        try:
            print("Intentando método alternativo de commit...")
            
            for file_path in files:
                if not os.path.exists(file_path):
                    print(f"⚠️ Archivo no encontrado: {file_path}")
                    continue
                
                with open(file_path, 'rb') as f:
                    content = f.read()
                
                try:
                    # Intentar obtener el archivo existente
                    contents = repo.get_contents(file_path, ref=BRANCH)
                    repo.update_file(
                        path=file_path,
                        message=message,
                        content=content,
                        sha=contents.sha,
                        branch=BRANCH
                    )
                    print(f"Archivo actualizado: {file_path}")
                except:
                    # Si no existe, crearlo
                    repo.create_file(
                        path=file_path,
                        message=message,
                        content=content,
                        branch=BRANCH
                    )
                    print(f"Archivo creado: {file_path}")
            
            print("✅ Commit realizado con método alternativo")
            return True
        
        except Exception as e2:
            print(f"❌ Error en método alternativo: {e2}")
            return False


def add_row_to_smartsheet(updated_annexes, unchanged_annexes):
    """
    Añade una fila a Smartsheet con información sobre las actualizaciones.
    
    Args:
        updated_annexes: Lista de anexos que se actualizaron
        unchanged_annexes: Lista de anexos que no se actualizaron
    
    Returns:
        bool: True si se añadió la fila correctamente, False en caso contrario
    """
    if not SMARTSHEET_TOKEN or not SMARTSHEET_SHEET_ID or not SMARTSHEET_COLUMN_ID:
        print("⚠️ No se ha proporcionado la configuración de Smartsheet.")
        return False
    
    try:
        print("Preparando actualización en Smartsheet...")
        
        # Preparar el contenido de la celda
        cell_value = f"Reporte de Actualización COSING - {time.strftime('%d/%m/%Y %H:%M:%S')}\n\n"
        
        if updated_annexes:
            cell_value += "✅ Anexos Actualizados:\n"
            for annex in updated_annexes:
                cell_value += f"- Annex {annex}\n"
        else:
            cell_value += "ℹ️ No se encontraron actualizaciones en ningún anexo.\n"
        
        if unchanged_annexes:
            cell_value += "\n🔄 Anexos sin cambios:\n"
            for annex in unchanged_annexes:
                cell_value += f"- Annex {annex}\n"
        
        # Preparar la solicitud a la API de Smartsheet
        headers = {
            "Authorization": f"Bearer {SMARTSHEET_TOKEN}",
            "Content-Type": "application/json"
        }
        
        # 1. Primero obtenemos información sobre la hoja
        sheet_info_url = f"{SMARTSHEET_API_URL}/sheets/{SMARTSHEET_SHEET_ID}"
        sheet_response = requests.get(sheet_info_url, headers=headers)
        
        if sheet_response.status_code != 200:
            print(f"❌ Error al obtener información de la hoja: {sheet_response.status_code} - {sheet_response.text}")
            return False
        
        # 2. Ahora añadimos una nueva fila
        add_row_url = f"{SMARTSHEET_API_URL}/sheets/{SMARTSHEET_SHEET_ID}/rows"
        
        row_data = {
            "cells": [
                {
                    "columnId": SMARTSHEET_COLUMN_ID,
                    "value": cell_value
                }
            ],
            "toTop": True  # Añadir al principio de la hoja
        }
        
        add_row_response = requests.post(
            add_row_url,
            headers=headers,
            json=row_data
        )
        
        if add_row_response.status_code in (200, 201):
            print(f"✅ Fila añadida correctamente a Smartsheet")
            return True
        else:
            print(f"❌ Error al añadir fila a Smartsheet: {add_row_response.status_code} - {add_row_response.text}")
            return False
    
    except Exception as e:
        print(f"❌ Error general al actualizar Smartsheet: {e}")
        return False


def main():
    """Función principal del script."""
    state = load_state()
    new_state = {}
    all_files_to_commit = []
    
    # Listas para seguimiento de actualizaciones
    updated_annexes = []
    unchanged_annexes = []

    for annex in ANNEX_PAGES:
        print(f"\n{'='*50}")
        print(f"Procesando ANNEX {annex}")
        print(f"{'='*50}")
        
        # Descargar archivo con la API directa
        downloaded_file, date = download_annex(annex)
        
        if downloaded_file and date:
            print(f"Versión identificada: {date}")
            
            new_state[annex] = date
            if state.get(annex) != date:
                print(f"[CHANGE] Annex {annex}: {state.get(annex)} -> {date}")
                updated_annexes.append(annex)
                
                # Preparar archivo para commit
                files = prepare_file_for_commit(downloaded_file, annex, OUTPUT_DIR)
                if files:
                    all_files_to_commit.extend(files)
            else:
                unchanged_annexes.append(annex)
            
            # Limpiar archivo temporal
            try:
                os.remove(downloaded_file)
            except:
                pass
        else:
            print(f"[WARN] No pude descargar el archivo para Annex {annex}")
            unchanged_annexes.append(annex)
            new_state[annex] = state.get(annex)

    save_state(new_state)

    # Realizar commit si hay archivos para subir
    commit_success = False
    if all_files_to_commit:
        commit_success = commit_files_with_github_api(all_files_to_commit, "🔄 Auto-update COSING Anexos")
        if commit_success:
            print(f"✅ Committed {len(all_files_to_commit)} archivos exitosamente.")
        else:
            print(f"❌ Error al hacer commit y push.")
    else:
        print("✅ Sin cambios detectados.")
    
    # Añadir fila a Smartsheet si hay actualizaciones o hubo errores
    if updated_annexes or not commit_success:
        add_row_to_smartsheet(updated_annexes, unchanged_annexes)


if __name__ == '__main__':
    main()
