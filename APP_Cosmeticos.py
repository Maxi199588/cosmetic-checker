import streamlit as st
import pandas as pd
import re
import os
import requests
import time
import json
from io import BytesIO
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak
)
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

# -----------------------------------------------------------
# FUNCIÓN PARA GENERAR REPORTE PDF
# -----------------------------------------------------------
def generar_reporte_pdf(resultados):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=1*inch, rightMargin=1*inch,
        topMargin=1*inch, bottomMargin=1*inch
    )
    styles = getSampleStyleSheet()
    normal = styles['Normal']
    h2     = styles['Heading2']
    h3     = styles['Heading3']
    bold   = ParagraphStyle(name='Bold', parent=normal, fontName='Helvetica-Bold')

    elementos = []
    # Título
    elementos.append(Paragraph(
        "Reporte de Búsqueda de CAS en Anexos de Restricciones",
        styles['Title']
    ))
    elementos.append(Spacer(1, 12))

    primera = True
    for cas_num, res in resultados.items():
        # salto de página entre cada CAS, excepto antes del primero
        if not primera:
            elementos.append(PageBreak())
        primera = False

        # Encabezado CAS
        elementos.append(Paragraph(f"CAS: {cas_num}", h2))
        elementos.append(Spacer(1, 6))

        if not res["encontrado"]:
            elementos.append(Paragraph("No encontrado en ningún anexo.", normal))
            elementos.append(Spacer(1, 12))
            continue

        # Para cada anexo donde se encontró
        for anexo in res["anexos"]:
            elementos.append(Paragraph(anexo['nombre'], h3))
            elementos.append(Spacer(1, 4))

            df = anexo['data'].reset_index(drop=True)
            # Por cada fila del DataFrame
            for _, row in df.iterrows():
                # Para cada par columna→valor
                for col, val in row.items():
                    texto = f"<b>{col}:</b> {'' if pd.isna(val) else val}"
                    elementos.append(Paragraph(texto, normal))
                    elementos.append(Spacer(1, 2))
                # separación entre filas
                elementos.append(Spacer(1, 6))

    # Construir el PDF
    doc.build(elementos)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

