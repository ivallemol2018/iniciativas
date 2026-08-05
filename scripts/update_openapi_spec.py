import os
import re
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

SPEC_SOURCE_PATH = 'api/nombre_repositorio.yaml'
SPEC_TARGET_TEMPLATE = 'api/{repo}.yaml'
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


def escalar_yaml(texto: str) -> str:
    """Escapa un valor para insertarlo como scalar plano de una linea en YAML.

    La plantilla usa placeholders sin comillas como '[NOMBRE-CONTROLADOR]', que no son
    YAML valido (se interpretan como flow sequence). Por eso el archivo no se puede
    parsear completo con yaml.safe_load y las sustituciones se hacen sobre texto.
    """
    if re.search(r'[:#{}\[\],&*!|>\'"%@`\n]', texto) or texto != texto.strip():
        escapado = texto.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escapado}"'
    return texto


def reemplazar_info(contenido: str, title: str, version: str) -> str:
    title_esc = escalar_yaml(title)
    contenido, n_title = re.subn(r'(?m)^(\s*title:\s*).*$', lambda m: m.group(1) + title_esc, contenido, count=1)
    contenido, n_version = re.subn(r'(?m)^(\s*version:\s*).*$', lambda m: m.group(1) + version, contenido, count=1)
    if not n_title or not n_version:
        raise ValueError("No se encontraron las claves 'title'/'version' bajo 'info' en la plantilla.")
    return contenido


def reemplazar_tags(contenido: str, tag: str) -> str:
    tag_esc = escalar_yaml(tag)
    descripcion_esc = escalar_yaml(f'{tag} Controller')
    patron = re.compile(r'(?m)^tags:\n(\s*-\s*name:\s*).*\n(\s*description:\s*).*$')
    nuevo, n = patron.subn(lambda m: f"tags:\n{m.group(1)}{tag_esc}\n{m.group(2)}{descripcion_esc}", contenido, count=1)
    if not n:
        raise ValueError("No se encontro el bloque 'tags' en la plantilla.")
    return nuevo


def reemplazar_paths(contenido: str, paths: dict) -> str:
    if paths:
        fragmento = yaml.safe_dump(paths, sort_keys=False, allow_unicode=True, default_flow_style=False)
        bloque = '\n'.join('  ' + linea if linea else linea for linea in fragmento.splitlines())
        reemplazo = 'paths:\n' + bloque + '\n'
    else:
        reemplazo = 'paths: {}\n'
    nuevo, n = re.subn(r'(?ms)^paths:.*\Z', lambda m: reemplazo, contenido, count=1)
    if not n:
        raise ValueError("No se encontro la clave 'paths' en la plantilla.")
    return nuevo


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


def crear_archivo(repo, path, contenido_yaml, mensaje):
    url = f"https://api.github.com/repos/{ORG}/{repo}/contents/{path}"
    payload = {
        'message': mensaje,
        'content': base64.b64encode(contenido_yaml.encode('utf-8')).decode('utf-8'),
    }
    response = requests.put(url, headers=HEADERS, json=payload)
    if response.status_code not in (200, 201):
        logging.error(f"No se pudo crear '{path}' en '{repo}': {response.status_code} - {response.text}")
        return False
    logging.info(f"Especificacion OpenAPI creada en '{repo}/{path}'.")
    return True


def eliminar_archivo(repo, path, sha, mensaje):
    url = f"https://api.github.com/repos/{ORG}/{repo}/contents/{path}"
    payload = {
        'message': mensaje,
        'sha': sha,
    }
    response = requests.delete(url, headers=HEADERS, json=payload)
    if response.status_code not in (200,):
        logging.error(f"No se pudo eliminar '{path}' en '{repo}': {response.status_code} - {response.text}")
        return False
    logging.info(f"Plantilla '{path}' eliminada de '{repo}'.")
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
        destino = SPEC_TARGET_TEMPLATE.format(repo=repo)

        contenido, sha = obtener_archivo(repo, SPEC_SOURCE_PATH)
        if contenido is None:
            continue

        try:
            nuevo_contenido = reemplazar_info(contenido, str(api_name).strip(), '1.0.0')
            nuevo_contenido = reemplazar_tags(nuevo_contenido, tag)
            nuevo_contenido = reemplazar_paths(nuevo_contenido, construir_paths(grupo, tag))
        except ValueError as error:
            logging.error(f"No se pudo actualizar la especificacion de '{repo}': {error}")
            continue

        if not crear_archivo(repo, destino, nuevo_contenido, f"chore: crear especificacion OpenAPI {destino}"):
            continue

        eliminar_archivo(repo, SPEC_SOURCE_PATH, sha, f"chore: eliminar plantilla {SPEC_SOURCE_PATH}")


if __name__ == '__main__':
    main()
