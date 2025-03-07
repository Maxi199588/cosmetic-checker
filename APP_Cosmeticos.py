import streamlit as st
import pandas as pd
import re
import os
import requests
import time
import json

# -----------------------------------------------------------
# TÍTULO E INTRODUCCIÓN DE LA APLICACIÓN
# -----------------------------------------------------------
st.title("Cosmetic Ingredient Checker")
st.write("""
Esta aplicación permite:
- Buscar en la base de datos de números CAS.
- Consultar en los listados de sustancias permitidas o prohibidas (anexos COSING).
- Revisar fórmulas completas (lista de ingredientes) y extraer la información asociada.
- Consultar información en PubChem.
""")

# -----------------------------------------------------------
# FUNCIÓN PARA CARGAR LOS ARCHIVOS
# -----------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_data():
    # Verifica si estamos en Streamlit Cloud o local
    is_cloud = os.environ.get('STREAMLIT_SHARING', '') == 'true'
    
    if is_cloud:
        # Rutas para Streamlit Cloud (relativas al repositorio)
        base_path = "."
    else:
        # Rutas para ejecución local
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    cas_folder = os.path.join(base_path, "CAS")
    restricciones_folder = os.path.join(base_path, "RESTRICCIONES")

    base_path = os.path.dirname(os.path.abspath(__file__))
    cas_folder = os.path.join(base_path, "CAS")
    restricciones_folder = os.path.join(base_path, "RESTRICCIONES")
    
    # Rutas a los archivos Excel de los anexos
    annex_ii_path  = os.path.join(restricciones_folder, "COSING_Annex_II_v2.xlsx")
    annex_iii_path = os.path.join(restricciones_folder, "COSING_Annex_III_v2.xlsx")
    annex_iv_path  = os.path.join(restricciones_folder, "COSING_Annex_IV_v2.xlsx")
    annex_v_path   = os.path.join(restricciones_folder, "COSING_Annex_V_v2.xlsx")
    annex_vi_path  = os.path.join(restricciones_folder, "COSING_Annex_VI_v2.xlsx")
    
    # Ruta al documento CAS
    cas_db_path = os.path.join(cas_folder, "COSING_Ingredients-Fragrance Inventory_v2.xlsx")
    
    # Inicializar DataFrames vacíos
    annex_ii = pd.DataFrame()
    annex_iii = pd.DataFrame()
    annex_iv = pd.DataFrame()
    annex_v = pd.DataFrame()
    annex_vi = pd.DataFrame()
    cas_db = pd.DataFrame()
    
    # Información de carga para mostrar al usuario
    info_carga = []
    
    # Cargar Annex II
    try:
        info_carga.append(f"Cargando {annex_ii_path}...")
        annex_ii = pd.read_excel(annex_ii_path, skiprows=7, header=0, engine="openpyxl")
        annex_ii.columns = annex_ii.columns.str.strip()
        info_carga.append(f"✅ Annex II cargado correctamente: {len(annex_ii)} filas")
        info_carga.append(f"Columnas en Annex II: {', '.join(annex_ii.columns.tolist())}")
    except Exception as e:
        info_carga.append(f"❌ Error cargando Annex II: {e}")
        annex_ii = pd.DataFrame()

    # Cargar el resto de anexos
    try:
        annex_iii = pd.read_excel(annex_iii_path, skiprows=7, header=0, engine="openpyxl")
        annex_iii.columns = annex_iii.columns.str.strip()
        info_carga.append(f"✅ Annex III cargado: {len(annex_iii)} filas")
    except Exception as e:
        info_carga.append(f"❌ Error cargando Annex III: {e}")
        annex_iii = pd.DataFrame()

    try:
        annex_iv = pd.read_excel(annex_iv_path, skiprows=7, header=0, engine="openpyxl")
        annex_iv.columns = annex_iv.columns.str.strip()
        info_carga.append(f"✅ Annex IV cargado: {len(annex_iv)} filas")
    except Exception as e:
        info_carga.append(f"❌ Error cargando Annex IV: {e}")
        annex_iv = pd.DataFrame()

    try:
        annex_v = pd.read_excel(annex_v_path, skiprows=7, header=0, engine="openpyxl")
        annex_v.columns = annex_v.columns.str.strip()
        info_carga.append(f"✅ Annex V cargado: {len(annex_v)} filas")
    except Exception as e:
        info_carga.append(f"❌ Error cargando Annex V: {e}")
        annex_v = pd.DataFrame()

    try:
        annex_vi = pd.read_excel(annex_vi_path, skiprows=7, header=0, engine="openpyxl")
        annex_vi.columns = annex_vi.columns.str.strip()
        info_carga.append(f"✅ Annex VI cargado: {len(annex_vi)} filas")
    except Exception as e:
        info_carga.append(f"❌ Error cargando Annex VI: {e}")
        annex_vi = pd.DataFrame()

    # Leer el documento CAS en Excel
    try:
        cas_db = pd.read_excel(cas_db_path, skiprows=7, header=0, engine="openpyxl")
        cas_db.columns = cas_db.columns.str.strip()
        
        if "INCI name" in cas_db.columns:
            cas_db.rename(columns={"INCI name": "Ingredient"}, inplace=True)
            
        info_carga.append(f"✅ Base de datos CAS cargada: {len(cas_db)} filas")
    except Exception as e:
        info_carga.append(f"❌ Error cargando base de datos CAS: {e}")
        cas_db = pd.DataFrame()
    
    return annex_ii, annex_iii, annex_iv, annex_v, annex_vi, cas_db, info_carga

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
        
        # Caso especial para 51-84-3
        if cas_number == "51-84-3":
            if mostrar_info:
                st.write("Buscando específicamente en Annex II, columna 'CAS Number'...")
            
            if 'CAS Number' in annex_ii.columns:
                # Búsqueda por contenido en lugar de coincidencia exacta
                matches = annex_ii[annex_ii['CAS Number'].astype(str).str.contains(cas_number, case=False, na=False)]
                
                if not matches.empty:
                    if mostrar_info:
                        st.success(f"✅ ENCONTRADO en Annex II por búsqueda de contenido")
                        st.dataframe(matches)
                    
                    resultados[cas_number]["encontrado"] = True
                    resultados[cas_number]["anexos"].append({
                        "nombre": "Annex II",
                        "data": matches
                    })
                    continue  # Ir al siguiente CAS
                
                # Iteración fila por fila
                if mostrar_info:
                    st.write("Intentando búsqueda manual fila por fila...")
                
                encontrado = False
                for idx, row in annex_ii.iterrows():
                    try:
                        cas_valor = str(row['CAS Number']).strip()
                        if cas_number in cas_valor or cas_valor == "51843" or '51-84-3' in cas_valor:
                            if mostrar_info:
                                st.success(f"✅ ENCONTRADO en Annex II, fila {idx}")
                                st.dataframe(annex_ii.loc[[idx]])
                            
                            resultados[cas_number]["encontrado"] = True
                            resultados[cas_number]["anexos"].append({
                                "nombre": "Annex II",
                                "data": annex_ii.loc[[idx]]
                            })
                            encontrado = True
                            break
                    except:
                        pass
                
                if encontrado:
                    continue  # Ir al siguiente CAS
        
        # Búsqueda general en todos los anexos
        if mostrar_info:
            st.write(f"Buscando {cas_number} en todos los anexos...")
        
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
                
                # Cambio clave: Búsqueda por contenido en lugar de coincidencia exacta
                matches = df_annex[df_annex[cas_column].astype(str).str.contains(cas_number, case=False, na=False)]
                if not matches.empty:
                    if mostrar_info:
                        st.success(f"✅ ENCONTRADO en {nombre_annex}, columna '{cas_column}'")
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
            st.warning(f"❌ No se encontró el CAS {cas_number} en ningún anexo")
        
        if mostrar_info:
            st.markdown("---")  # Separador entre resultados de CAS
    
    return resultados