# -----------------------------------------------------------
# FUNCIÓN PARA CARGAR TODOS LOS ARCHIVOS
# -----------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_data():
    is_cloud   = os.environ.get('STREAMLIT_SHARING', '') == 'true'
    base_path  = "." if is_cloud else os.path.dirname(os.path.abspath(__file__))
    restr_path = os.path.join(base_path, "RESTRICCIONES")

    info_carga = []

    def load_annex(name, filename, skip):
        # 1) Leer toda la tabla con saltos para datos
        path = os.path.join(restr_path, filename)
        df = pd.read_excel(path, skiprows=skip, header=0, engine="openpyxl")
        df.columns = df.columns.str.strip()

        # 2) Leer SOLO la fila de fallback (la fila justo anterior al header)
        raw = pd.read_excel(path, header=None, nrows=skip, engine="openpyxl")
        fallback = raw.iloc[skip-1].tolist()

        # 3) Reemplazar columnas Unnamed por el valor de fallback
        new_cols = []
        for idx, col in enumerate(df.columns):
            if str(col).lower().startswith("unnamed"):
                # fallback[idx] puede ser nan, así que chequeamos
                val = fallback[idx]
                new = str(val).strip() if pd.notna(val) else col
                new_cols.append(new)
            else:
                new_cols.append(col)
        df.columns = new_cols

        info_carga.append(f"✅ {name}: {len(df)} filas")
        return df

    annex_ii  = load_annex("Annex II",  "COSING_Annex_II_v2.xlsx",  7)
    annex_iii = load_annex("Annex III", "COSING_Annex_III_v2.xlsx",7)
    annex_iv  = load_annex("Annex IV",  "COSING_Annex_IV_v2.xlsx", 7)
    annex_v   = load_annex("Annex V",   "COSING_Annex_V_v2.xlsx",   7)
    annex_vi  = load_annex("Annex VI",  "COSING_Annex_VI_v2.xlsx", 7)

    # MERCOSUR Prohibidas
    mercosur = pd.DataFrame()
    try:
        path = os.path.join(restr_path, "07 MERCOSUR_062_2014_PROHIBIDAS.xlsx")
        # skiprows=5: header fila6, fallback fila5
        mercosur = pd.read_excel(path, skiprows=5, header=0, engine="openpyxl")
        mercosur.columns = mercosur.columns.str.strip()
        raw = pd.read_excel(path, header=None, nrows=5, engine="openpyxl")
        fallback = raw.iloc[4].tolist()
        new_cols = []
        for idx, col in enumerate(mercosur.columns):
            if str(col).lower().startswith("unnamed"):
                val = fallback[idx]
                new_cols.append(str(val).strip() if pd.notna(val) else col)
            else:
                new_cols.append(col)
        mercosur.columns = new_cols

        info_carga.append(f"✅ MERCOSUR Prohibidas: {len(mercosur)} filas")
    except Exception as e:
        info_carga.append(f"❌ Error MERCOSUR Prohibidas: {e}")

    # Cargar base de datos CAS - CORREGIDO
    cas_db = pd.DataFrame()
    try:
        # RUTA CORREGIDA: usar carpeta CAS
        cas_db_path = os.path.join(base_path, "CAS", "COSING_Ingredients-Fragrance Inventory_v2.xlsx")
        info_carga.append(f"Intentando cargar CAS desde: {cas_db_path}")
        
        # Intentar diferentes configuraciones de skiprows para encontrar la correcta
        cas_db_loaded = False
        for skip_rows in [7, 8, 6, 9, 5, 10, 4, 3, 2, 1, 0]:  # Empezar con 7 que es lo más probable
            try:
                cas_db_temp = pd.read_excel(cas_db_path, skiprows=skip_rows, header=0, engine="openpyxl")
                cas_db_temp.columns = cas_db_temp.columns.str.strip()
                
                # Verificar si tiene datos útiles y columnas reales (no todas "Unnamed")
                if len(cas_db_temp) > 1000:  # Debe tener muchos registros
                    # Contar cuántas columnas NO son "Unnamed"
                    named_columns = [col for col in cas_db_temp.columns if not str(col).lower().startswith("unnamed")]
                    unnamed_columns = [col for col in cas_db_temp.columns if str(col).lower().startswith("unnamed")]
                    
                    # Si tiene más columnas con nombre real que "Unnamed", es buena señal
                    if len(named_columns) >= len(unnamed_columns):
                        has_name_col = any('name' in col.lower() or 'inci' in col.lower() or 'ingredient' in col.lower() for col in cas_db_temp.columns)
                        if has_name_col:
                            cas_db = cas_db_temp
                            info_carga.append(f"✅ COSING Ingredients-Fragrance Inventory cargado con skiprows={skip_rows}: {len(cas_db)} filas")
                            info_carga.append(f"Columnas en CAS DB: {', '.join(cas_db.columns.tolist())}")
                            
                            # Renombrar columna si es necesario
                            if "INCI name" in cas_db.columns:
                                cas_db.rename(columns={"INCI name": "Ingredient"}, inplace=True)
                                info_carga.append("✅ Columna 'INCI name' renombrada a 'Ingredient'")
                            
                            cas_db_loaded = True
                            break
            except Exception as inner_e:
                continue
        
        if not cas_db_loaded:
            info_carga.append(f"❌ No se pudo cargar la base de datos CAS con ninguna configuración válida")
        
    except Exception as e:
        cas_db = pd.DataFrame(columns=['Ingredient', 'CAS Number'])
        info_carga.append(f"❌ Error cargando COSING Ingredients-Fragrance Inventory: {e}")

    return annex_ii, annex_iii, annex_iv, annex_v, annex_vi, mercosur, cas_db, info_carga
