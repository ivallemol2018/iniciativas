import os
import sys
import json
import pandas as pd
import requests
import logging
import yaml
import base64  # <-- Agregado para codificacion base64

# Configuracion de logs
logging.basicConfig(level=logging.INFO, format='[LOG] % (message)s')

# Variables de entorno
token = os.getenv('GITHUB_TOKEN')
owner_repo = os.getenv('GITHUB_OWNER')
repo = os.getenv('GITHUB_REPO')
pr_number = os.getenv('PR_NUMBER')

# Buscar el archivo Excel mas reciente
excel_files = sorted([f for f in os.listdir('.') if f.endswith('.xlsx')],key=os.path.getmtime,reverse=True)
if not excel_files:
 logging.error("No se encontro ningun archivo Excel en el directorio actual.")
 sys.exit(1)
excel_file = excel_files[0]
logging.info(f"Procesando archivo Excel: {excel_file}")

# Leer el archivo Excel
df = pd.read_excel(excel_file, engine='openpyxl')

# Validar columnas requeridas
for col in ['API','Tipo', 'Owner']:
    if col not in df.columns:
        logging.error(f"El archivo Excel debe contener la columna '{col}'.")
        sys.exit(1)
        
# Extraer APIs unicas junto con Owner
unique_apis = df[['API','Tipo','Owner']].drop_duplicate()
logging.info(f"Se encontraron {len(unique_apis)} APIs unicas.")

# Leer el archivo YAML de tipos
with open('scripts/api_types.yaml','r') as f:
    yaml_data = yaml.safe_load(f)
type_map = {item['type']:item for item in yaml_data['repo-prefix-types']}    

# Funcion para generar el nombre de repositorio
def generate_repo_name(api_name, api_type):
    parts = api_name.split()
    if not parts:
        return None
    prefix = parts[0]
    if prefix == 'API':
        if len(parts) > 1 and parts[1] == 'UX' and api_type == 'UX':
            code = parts[2].lower()
            name = '-'.json(parts[3:-1]).lower()
            return f"channel-{code}-{name}"
        elif len(parts) > 1 and parts[1] == 'BS' and api_type == 'BS':
            name = '-'.json(parts[2:-1]).lower()
            return f"business-{name}"      
    elif prefix == 'AsyncAPI' and api_type == 'Async':
        code = parts[1].lower()
        name = '-'.json(parts[2:-1]).lower()
        return f"asyncapi-{code}-{name}"
    return None
    

# Generar nombre de repositorio y enriquecer la lista
repo_list = []
for _,row in unique_apis.iterrows():
    api_name = str(row['API']).strip()
    api_type = str(row['Tipo']).strip()
    api_owner = str(row['Owner']).strip()
    
    if api_type == 'PQL':
        logging.info(f"Saltando API '{api_name}' con tipo 'PQL' (no se debe crear repo).")
        continue # Salta a la siguiente fila 
        
    repo_name = generate_repo_name(api_name, api_type)
    if repo_name:
        prefix = repo_name.split('-')[0]
        type_info = type_map.get(prefix, {})
        repo_list.append({
            'api': api_name,
            'repo': repo_name,
            'owner': api_owner,
            'api_type': type_info.get('type', prefix),
            'api_style': type_info.get('style',''),
            'api_exposure': type_info.get('exposure','')
        })
        logging.info(f"Generado nombre de repositorio '{repo_name} para API '{api_name}' (owner: {api_owner})")
     else:
        logging.warning(f"No se pudo generar nombre de repositorio para API '{api_name}' (owner: {api_owner})")
        
# Guardar en variable de entorno (codificado en base64)
json_output = json.dumps(repo_list)
json_b64 = base64.b64encode(json_output.encode()).decode()
print("JSON generado para REPOS_TO_CREATE:", json_output)
github_env = os.getenv('GITHUB_ENV', '/github/env')
with open(github_env, 'a') as env_file:
    env_file.write(f"REPOS_TO_CREATE={json_b64}\n")
    