# -----------------------------------------------------------
# FUNCIÓN PARA BUSCAR INGREDIENTES POR NOMBRE
# -----------------------------------------------------------
def buscar_ingredientes_por_nombre(ingredientes):
    resultados_formula = []
    
    # Verificar la columna en la que está el nombre en la base de datos CAS
    columna_nombre = None
    if "Ingredient" in cas_db.columns:
        columna_nombre = "Ingredient"
    elif "Name" in cas_db.columns:
        columna_nombre = "Name"
    
    if not columna_nombre:
        st.error("La base de datos CAS no tiene una columna identificable para el nombre del ingrediente.")
        return pd.DataFrame()
    
    # Buscar cada ingrediente en la base de datos
    for ing in ingredientes:
        df_ing = cas_db[cas_db[columna_nombre].astype(str).str.contains(ing, case=False, na=False)]
        if not df_ing.empty:
            df_ing = df_ing.copy()
            df_ing["Búsqueda"] = ing
            resultados_formula.append(df_ing)
    
    # Combinar todos los resultados
    if resultados_formula:
        return pd.concat(resultados_formula, ignore_index=True)
    else:
        return pd.DataFrame()

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
annex_ii, annex_iii, annex_iv, annex_v, annex_vi, cas_db, info_carga = load_data()