# -----------------------------------------------------------
# FUNCIÓN PARA BÚSQUEDA EN PUBCHEM POR CAS
# -----------------------------------------------------------
def buscar_cas_en_pubchem(cas_number):
    """
    Busca un número CAS en PubChem y devuelve información relevante.
    """
    try:
        # Primero, buscar el CAS para obtener el CompoundID (CID)
        search_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{cas_number}/cids/JSON"
        response = requests.get(search_url)
        
        if response.status_code != 200:
            return {
                'encontrado': False,
                'error': f"Error en la búsqueda: Código {response.status_code}",
                'mensaje': "No se encontró el CAS en PubChem"
            }
        
        data = response.json()
        
        if 'IdentifierList' not in data or 'CID' not in data['IdentifierList'] or not data['IdentifierList']['CID']:
            return {
                'encontrado': False,
                'error': "No se encontró un CID válido",
                'mensaje': "PubChem no tiene registros para este número CAS"
            }
        
        # Obtener el CID
        cid = data['IdentifierList']['CID'][0]
        
        # Obtener información detallada usando el CID
        info_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/MolecularFormula,MolecularWeight,IUPACName,InChIKey,CanonicalSMILES/JSON"
        info_response = requests.get(info_url)
        
        if info_response.status_code != 200:
            return {
                'encontrado': True,
                'cid': cid,
                'error': f"Error obteniendo detalles: Código {info_response.status_code}",
                'url': f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}"
            }
        
        info_data = info_response.json()
        properties = info_data['PropertyTable']['Properties'][0]
        
        # Obtener sinónimos
        synonyms_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/synonyms/JSON"
        synonyms_response = requests.get(synonyms_url)
        
        synonyms = []
        if synonyms_response.status_code == 200:
            synonyms_data = synonyms_response.json()
            if 'InformationList' in synonyms_data and 'Information' in synonyms_data['InformationList']:
                synonyms = synonyms_data['InformationList']['Information'][0].get('Synonym', [])
                # Limitar a máximo 10 sinónimos para no sobrecargar la UI
                synonyms = synonyms[:10] if len(synonyms) > 10 else synonyms
        
        return {
            'encontrado': True,
            'cid': cid,
            'nombre_iupac': properties.get('IUPACName', 'No disponible'),
            'formula': properties.get('MolecularFormula', 'No disponible'),
            'peso_molecular': properties.get('MolecularWeight', 'No disponible'),
            'inchikey': properties.get('InChIKey', 'No disponible'),
            'smiles': properties.get('CanonicalSMILES', 'No disponible'),
            'sinonimos': synonyms,
            'url': f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}"
        }
    
    except Exception as e:
        return {
            'encontrado': False,
            'error': str(e),
            'mensaje': "Error al conectar con PubChem"
        }

