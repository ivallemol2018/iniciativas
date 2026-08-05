import os
import sys
import time
import base64
import logging

import pandas as pd
import requests
import yaml

from repo_naming import parse_api_name, controller_name

logging.basicConfig(level=logging.INFO, format='[LOG] %(message)s')

TOKEN = os.getenv('GITHUB_TOKEN')
ORG = os.getenv('GITHUB_OWNER')

SPEC_PATH_TEMPLATE = 'template/api/{repo}.yaml'
REQUIRED_COLUMNS = ['API', 'Tipo', 'Owner', 'Metodo', 'Endpoint', 'Descripcion del Endpoint']

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def cargar_repos_creados(path="repos_creados.txt"):
    if not os.path.exists(path):
        logging.info("No existe repos_creados.txt: no se creo ningun repositorio en esta corrida.")
        return set()
    with open(path) as f:
        return {linea.split(',')[0].strip() for linea in f if linea.strip()}


def cargar_excel():
    excel_files = sorted([f for f in os.listdir('.') if f.endswith('.xlsx')], key=os.path.getmtime, reverse=True)
    if not excel_files:
        logging.error("No se encontro ningun archivo Excel en el directorio actual.")
        sys.exit(1)
    excel_file = excel_files[0]
    logging.info(f"Procesando archivo Excel: {excel_file}")
    df = pd.read_excel(excel_file, engine='openpyxl')
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            logging.error(f"El archivo Excel debe contener la columna '{col}'.")
            sys.exit(1)
    return df


def construir_paths(filas, tag):
    paths = {}
    for _, fila in filas.iterrows():
        endpoint = str(fila['Endpoint']).strip()
        metodo = str(fila['Metodo']).strip().lower()
        descripcion = str(fila['Descripcion del Endpoint']).strip()
        if not endpoint or not metodo:
            continue
        paths.setdefault(endpoint, {})[metodo] = {
            'tags': [tag],
            'summary': descripcion,
            'responses': {
                '200': {'description': 'OK'},
            },
        }
    return paths


def obtener_archivo(repo, path):
    url = f"https://api.github.com/repos/{ORG}/{repo}/contents/{path}"
    for intento in range(3):
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            data = response.json()
            contenido = base64.b64decode(data['content']).decode('utf-8')
            return contenido, data['sha']
        if response.status_code == 404 and intento < 2:
            logging.info(f"'{path}' aun no disponible en '{repo}', reintentando...")
            time.sleep(5)
            continue
        logging.error(f"No se pudo obtener '{path}' en '{repo}': {response.status_code} - {response.text}")
        return None, None
    return None, None


def actualizar_archivo(repo, path, contenido_yaml, sha, mensaje):
    url = f"https://api.github.com/repos/{ORG}/{repo}/contents/{path}"
    payload = {
        'message': mensaje,
        'content': base64.b64encode(contenido_yaml.encode('utf-8')).decode('utf-8'),
        'sha': sha,
    }
    response = requests.put(url, headers=HEADERS, json=payload)
    if response.status_code not in (200, 201):
        logging.error(f"No se pudo actualizar '{path}' en '{repo}': {response.status_code} - {response.text}")
        return False
    logging.info(f"Especificacion OpenAPI actualizada en '{repo}'.")
    return True


def main():
    if not TOKEN or not ORG:
        logging.error("Faltan las variables de entorno GITHUB_TOKEN u GITHUB_OWNER.")
        sys.exit(1)

    repos_creados = cargar_repos_creados()
    if not repos_creados:
        logging.info("No hay repositorios nuevos que actualizar.")
        return

    df = cargar_excel()

    for api_name, grupo in df.groupby('API', sort=False):
        api_type = str(grupo.iloc[0]['Tipo']).strip()
        if api_type == 'PQL':
            continue

        parsed = parse_api_name(str(api_name).strip(), api_type)
        if not parsed or parsed['repo_name'] not in repos_creados:
            continue

        repo = parsed['repo_name']
        tag = controller_name(parsed['name_part'])
        spec_path = SPEC_PATH_TEMPLATE.format(repo=repo)

        contenido, sha = obtener_archivo(repo, spec_path)
        if contenido is None:
            continue

        spec = yaml.safe_load(contenido)
        spec['info']['title'] = str(api_name).strip()
        spec['info']['version'] = '1.0.0'
        spec['tags'] = [{'name': tag, 'description': f'{tag} Controller'}]
        spec['paths'] = construir_paths(grupo, tag)

        nuevo_contenido = yaml.dump(spec, sort_keys=False, allow_unicode=True)
        actualizar_archivo(repo, spec_path, nuevo_contenido, sha, f"chore: actualizar especificacion OpenAPI de {repo}")


if __name__ == '__main__':
    main()