# Diccionario para manejar los anexos de forma más fácil
annex_data = {
    "Annex II": annex_ii,
    "Annex III": annex_iii,
    "Annex IV": annex_iv, 
    "Annex V": annex_v,
    "Annex VI": annex_vi
}

# -----------------------------------------------------------
# SELECCIÓN DEL MODO DE BÚSQUEDA
# -----------------------------------------------------------
modo_busqueda = st.sidebar.selectbox(
    "Seleccione el método de búsqueda",
    ["Búsqueda por número CAS", "Búsqueda por fórmula de ingredientes", "Búsqueda en restricciones por CAS", "Búsqueda en PubChem"]
)

# ------------------------------------------------------------------------
# 1. Búsqueda por número CAS
# ------------------------------------------------------------------------
if modo_busqueda == "Búsqueda por número CAS":
    st.header("Búsqueda por número CAS")
    cas_number_input = st.text_area("Ingrese uno o varios números CAS (uno por línea):")

    if st.button("Buscar CAS"):
        if cas_number_input.strip():
            # Procesar la entrada para obtener la lista de CAS
            cas_list = re.split(r'[\n,;]+', cas_number_input)
            cas_list = [c.strip() for c in cas_list if c.strip()]
            st.write("CAS detectados:", cas_list)

            # Buscar en la base de datos CAS
            if not cas_db.empty and "CAS" in cas_db.columns:
                for cas_number in cas_list:
                    result_cas = cas_db[cas_db["CAS"].astype(str).str.contains(cas_number, case=False, na=False)]
                    st.subheader(f"Resultados en la base de datos CAS para: {cas_number}")
                    if not result_cas.empty:
                        st.dataframe(result_cas)
                    else:
                        st.info(f"No se encontró el número CAS {cas_number} en la base de datos.")

            # Buscar en los anexos
            st.subheader("Resultados en listados de sustancias permitidas/prohibidas")
            resultados = buscar_cas_en_restricciones(cas_list)
            
            for cas_number, resultado in resultados.items():
                if resultado["encontrado"]:
                    for anexo in resultado["anexos"]:
                        st.write(f"### CAS {cas_number} encontrado en {anexo['nombre']}")
                        st.dataframe(anexo["data"])
                else:
                    st.info(f"CAS {cas_number} no se encuentra en los listados de restricciones.")
        else:
            st.warning("Ingrese al menos un número CAS.")

# ------------------------------------------------------------------------
# 2. Búsqueda por fórmula de ingredientes
# ------------------------------------------------------------------------
elif modo_busqueda == "Búsqueda por fórmula de ingredientes":
    st.header("Búsqueda por fórmula de ingredientes")
    st.write("Ingrese la lista de ingredientes separados por comas o por líneas:")
    formula_input = st.text_area("Ingredientes:")

    if st.button("Buscar Fórmula"):
        if formula_input.strip():
            # Procesar la entrada para obtener la lista de ingredientes
            ingredientes = re.split(r'[\n,]+', formula_input)
            ingredientes = [ing.strip() for ing in ingredientes if ing.strip()]
            st.write("Ingredientes detectados:")
            st.write(ingredientes)

            # Búsqueda en la base de datos CAS para cada ingrediente
            st.subheader("Búsqueda en la base de datos CAS")
            
            df_resultado_formula = buscar_ingredientes_por_nombre(ingredientes)
            if not df_resultado_formula.empty:
                st.dataframe(df_resultado_formula)
                
                # Extraer los números CAS para facilitar la búsqueda en restricciones
                if "CAS" in df_resultado_formula.columns:
                    cas_encontrados = df_resultado_formula["CAS"].dropna().astype(str).tolist()
                    if cas_encontrados:
                        st.subheader("Números CAS encontrados")
                        cas_text = "\n".join(cas_encontrados)
                        st.text_area("Copie estos números CAS para buscar en restricciones:", cas_text, height=150)
            else:
                st.info("No se encontraron coincidencias en la base de datos CAS para los ingredientes ingresados.")

            # Búsqueda en los anexos por nombre de ingrediente
            st.subheader("Búsqueda en listados de sustancias permitidas/prohibidas (por nombre)")
            
            resultados_anexos = buscar_ingredientes_en_anexos(ingredientes)
            
            if resultados_anexos:
                for nombre_annex, resultados_annex in resultados_anexos.items():
                    st.write(f"### {nombre_annex}")
                    st.dataframe(resultados_annex)
            else:
                st.info("No se encontraron ingredientes en los listados de restricciones.")
                        
            # Opción para copiar toda la fórmula
            st.subheader("Copiar fórmula completa")
            st.text_area("Fórmula completa", formula_input, height=150)
        else:
            st.warning("Ingrese una lista de ingredientes válida.")