# -----------------------------------------------------------
# FUNCIÓN PARA BÚSQUEDA EN PUBCHEM POR NOMBRE DE INGREDIENTE
# -----------------------------------------------------------
def buscar_ingrediente_en_pubchem(nombre_ingrediente):
    """
    Busca un ingrediente por nombre en PubChem y devuelve información relevante.
    """
    try:
        # Primero, buscar el nombre para obtener el CompoundID (CID)
        search_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{nombre_ingrediente}/cids/JSON"
        response = requests.get(search_url)
        
        if response.status_code != 200:
            return {
                'encontrado': False,
                'error': f"Error en la búsqueda: Código {response.status_code}",
                'mensaje': f"No se encontró '{nombre_ingrediente}' en PubChem",
                'input': nombre_ingrediente
            }
        
        data = response.json()
        
        if 'IdentifierList' not in data or 'CID' not in data['IdentifierList'] or not data['IdentifierList']['CID']:
            return {
                'encontrado': False,
                'error': "No se encontró un CID válido",
                'mensaje': f"PubChem no tiene registros para '{nombre_ingrediente}'",
                'input': nombre_ingrediente
            }
        
        # Obtener el CID
        cid = data['IdentifierList']['CID'][0]
        
        # Obtener información detallada usando el CID
        info_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/MolecularFormula,MolecularWeight,IUPACName,InChIKey,CanonicalSMILES/JSON"
        info_response = requests.get(info_url)
        
        if info_response.status_code != 200:
            return {
                'encontrado': True,
                'cid': cid,
                'input': nombre_ingrediente,
                'error': f"Error obteniendo detalles: Código {info_response.status_code}",
                'url': f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}"
            }
        
        info_data = info_response.json()
        properties = info_data['PropertyTable']['Properties'][0]
        
        # Obtener sinónimos
        synonyms_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/synonyms/JSON"
        synonyms_response = requests.get(synonyms_url)
        
        synonyms = []
        if synonyms_response.status_code == 200:
            synonyms_data = synonyms_response.json()
            if 'InformationList' in synonyms_data and 'Information' in synonyms_data['InformationList']:
                synonyms = synonyms_data['InformationList']['Information'][0].get('Synonym', [])
                # Limitar a máximo 10 sinónimos para no sobrecargar la UI
                synonyms = synonyms[:10] if len(synonyms) > 10 else synonyms
        
        # Intentar obtener el número CAS
        cas_number = None
        if synonyms:
            # Buscar patrones como "CAS-xxxxx" o "xxxxx-xx-x" (formato CAS común)
            cas_pattern = re.compile(r'(?:CAS[ -]+)?(\d{1,7}-\d{2}-\d{1})')
            for syn in synonyms:
                cas_match = cas_pattern.search(syn)
                if cas_match:
                    cas_number = cas_match.group(1)
                    break
        
        return {
            'encontrado': True,
            'cid': cid,
            'input': nombre_ingrediente,
            'nombre_iupac': properties.get('IUPACName', 'No disponible'),
            'formula': properties.get('MolecularFormula', 'No disponible'),
            'peso_molecular': properties.get('MolecularWeight', 'No disponible'),
            'inchikey': properties.get('InChIKey', 'No disponible'),
            'smiles': properties.get('CanonicalSMILES', 'No disponible'),
            'sinonimos': synonyms,
            'cas_number': cas_number,
            'url': f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}"
        }
    
    except Exception as e:
        return {
            'encontrado': False,
            'error': str(e),
            'mensaje': f"Error al conectar con PubChem para '{nombre_ingrediente}'",
            'input': nombre_ingrediente
        }

# -----------------------------------------------------------
# FUNCIÓN PARA BUSCAR MÚLTIPLES ELEMENTOS EN PUBCHEM
# -----------------------------------------------------------
def buscar_lista_en_pubchem(lista, por_cas=True):
    """
    Busca múltiples números CAS o nombres de ingredientes en PubChem con un retraso para evitar sobrecargar la API.
    """
    resultados = {}
    
    for i, elemento in enumerate(lista):
        if i > 0:  # Añadir delay entre peticiones excepto para la primera
            time.sleep(1)  # 1 segundo de retraso para respetar límites de la API
        
        if por_cas:
            mensaje = f"Buscando CAS {elemento} en PubChem..."
            resultado = buscar_cas_en_pubchem(elemento)
        else:
            mensaje = f"Buscando ingrediente '{elemento}' en PubChem..."
            resultado = buscar_ingrediente_en_pubchem(elemento)
        
        with st.spinner(mensaje):
            resultados[elemento] = resultado
    
    return resultados

# -----------------------------------------------------------
# FUNCIÓN PARA BUSCAR CAS EN RESTRICCIONES
# -----------------------------------------------------------
def buscar_cas_en_restricciones(cas_list, mostrar_info=False):
    resultados = {}
    
    for cas_number in cas_list:
        resultados[cas_number] = {"encontrado": False, "anexos": []}
        
        if mostrar_info:
            st.markdown(f"### Buscando CAS: {cas_number}")
        
        # Búsqueda EXACTA en todos los anexos
        if mostrar_info:
            st.write(f"Buscando {cas_number} con coincidencia EXACTA...")
        
        encontrado_en_alguno = False
        
        for nombre_annex, df_annex in annex_data.items():
            if df_annex.empty:
                continue
            
            # Buscar columnas CAS
            cas_columns = [col for col in df_annex.columns if 'cas' in col.lower()]
            
            if not cas_columns:
                continue
            
            for cas_column in cas_columns:
                if mostrar_info:
                    st.write(f"Buscando en {nombre_annex}, columna '{cas_column}'...")
                
                # BÚSQUEDA EXACTA: Convertir a string, limpiar espacios y comparar exactamente
                matches = df_annex[df_annex[cas_column].astype(str).str.strip() == cas_number.strip()]
                
                if not matches.empty:
                    if mostrar_info:
                        st.success(f"✅ ENCONTRADO en {nombre_annex}, columna '{cas_column}' (coincidencia exacta)")
                        st.dataframe(matches)
                    
                    resultados[cas_number]["encontrado"] = True
                    resultados[cas_number]["anexos"].append({
                        "nombre": nombre_annex,
                        "data": matches
                    })
                    encontrado_en_alguno = True
                    break
            
            # Si ya lo encontramos en este anexo, pasamos al siguiente
            if encontrado_en_alguno:
                break
        
        if not encontrado_en_alguno and mostrar_info:
            st.warning(f"❌ No se encontró el CAS {cas_number} en ningún anexo (búsqueda exacta)")
        
        if mostrar_info:
            st.markdown("---")  # Separador entre resultados de CAS
    
    return resultados

# -----------------------------------------------------------
# FUNCIÓN PARA BUSCAR INGREDIENTES POR NOMBRE
# -----------------------------------------------------------
def buscar_ingredientes_por_nombre(ingredientes, exact=False):
    resultados_formula = []
    
    # Verificar si la base de datos CAS está cargada y no está vacía
    if cas_db.empty:
        st.error("La base de datos CAS está vacía o no se cargó correctamente.")
        return pd.DataFrame()
    
    # Detectar automáticamente las posibles columnas de nombre
    posibles_columnas_nombre = []
    for col in cas_db.columns:
        col_lower = col.lower()
        if any(keyword in col_lower for keyword in ['name', 'ingredient', 'inci', 'substance']):
            posibles_columnas_nombre.append(col)
    
    if not posibles_columnas_nombre:
        st.error("No se encontraron columnas que contengan nombres de ingredientes.")
        st.write("Las columnas disponibles son:", cas_db.columns.tolist())
        return pd.DataFrame()
    
    # Usar la primera columna detectada como columna principal
    columna_nombre = posibles_columnas_nombre[0]
    
    # Detectar columna de CAS
    columna_cas = None
    for col in cas_db.columns:
        if 'cas' in col.lower() and 'no' in col.lower():
            columna_cas = col
            break
    
    # Buscar cada ingrediente según el modo (exacto o aproximado)
    for ing in ingredientes:
        # Limpiar el ingrediente de búsqueda
        ing_limpio = ing.strip()
        
        if exact:
            # Comparación exacta (ignorando mayúsculas y espacios adicionales)
            mask = cas_db[columna_nombre].astype(str).str.lower().str.strip() == ing_limpio.lower()
            df_ing = cas_db[mask]
            
            if df_ing.empty:
                # Si no se encuentra, crear una fila indicando "No encontrado"
                df_not_found = pd.DataFrame({
                    "Búsqueda": [ing],
                    columna_nombre: [ing],
                    "Resultado": ["No encontrado (exacto)"]
                })
                if columna_cas:
                    df_not_found[columna_cas] = [None]
                resultados_formula.append(df_not_found)
            else:
                df_ing = df_ing.copy()
                df_ing["Búsqueda"] = ing
                resultados_formula.append(df_ing)
        else:
            # Búsqueda aproximada: se buscan coincidencias parciales
            mask = cas_db[columna_nombre].astype(str).str.contains(ing_limpio, case=False, na=False, regex=False)
            df_ing = cas_db[mask]
            
            if not df_ing.empty:
                df_ing = df_ing.copy()
                df_ing["Búsqueda"] = ing
                resultados_formula.append(df_ing)
            else:
                # También crear una fila "No encontrado" en modo aproximado
                df_not_found = pd.DataFrame({
                    "Búsqueda": [ing],
                    columna_nombre: [ing],
                    "Resultado": ["No encontrado (aproximado)"]
                })
                if columna_cas:
                    df_not_found[columna_cas] = [None]
                resultados_formula.append(df_not_found)
    
    if resultados_formula:
        resultado_final = pd.concat(resultados_formula, ignore_index=True)
        return resultado_final
    else:
        return pd.DataFrame()