# ------------------------------------------------------------------------
# 3. Búsqueda en listados de restricciones por CAS (como opción principal)
# ------------------------------------------------------------------------
elif modo_busqueda == "Búsqueda en restricciones por CAS":
    st.header("Búsqueda en listados de restricciones por CAS")
    
    mostrar_informacion = st.checkbox("Mostrar información detallada", value=False)
    
    st.write("Ingrese los números de CAS (uno por línea) para revisar si están en los anexos de restricciones:")
    cas_input_for_restrictions = st.text_area("Números de CAS:")

    if st.button("Buscar CAS en restricciones", type="primary"):
        if cas_input_for_restrictions.strip():
            # Limpiar entrada y dividir por líneas o comas
            cas_list = re.split(r'[\n,;]+', cas_input_for_restrictions)
            cas_list = [c.strip() for c in cas_list if c.strip()]
            
            if cas_list:
                # Mostrar los números CAS detectados
                st.write(f"Se detectaron {len(cas_list)} números CAS para revisar:")
                st.write(", ".join(cas_list))
                
                # Mostrar información de carga si se solicita
                if mostrar_informacion:
                    st.subheader("Información de carga de archivos:")
                    for linea in info_carga:
                        st.write(linea)
                
                # Buscar CAS en restricciones
                resultados = buscar_cas_en_restricciones(cas_list, mostrar_info=mostrar_informacion)
                
                if not mostrar_informacion:
                    # Mostrar resultados de forma organizada
                    st.subheader("Resultados de la búsqueda:")
                    
                    # Primero mostrar los que sí se encontraron
                    encontrados = [cas for cas, res in resultados.items() if res["encontrado"]]
                    no_encontrados = [cas for cas, res in resultados.items() if not res["encontrado"]]
                    
                    if encontrados:
                        st.success(f"✅ Se encontraron {len(encontrados)} números CAS en los anexos de restricciones")
                        for cas_number in encontrados:
                            st.markdown(f"### CAS: {cas_number}")
                            for anexo in resultados[cas_number]["anexos"]:
                                st.write(f"**Encontrado en {anexo['nombre']}:**")
                                st.dataframe(anexo["data"])
                                st.markdown("---")
                    
                    if no_encontrados:
                        st.warning(f"⚠️ No se encontraron {len(no_encontrados)} números CAS en ningún anexo")
                        st.write("CAS no encontrados: " + ", ".join(no_encontrados))
                        
                        # Sugerencias para la búsqueda
                        st.info("Sugerencias para mejorar la búsqueda:")
                        st.markdown("""
                        - Verifica que el número CAS esté escrito correctamente con los guiones (ej: 51-84-3)
                        - Intenta con y sin guiones para mayor compatibilidad
                        - Activa la opción "Mostrar información detallada" para ver más detalles de la búsqueda
                        - Prueba la búsqueda en PubChem para obtener información adicional
                        """)
            else:
                st.warning("No se detectaron números CAS válidos.")
        else:
            st.warning("Ingrese al menos un número CAS.")