# -----------------------------------------------------------
# FUNCIÓN PARA BUSCAR MÚLTIPLES CAS EN PUBCHEM
# -----------------------------------------------------------
def buscar_cas_faltantes_en_pubchem(ingredientes_sin_cas):
    """
    Busca números CAS en PubChem para ingredientes que no los tienen en la base local
    """
    st.info(f"🔍 Buscando números CAS en PubChem para {len(ingredientes_sin_cas)} ingredientes...")
    
    resultados_pubchem = {}
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, ingrediente in enumerate(ingredientes_sin_cas):
        # Actualizar progreso
        progress = (i + 1) / len(ingredientes_sin_cas)
        progress_bar.progress(progress)
        status_text.text(f"Buscando: {ingrediente} ({i+1}/{len(ingredientes_sin_cas)})")
        
        # Buscar en PubChem
        resultado = buscar_ingrediente_en_pubchem(ingrediente)
        resultados_pubchem[ingrediente] = resultado
        
        # Delay para no sobrecargar la API
        if i < len(ingredientes_sin_cas) - 1:
            time.sleep(1)
    
    progress_bar.empty()
    status_text.empty()
    
    # Procesar resultados
    cas_encontrados = {}
    ingredientes_sin_exito = []
    
    for ingrediente, resultado in resultados_pubchem.items():
        if resultado['encontrado'] and 'cas_number' in resultado and resultado['cas_number']:
            cas_encontrados[ingrediente] = resultado['cas_number']
        else:
            ingredientes_sin_exito.append(ingrediente)
    
    # Mostrar resultados
    if cas_encontrados:
        st.success(f"✅ Se encontraron números CAS para {len(cas_encontrados)} ingredientes en PubChem:")
        
        # Crear DataFrame con los resultados
        df_pubchem = pd.DataFrame([
            {
                "Ingrediente": ing,
                "CAS Number": cas,
                "Fuente": "PubChem"
            }
            for ing, cas in cas_encontrados.items()
        ])
        
        st.dataframe(df_pubchem)
        
        # Guardar en session_state para usar después
        st.session_state["cas_from_pubchem"] = df_pubchem
    
    if ingredientes_sin_exito:
        st.warning(f"⚠️ No se encontraron números CAS para {len(ingredientes_sin_exito)} ingredientes:")
        st.write(", ".join(ingredientes_sin_exito))
    
    return cas_encontrados

# -----------------------------------------------------------
# FUNCIÓN PARA VALIDAR Y FILTRAR CAS VÁLIDOS
# -----------------------------------------------------------
def validar_y_filtrar_cas(df_editado, cas_column):
    """
    Valida qué filas tienen números CAS válidos y cuáles no
    """
    seleccionadas = df_editado[df_editado["Seleccionar"] == True]
    
    if seleccionadas.empty:
        return [], [], "No se ha seleccionado ninguna fila."
    
    cas_validos = []
    ingredientes_sin_cas = []
    
    for _, row in seleccionadas.iterrows():
        cas_value = row[cas_column] if cas_column in row else None
        ingrediente = row.get("Búsqueda", "Ingrediente desconocido")
        
        # Verificar si el CAS es válido (no es NaN, None, o string vacío)
        if pd.notna(cas_value) and str(cas_value).strip() and str(cas_value).strip().lower() != 'nan':
            cas_validos.append(str(cas_value).strip())
        else:
            ingredientes_sin_cas.append(ingrediente)
    
    return cas_validos, ingredientes_sin_cas, None

# -----------------------------------------------------------
# FUNCIÓN PARA BUSCAR INGREDIENTES EN ANEXOS
# -----------------------------------------------------------
def buscar_ingredientes_en_anexos(ingredientes):
    resultados_anexos = {}
    
    for nombre_annex, df_annex in annex_data.items():
        if df_annex.empty or "Name" not in df_annex.columns:
            continue
        
        resultados_annex = pd.DataFrame()
        for ing in ingredientes:
            res = df_annex[df_annex["Name"].astype(str).str.contains(ing, case=False, na=False)]
            if not res.empty:
                res = res.copy()
                res["Búsqueda"] = ing
                resultados_annex = pd.concat([resultados_annex, res], ignore_index=True)
        
        if not resultados_annex.empty:
            resultados_anexos[nombre_annex] = resultados_annex
    
    return resultados_anexos

# -----------------------------------------------------------
# FUNCIÓN PARA MOSTRAR INFORMACIÓN DE PUBCHEM
# -----------------------------------------------------------
def mostrar_info_pubchem(pubchem_data):
    """
    Muestra la información de PubChem de forma organizada.
    """
    if pubchem_data['encontrado']:
        st.success("✅ Información encontrada en PubChem")
        
        input_value = pubchem_data.get('input', 'No disponible')
        
        # Información básica
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Búsqueda por:**", input_value)
            st.write("**Nombre IUPAC:**", pubchem_data.get('nombre_iupac', 'No disponible'))
            st.write("**Fórmula molecular:**", pubchem_data.get('formula', 'No disponible'))
            st.write("**Peso molecular:**", pubchem_data.get('peso_molecular', 'No disponible'))
        
        with col2:
            st.write("**CompoundID (CID):**", pubchem_data.get('cid', 'No disponible'))
            st.write("**InChIKey:**", pubchem_data.get('inchikey', 'No disponible'))
            
            # Mostrar CAS si está disponible
            if 'cas_number' in pubchem_data and pubchem_data['cas_number']:
                st.write("**Número CAS encontrado:**", pubchem_data['cas_number'])
            
            st.write("**SMILES:**", pubchem_data.get('smiles', 'No disponible'))
        
        # Sinónimos
        if 'sinonimos' in pubchem_data and pubchem_data['sinonimos']:
            with st.expander("Ver sinónimos"):
                for sinonimo in pubchem_data['sinonimos']:
                    st.write(f"• {sinonimo}")
        
        # Enlace a PubChem
        st.markdown(f"[Ver ficha completa en PubChem]({pubchem_data['url']})")
    else:
        st.warning("❌ No se encontró información en PubChem")
        if 'mensaje' in pubchem_data:
            st.write(pubchem_data['mensaje'])
        if 'error' in pubchem_data:
            st.write("Error:", pubchem_data['error'])

# -----------------------------------------------------------
# CARGA DE DATOS
# -----------------------------------------------------------
annex_ii, annex_iii, annex_iv, annex_v, annex_vi, mercosur, cas_db, info_carga = load_data()
annex_data = {
    "Annex II": annex_ii,
    "Annex III": annex_iii,
    "Annex IV": annex_iv,
    "Annex V": annex_v,
    "Annex VI": annex_vi,
    "MERCOSUR Prohibidas": mercosur
}

# -----------------------------------------------------------
# INTERFAZ PRINCIPAL
# -----------------------------------------------------------
st.title("Cosmetic Ingredient Checker")
st.write("""
Esta aplicación permite:
- Buscar en la base de datos de números CAS.
- Consultar en los listados de sustancias permitidas o prohibidas (anexos COSING y MERCOSUR).
- Revisar fórmulas completas (lista de ingredientes) y extraer la información asociada.
- Consultar información en PubChem.
""")

modo_busqueda = st.sidebar.selectbox(
    "Seleccione el método de búsqueda",
    [
        "Búsqueda por fórmula de ingredientes",
        "Búsqueda en restricciones por CAS",
        "Búsqueda en PubChem"
    ]
)