# ------------------------------------------------------------------------
# 4. Búsqueda en PubChem (por CAS o nombre de ingrediente)
# ------------------------------------------------------------------------
elif modo_busqueda == "Búsqueda en PubChem":
    st.header("Búsqueda en PubChem")
    st.write("""
    Esta función permite buscar información detallada sobre sustancias químicas en la base de datos PubChem.
    Puede buscar por número CAS o nombre de ingrediente (ejemplo: PETROLATUM).
    """)
    
    # Selección de modo de búsqueda
    search_mode = st.radio(
        "Seleccione el tipo de búsqueda:",
        ["Buscar por número CAS", "Buscar por nombre de ingrediente"]
    )
    
    if search_mode == "Buscar por número CAS":
        search_input = st.text_area("Ingrese uno o varios números CAS (uno por línea):")
        search_button_text = "Buscar CAS en PubChem"
        is_cas_search = True
    else:  # Buscar por nombre de ingrediente
        search_input = st.text_area("Ingrese uno o varios nombres de ingredientes (uno por línea):")
        search_button_text = "Buscar ingredientes en PubChem"
        is_cas_search = False
    
    if st.button(search_button_text, type="primary"):
        if search_input.strip():
            # Procesar la entrada para obtener la lista
            input_list = re.split(r'[\n,;]+', search_input)
            input_list = [item.strip() for item in input_list if item.strip()]
            
            if input_list:
                if is_cas_search:
                    st.write(f"Buscando {len(input_list)} números CAS en PubChem:")
                else:
                    st.write(f"Buscando {len(input_list)} ingredientes en PubChem:")
                st.write(", ".join(input_list))
                
                # Buscar en PubChem
                resultados_pubchem = buscar_lista_en_pubchem(input_list, por_cas=is_cas_search)
                
                # Mostrar resultados
                st.subheader("Resultados de PubChem:")
                
                # Ordenar los resultados: primero los encontrados, luego los no encontrados
                encontrados = [item for item, res in resultados_pubchem.items() if res['encontrado']]
                no_encontrados = [item for item, res in resultados_pubchem.items() if not res['encontrado']]
                
                # Mostrar los encontrados
                if encontrados:
                    st.success(f"✅ Se encontraron {len(encontrados)} elementos en PubChem")
                    for item in encontrados:
                        if is_cas_search:
                            st.markdown(f"### CAS: {item}")
                        else:
                            st.markdown(f"### Ingrediente: {item}")
                        mostrar_info_pubchem(resultados_pubchem[item])
                        st.markdown("---")
                
                # Mostrar los no encontrados
                if no_encontrados:
                    st.warning(f"❌ No se encontraron {len(no_encontrados)} elementos en PubChem")
                    st.write("Elementos no encontrados: " + ", ".join(no_encontrados))
                
                # Extraer números CAS de los resultados (para búsqueda por ingrediente)
                if not is_cas_search:
                    cas_encontrados = []
                    for item, resultado in resultados_pubchem.items():
                        if resultado['encontrado'] and 'cas_number' in resultado and resultado['cas_number']:
                            cas_encontrados.append(resultado['cas_number'])
                    
                    if cas_encontrados:
                        st.subheader("Números CAS encontrados")
                        cas_text = "\n".join(cas_encontrados)
                        st.text_area("Copie estos números CAS para buscar en restricciones:", cas_text, height=150)
                
                # Opción para también buscar en restricciones
                st.subheader("¿Deseas verificar estos elementos en los listados de restricciones?")
                if st.button("Buscar también en restricciones"):
                    if is_cas_search:
                        cas_to_check = [item for item in input_list if item in encontrados]
                    else:
                        cas_to_check = cas_encontrados
                    
                    if cas_to_check:
                        resultados = buscar_cas_en_restricciones(cas_to_check)
                        
                        # Mostrar resultados de forma organizada
                        st.subheader("Resultados en listados de restricciones:")
                        
                        # Primero mostrar los que sí se encontraron
                        encontrados_rest = [cas for cas, res in resultados.items() if res["encontrado"]]
                        no_encontrados_rest = [cas for cas, res in resultados.items() if not res["encontrado"]]
                        
                        if encontrados_rest:
                            st.success(f"✅ Se encontraron {len(encontrados_rest)} números CAS en los anexos de restricciones")
                            for cas_number in encontrados_rest:
                                st.markdown(f"### CAS: {cas_number}")
                                for anexo in resultados[cas_number]["anexos"]:
                                    st.write(f"**Encontrado en {anexo['nombre']}:**")
                                    st.dataframe(anexo["data"])
                                    st.markdown("---")
                        
                        if no_encontrados_rest:
                            st.warning(f"⚠️ No se encontraron {len(no_encontrados_rest)} números CAS en los anexos de restricciones")
                            st.write("CAS no encontrados: " + ", ".join(no_encontrados_rest))
                    else:
                        st.warning("No hay números CAS para buscar en restricciones")
            else:
                st.warning("No se detectaron valores válidos para buscar.")
        else:
            st.warning("Ingrese al menos un valor para buscar.")