# -----------------------------------------------------------
# 1) Búsqueda por fórmula de ingredientes (con cas_column dinámico)
# -----------------------------------------------------------
if modo_busqueda == "Búsqueda por fórmula de ingredientes":
    st.header("Búsqueda por fórmula de ingredientes")
    formula_input = st.text_area("Ingredientes (separados por comas o líneas):")
    tipo_busqueda = st.radio("Tipo de búsqueda", ["Aproximada", "Exacta"])

    if st.button("Buscar Fórmula"):
        ingredientes = [i.strip() for i in re.split(r'[\n,]+', formula_input) if i.strip()]
        df_res = buscar_ingredientes_por_nombre(ingredientes, exact=(tipo_busqueda == "Exacta"))
        st.session_state["df_formula"] = df_res

    if "df_formula" in st.session_state:
        df = st.session_state["df_formula"]

        # 1) Detectar columna de CAS de forma dinámica
        cas_column = next((c for c in df.columns if 'cas' in c.lower()), None)

        if not df.empty and cas_column:
            # 2) Preparar tabla editable
            df_edit = df.copy()
            df_edit["Seleccionar"] = False
            cols = ["Seleccionar"] + [c for c in df_edit.columns if c != "Seleccionar"]
            df_edit = df_edit[cols]

            df_editado = st.data_editor(
                df_edit,
                column_config={
                    "Seleccionar": st.column_config.CheckboxColumn(label="Seleccionar")
                },
                use_container_width=True,
                key="editor_formula"
            )

            # 3) Botón que ahora usa la misma función de búsqueda manual
            if st.button("Buscar seleccionados en restricciones"):
                seleccionadas = df_editado[df_editado["Seleccionar"] == True]
                # Limpiar y extraer sólo strings no nulos
                cas_sel = [str(x).strip() for x in seleccionadas[cas_column] if pd.notna(x)]

                if not cas_sel:
                    st.warning("Selecciona al menos un CAS válido para buscar.")
                else:
                    # Ejecuta la misma búsqueda que en la rama manual
                    resultados = buscar_cas_en_restricciones(cas_sel, mostrar_info=False)

                    # Mostrar resultados idénticos a la búsqueda manual
                    st.subheader("Resultados en listados de restricciones")
                    for cas_n, res in resultados.items():
                        if res["encontrado"]:
                            st.markdown(f"### CAS {cas_n}")
                            for anexo in res["anexos"]:
                                st.write(f"**{anexo['nombre']}**")
                                st.dataframe(anexo["data"])
                                st.markdown("---")
                        else:
                            st.warning(f"⚠️ {cas_n} no encontrado en ningún anexo")

                    # Ofrecer descarga de PDF
                    pdf = generar_reporte_pdf(resultados)
                    st.download_button(
                        "📥 Descargar reporte en PDF",
                        data=pdf,
                        file_name="reporte_cas_restricciones.pdf",
                        mime="application/pdf"
                    )
        else:
            st.info("No se encontraron coincidencias en la base CAS o no hay columna CAS detectada.")

# ------------------------------------------------------------------------
# 2) Búsqueda en restricciones por CAS
# ------------------------------------------------------------------------
elif modo_busqueda == "Búsqueda en restricciones por CAS":
    st.header("Búsqueda en listados de restricciones por CAS")
    mostrar_info = st.checkbox("Mostrar información de carga", False)
    cas_input = st.text_area("Ingrese números CAS (uno por línea):")
    if st.button("Buscar CAS en restricciones"):
        cas_list = [x.strip() for x in re.split(r'[\n,;]+', cas_input) if x.strip()]
        if cas_list:
            if mostrar_info:
                st.write("".join(f"- {l}\n" for l in info_carga))
            resultados = buscar_cas_en_restricciones(cas_list, mostrar_info=False)
            st.subheader("Resultados")
            for cas_n, res in resultados.items():
                if res["encontrado"]:
                    st.markdown(f"### CAS {cas_n}")
                    for anexo in res["anexos"]:
                        st.write(f"**{anexo['nombre']}**")
                        st.dataframe(anexo["data"])
                        st.markdown("---")
                else:
                    st.warning(f"⚠️ {cas_n} no encontrado")

# ------------------------------------------------------------------------
# 3) Búsqueda en PubChem
# ------------------------------------------------------------------------
else:
    st.header("Búsqueda en PubChem")
    modo = st.radio("Buscar por:", ["Número CAS", "Nombre de ingrediente"])
    prompt = st.text_area("Ingrese valores (uno por línea):")
    if st.button("Buscar en PubChem"):
        items = [x.strip() for x in re.split(r'[\n,;]+', prompt) if x.strip()]
        if items:
            resultados = buscar_lista_en_pubchem(items, por_cas=(modo=="Número CAS"))
            for item, data in resultados.items():
                st.markdown(f"### {item}")
                mostrar_info_pubchem(data)
                st.markdown("---")
