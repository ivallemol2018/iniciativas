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
REQUIRED_COLUMNS = ['API', 'Estilo', 'Tipo', 'Owner', 'Metodo', 'Endpoint', 'Descripcion del Endpoint']

METODO_A_OPERACION_ASYNC = {
    'send': 'publish',
    'publish': 'publish',
    'receive': 'subscribe',
    'subscribe': 'subscribe',
}

HEADERS_INTERNOS = ['Authorization', 'Request-ID', 'request-data', 'app-code', 'caller-name', 'Ocp-Apim-Subscription-Key']
HEADERS_UX = ['Authorization', 'Ocp-Apim-Subscription-Key']
HEADERS_PV = ['Authorization', 'subscription-key']

HEADERS_REQUERIDOS_POR_TIPO = {
    'BS': HEADERS_INTERNOS,
    'CR': HEADERS_INTERNOS,
    'DATA': HEADERS_INTERNOS,
    'UX': HEADERS_UX,
    'PV': HEADERS_PV,
}

# Componentes de error estandar que se agregan a toda especificacion REST generada,
# para que cada endpoint pueda referenciar '500'/'504' contra un mismo contrato de error.
COMPONENTES_ERROR = {
    'responses': {
        'InternalServerError': {
            'description': 'El servicio lanzo algun error. Por favor contactarse con soporte Tecnico. Por favor, comuniquese con su administrador.',
            'content': {
                'application/json': {
                    'schema': {'$ref': '#/components/schemas/ApiException'},
                    'examples': {
                        'internalServerErrorExample': {'$ref': '#/components/examples/InternalServerErrorExample'},
                    },
                },
            },
        },
        'GatewayTimeout': {
            'description': 'El tiempo de espera para recibir una respuesta del  backend ha expirado',
            'content': {
                'application/json': {
                    'schema': {'$ref': '#/components/schemas/ApiException'},
                    'examples': {
                        'internalServerErrorExample': {'$ref': '#/components/examples/GatewayTimeoutExample'},
                    },
                },
            },
        },
    },
    'examples': {
        'InternalServerErrorExample': {
            'summary': 'Error interno',
            'value': {
                'code': 'ER0006',
                'description': 'Error interno del servidor',
                'errorType': 'Technical',
                'errorDetail': [
                    {
                        'code': 'TL005',
                        'description': 'Fallo en servicio backend',
                        'path': 'backend.service',
                        'url': 'http://documentacion-to-fix-error.com/internal-error',
                    },
                ],
            },
        },
        'GatewayTimeoutExample': {
            'summary': 'Timeout backend',
            'value': {
                'code': 'ER0007',
                'description': 'Tiempo de espera excedido',
                'errorType': 'Technical',
                'errorDetail': [
                    {
                        'code': 'TL0006',
                        'description': 'Timeout en integracion externa',
                        'path': 'backend.timeout',
                        'url': 'http://documentacion-to-fix-error.com/internal-error',
                    },
                ],
            },
        },
    },
    'schemas': {
        'Code': {
            'type': 'string',
            'title': 'Code',
            'description': 'Codigo de error de alto, nivel, es el 2do nivel de detalle de un error, se basa en el http code devuelto.El formato es ERXXXX, donde XXXX es el numero de error.',
            'maxLength': 6,
            'example': 'ER0007',
        },
        'ErrorType': {
            'type': 'string',
            'title': 'ErrorType',
            'enum': ['Functional', 'Technical'],
            'description': (
                'Tipo de error:\n'
                '- Functional - Error devuelto por una validacion o regla de \n'
                'negocio no superada\n'
                '- Techical - Error devuelto por la herramienta o sistema,\n'
                'generalmente causado por problemas tecnicos o dependencias externas.\n'
            ),
            'example': 'Functional',
        },
        'Description': {
            'type': 'string',
            'title': 'Description',
            'description': 'Descripcion del mensaje de error, alto nivel.',
            'maxLength': 500,
            'example': 'Error al llamar al servicio',
        },
        'Path': {
            'type': 'string',
            'title': 'Path',
            'maxLength': 200,
            'description': 'Referencia al path del Json involucrado en el error, aqui se indica que objecto del request, response o parametro de consulta es el involucrado con el error',
            'example': 'Party.partyIdentification.IdentifierValue',
        },
        'Url': {
            'type': 'string',
            'title': 'Url',
            'maxLength': 200,
            'description': 'Ubicacion de la documentacion para soporte del problema.',
            'example': 'https://documentation-to-fix-error.com/como-consultar-datos-usuario-info',
        },
        'ApiExceptionDetail': {
            'type': 'object',
            'title': 'ApiExceptionDetail',
            'description': 'Contiene la lista de detalles para mayor detalle del error originado',
            'example': {
                'code': 'TL0001',
                'description': 'Error al llamar al servicio',
                'path': 'Party.partyIdentification.IdentifierValue',
                'url': 'https://documentacion-to-fix-error.com/como-consultar-datos-usuario-info',
            },
            'properties': {
                'code': {'$ref': '#/components/schemas/Code'},
                'description': {'$ref': '#/components/schemas/Description'},
                'path': {'$ref': '#/components/schemas/Path'},
                'url': {'$ref': '#/components/schemas/Url'},
                'errorDetail': {
                    'type': 'array',
                    'description': 'Contiene la lista de detalles para mayor detalle del error originado',
                    'items': {'$ref': '#/components/schemas/ApiExceptionDetail'},
                },
            },
        },
        'ApiException': {
            'type': 'object',
            'title': 'ApiException',
            'description': 'El servicio no recibio una respuesta oportuna de la aplicacion',
            'example': {
                'code': 'ER0007',
                'description': 'Error al llamar al servicio',
                'errorType': 'Functional',
                'exceptionalDetails': [
                    {
                        'code': 'TL001',
                        'description': 'Error al llamar al servicio',
                        'path': 'Party.part',
                        'url': 'https://documentation-to-fix-error.com/como-consultar-datos-usuario-info',
                    },
                ],
            },
            'properties': {
                'code': {'$ref': '#/components/schemas/Code'},
                'errorType': {'$ref': '#/components/schemas/ErrorType'},
                'description': {'$ref': '#/components/schemas/Description'},
                'errorDetail': {
                    'type': 'array',
                    'description': 'Contiene la lista de detalles para mayor detalle del error originado',
                    'items': {'$ref': '#/components/schemas/ApiExceptionDetail'},
                },
            },
        },
    },
}

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


def texto_o_vacio(valor) -> str:
    """Convierte una celda del Excel a texto, tratando celdas vacias (NaN) como '' en
    vez de la cadena literal 'nan' que produce str() sobre un float NaN de pandas."""
    if pd.isna(valor):
        return ''
    return str(valor).strip()


def escalar_yaml(texto: str) -> str:
    """Escapa un valor para insertarlo como scalar plano de una linea en YAML.

    Las plantillas usan placeholders sin comillas como '[NOMBRE-CONTROLADOR]', que no
    son YAML valido (se interpretan como flow sequence). Por eso los archivos no se
    pueden parsear completos con yaml.safe_load y las sustituciones se hacen sobre texto.
    """
    if re.search(r'[:#{}\[\],&*!|>\'"%@`\n]', texto) or texto != texto.strip():
        escapado = texto.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escapado}"'
    return texto


def operation_id(accion: str, endpoint: str) -> str:
    piezas = [p.capitalize() for p in re.split(r'[\/\-_.\s{}]+', endpoint) if p]
    return accion + ''.join(piezas)


def slug(texto: str) -> str:
    return texto.strip().lower().replace(' ', '-')


def reemplazar_info(contenido: str, title: str, version: str) -> str:
    title_esc = escalar_yaml(title)
    contenido, n_title = re.subn(r'(?m)^(\s*title:\s*).*$', lambda m: m.group(1) + title_esc, contenido, count=1)
    contenido, n_version = re.subn(r'(?m)^(\s*version:\s*).*$', lambda m: m.group(1) + version, contenido, count=1)
    if not n_title or not n_version:
        raise ValueError("No se encontraron las claves 'title'/'version' bajo 'info' en la plantilla.")
    return contenido


def reemplazar_clave_simple(contenido: str, clave: str, valor: str) -> str:
    valor_esc = escalar_yaml(valor)
    patron = re.compile(rf'(?m)^(\s*{re.escape(clave)}:\s*).*$')
    nuevo, n = patron.subn(lambda m: m.group(1) + valor_esc, contenido, count=1)
    if not n:
        raise ValueError(f"No se encontro la clave '{clave}' en la plantilla.")
    return nuevo


def encontrar_bloque(lineas: list, clave: str):
    """Ubica una clave 'clave:' (a cualquier nivel de indentacion) y el rango de lineas
    de su bloque hijo, comparando indentacion en vez de asumir que es una clave raiz o
    que su contenido llega hasta el final del archivo."""
    patron = re.compile(rf'^(\s*){re.escape(clave)}:\s*$')
    for i, linea in enumerate(lineas):
        m = patron.match(linea)
        if not m:
            continue
        indent = len(m.group(1))
        fin = i + 1
        for j in range(i + 1, len(lineas)):
            siguiente = lineas[j]
            if siguiente.strip() == '':
                fin = j + 1
                continue
            indent_siguiente = len(siguiente) - len(siguiente.lstrip(' \t'))
            if indent_siguiente > indent:
                fin = j + 1
                continue
            break
        return i, fin, indent
    return None


def encontrar_hijo_directo(lineas: list, inicio: int, fin: int, indent_esperado: int, clave: str):
    """Busca 'clave' dentro de [inicio, fin) exigiendo que este exactamente al nivel
    'indent_esperado'. No basta con acotar el rango de lineas porque una clave como
    'examples' o 'responses' puede repetirse anidada mas profundo con otro significado
    (ej. 'components.responses.X.content.application/json.examples' vs
    'components.examples'); exigir la indentacion exacta evita confundirlas."""
    patron = re.compile(rf'^(\s*){re.escape(clave)}:\s*$')
    for i in range(inicio, fin):
        m = patron.match(lineas[i])
        if not m or len(m.group(1)) != indent_esperado:
            continue
        f = i + 1
        for j in range(i + 1, fin):
            siguiente = lineas[j]
            if siguiente.strip() == '':
                f = j + 1
                continue
            indent_siguiente = len(siguiente) - len(siguiente.lstrip(' \t'))
            if indent_siguiente > indent_esperado:
                f = j + 1
                continue
            break
        return i, f
    return None


def agregar_o_actualizar_hijo(contenido: str, padre: str, clave: str, datos: dict) -> str:
    """Agrega 'clave' como hija directa de 'padre' (ej. 'responses' bajo 'components'), o
    regenera su bloque si ya existe. Exige que 'clave' este al nivel de indentacion
    inmediato de 'padre' para no confundirla con una clave homonima anidada mas profundo."""
    lineas = contenido.split('\n')
    bloque_padre = encontrar_bloque(lineas, padre)
    if not bloque_padre:
        raise ValueError(f"No se encontro la clave '{padre}' en la plantilla.")
    inicio_padre, fin_padre, indent_padre = bloque_padre

    indent_clave = indent_padre + 2
    prefijo_nietos = ' ' * (indent_clave + 2)
    fragmento = yaml.safe_dump(datos, sort_keys=False, allow_unicode=True, default_flow_style=False)
    cuerpo = [prefijo_nietos + linea if linea else linea for linea in fragmento.splitlines()]
    bloque_nuevo = [f"{' ' * indent_clave}{clave}:"] + cuerpo

    bloque_hijo = encontrar_hijo_directo(lineas, inicio_padre + 1, fin_padre, indent_clave, clave)
    if bloque_hijo:
        inicio_hijo, fin_hijo = bloque_hijo
        nuevas = lineas[:inicio_hijo] + bloque_nuevo + lineas[fin_hijo:]
    else:
        nuevas = lineas[:fin_padre] + bloque_nuevo + lineas[fin_padre:]
    return '\n'.join(nuevas)


def asegurar_clave_raiz(contenido: str, clave: str) -> str:
    """Garantiza que 'clave' exista como clave raiz (indent 0), agregandola vacia al
    final del archivo si no esta presente. La plantilla base REST no trae 'components',
    a diferencia de la de AsyncAPI que ya trae 'messageTraits' bajo ese nodo."""
    lineas = contenido.split('\n')
    if encontrar_bloque(lineas, clave):
        return contenido
    while lineas and lineas[-1].strip() == '':
        lineas.pop()
    lineas.append(f'{clave}:')
    return '\n'.join(lineas)


def agregar_componentes_error(contenido: str) -> str:
    """Agrega bajo 'components' las respuestas/ejemplos/schemas estandar de error, para
    que las operaciones puedan referenciar '500'/'504' contra un contrato comun."""
    contenido = asegurar_clave_raiz(contenido, 'components')
    contenido = agregar_o_actualizar_hijo(contenido, 'components', 'responses', COMPONENTES_ERROR['responses'])
    contenido = agregar_o_actualizar_hijo(contenido, 'components', 'examples', COMPONENTES_ERROR['examples'])
    contenido = agregar_o_actualizar_hijo(contenido, 'components', 'schemas', COMPONENTES_ERROR['schemas'])
    return contenido


def reemplazar_bloque_indentado(contenido: str, clave: str, datos: dict, vacio: str = '{}') -> str:
    """Regenera por completo el bloque hijo de 'clave' a partir de un dict, sin importar
    su indentacion ni si tiene contenido despues (a diferencia de 'paths' en la plantilla
    REST, 'channels'/'messages' en la de AsyncAPI no quedan al final del archivo).

    Regenerar desde el dict (en vez de duplicar texto ya existente en el archivo) es lo
    que hace esto idempotente ante reruns del workflow (ej. push adicional al PR).
    """
    lineas = contenido.split('\n')
    encontrado = encontrar_bloque(lineas, clave)
    if not encontrado:
        raise ValueError(f"No se encontro la clave '{clave}' en la plantilla.")
    inicio, fin, indent = encontrado
    prefijo_hijo = ' ' * (indent + 2)
    if datos:
        fragmento = yaml.safe_dump(datos, sort_keys=False, allow_unicode=True, default_flow_style=False)
        cuerpo = [prefijo_hijo + linea if linea else linea for linea in fragmento.splitlines()]
    else:
        cuerpo = [prefijo_hijo + vacio]
    nuevas = lineas[:inicio] + [f"{' ' * indent}{clave}:"] + cuerpo + lineas[fin:]
    return '\n'.join(nuevas)


# --- REST / OpenAPI -----------------------------------------------------

SERVER_URL_POR_TIPO = {
    'UX': '/channel-{app_code}-{contexto}/v1',
    'BS': '/business-{contexto}/v1',
    'CR': '/core-{contexto}/v1',
    'DATA': '/data-{contexto}/v1',
    'PU': '/public-{contexto}/v1',
    'PV': '/private-{app_code}-{contexto}/v1',
    'OP': '/open-{contexto}/v1',
}


def construir_server_url(api_type: str, owner: str, tag: str) -> str:
    plantilla_url = SERVER_URL_POR_TIPO.get(api_type.strip().upper())
    if not plantilla_url:
        raise ValueError(f"No hay una regla de URL de servidor definida para el tipo '{api_type}'.")
    return plantilla_url.format(app_code=slug(owner), contexto=slug(tag))


def reemplazar_url_servidor(contenido: str, url: str) -> str:
    url_esc = escalar_yaml(url)
    patron = re.compile(r'(?m)^(\s*-\s*url:\s*).*$')
    nuevo, n = patron.subn(lambda m: m.group(1) + url_esc, contenido, count=1)
    if not n:
        raise ValueError("No se encontro la clave 'url' bajo 'servers' en la plantilla.")
    return nuevo


def construir_parametros_header(api_type: str) -> list:
    headers = HEADERS_REQUERIDOS_POR_TIPO.get(api_type.strip().upper(), [])
    return [
        {'name': header, 'in': 'header', 'required': True, 'schema': {'type': 'string'}}
        for header in headers
    ]


def construir_paths(filas, tag, api_type) -> dict:
    paths = {}
    for _, fila in filas.iterrows():
        endpoint = str(fila['Endpoint']).strip()
        metodo = str(fila['Metodo']).strip().lower()
        descripcion = texto_o_vacio(fila['Descripcion del Endpoint'])
        if not endpoint or not metodo:
            continue
        operacion = {
            'tags': [tag],
            'summary': descripcion,
        }
        parametros = construir_parametros_header(api_type)
        if parametros:
            operacion['parameters'] = parametros
        operacion['responses'] = {
            '200': {'description': 'OK'},
            '500': {'$ref': '#/components/responses/InternalServerError'},
            '504': {'$ref': '#/components/responses/GatewayTimeout'},
        }
        paths.setdefault(endpoint, {})[metodo] = operacion
    return paths


def reemplazar_tags_rest(contenido: str, tag: str) -> str:
    tag_esc = escalar_yaml(tag)
    descripcion_esc = escalar_yaml(f'{tag} Controller')
    patron = re.compile(r'(?m)^tags:\n(\s*-\s*name:\s*).*\n(\s*description:\s*).*$')
    nuevo, n = patron.subn(lambda m: f"tags:\n{m.group(1)}{tag_esc}\n{m.group(2)}{descripcion_esc}", contenido, count=1)
    if not n:
        raise ValueError("No se encontro el bloque 'tags' en la plantilla REST.")
    return nuevo


def procesar_rest(contenido: str, api_name: str, tag: str, grupo) -> str:
    api_type = str(grupo.iloc[0]['Tipo']).strip()
    owner = str(grupo.iloc[0]['Owner']).strip()

    nuevo = reemplazar_info(contenido, api_name, '1.0.0')
    nuevo = reemplazar_tags_rest(nuevo, tag)
    nuevo = reemplazar_clave_simple(nuevo, 'x-bcp-api-type', api_type)
    nuevo = reemplazar_clave_simple(nuevo, 'x-bcp-api-id', slug(tag))
    nuevo = reemplazar_url_servidor(nuevo, construir_server_url(api_type, owner, tag))
    nuevo = reemplazar_bloque_indentado(nuevo, 'paths', construir_paths(grupo, tag, api_type))
    nuevo = agregar_componentes_error(nuevo)
    return nuevo


# --- Event-Driven / AsyncAPI ---------------------------------------------

def extraer_topic(endpoint: str) -> str:
    """El Excel trae el Endpoint como 'topic: nombre_topico'; nos quedamos solo con el nombre."""
    match = re.match(r'(?i)^\s*topic\s*:\s*(.+)$', endpoint)
    return match.group(1).strip() if match else endpoint.strip()


def construir_channels(filas, tag) -> dict:
    channels = {}
    for _, fila in filas.iterrows():
        topic = extraer_topic(str(fila['Endpoint']))
        metodo = str(fila['Metodo']).strip().lower()
        descripcion = texto_o_vacio(fila['Descripcion del Endpoint'])
        if not topic or not metodo:
            continue
        operacion = METODO_A_OPERACION_ASYNC.get(metodo)
        if not operacion:
            logging.warning(f"Metodo '{metodo}' no reconocido para el topic '{topic}' (se esperaba Send/Receive). Fila omitida.")
            continue
        canal = channels.setdefault(topic, {'description': descripcion})
        canal[operacion] = {
            'operationId': operation_id(operacion, topic),
            'description': descripcion,
            'message': {'$ref': f'#/components/messages/{topic}'},
        }
    return channels


def construir_mensaje(topic: str, owner: str) -> dict:
    """Replica la entrada de ejemplo 'messageName' de la plantilla, una por topic,
    sustituyendo CODEAPP (Owner del Excel) y TOPIC-NAME-VALUE (topic + '-value')."""
    value_name = f'{topic}-value'
    return {
        'name': topic,
        'title': 'Message title (Evento)',
        'contentType': 'avro/binary',
        'schemaFormat': 'application/vnd.apache.avro;version=1.9.0',
        'summary': 'Summary',
        'traits': [{'$ref': '#/components/messageTraits/commonHeaders'}],
        'payload': {'$ref': f'../schema/{owner}/{value_name}.avsc'},
        'example': [{
            'name': 'Example name',
            'summary': 'Summary',
            'payload': {'$ref': f'../schemas/{owner}/mocks/{value_name}-example-01.json'},
        }],
    }


def construir_messages(topics, owner: str) -> dict:
    return {topic: construir_mensaje(topic, owner) for topic in topics}


def reemplazar_tags_async(contenido: str, tag: str) -> str:
    tag_esc = escalar_yaml(tag)
    patron = re.compile(r'(?m)^tags:\n(\s*-\s*name:\s*).*$')
    nuevo, n = patron.subn(lambda m: f"tags:\n{m.group(1)}{tag_esc}", contenido, count=1)
    if not n:
        raise ValueError("No se encontro el bloque 'tags' en la plantilla AsyncAPI.")
    return nuevo


def procesar_event_driven(contenido: str, api_name: str, tag: str, grupo) -> str:
    owner = str(grupo.iloc[0]['Owner']).strip()
    channels = construir_channels(grupo, tag)

    nuevo = reemplazar_info(contenido, api_name, '1.0.0')
    nuevo = reemplazar_tags_async(nuevo, tag)
    nuevo = reemplazar_bloque_indentado(nuevo, 'channels', channels)
    nuevo = reemplazar_bloque_indentado(nuevo, 'messages', construir_messages(channels.keys(), owner))
    return nuevo


# --- GitHub Contents API --------------------------------------------------

def obtener_archivo(repo, path):
    url = f"https://api.github.com/repos/{ORG}/{repo}/contents/{path}"
    for intento in range(3):
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            try:
                data = response.json()
            except ValueError:
                logging.error(
                    f"Respuesta 200 con cuerpo no-JSON al obtener '{path}' en '{repo}'. "
                    f"Content-Type: {response.headers.get('Content-Type')}. "
                    f"Cuerpo (primeros 500 chars): {response.text[:500]!r}"
                )
                if intento < 2:
                    time.sleep(5)
                    continue
                return None, None
            contenido = base64.b64decode(data['content']).decode('utf-8')
            contenido = contenido.replace('\r\n', '\n').replace('\r', '\n')
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
    logging.info(f"Especificacion de API creada en '{repo}/{path}'.")
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
        estilo = str(grupo.iloc[0]['Estilo']).strip().lower()

        contenido, sha = obtener_archivo(repo, SPEC_SOURCE_PATH)
        if contenido is None:
            continue

        try:
            if estilo == 'rest':
                nuevo_contenido = procesar_rest(contenido, str(api_name).strip(), tag, grupo)
            elif estilo == 'event-driven':
                nuevo_contenido = procesar_event_driven(contenido, str(api_name).strip(), tag, grupo)
            else:
                logging.warning(f"Estilo '{estilo}' no soportado para '{repo}'. Se omite.")
                continue
        except ValueError as error:
            logging.error(f"No se pudo actualizar la especificacion de '{repo}': {error}")
            continue

        if not crear_archivo(repo, destino, nuevo_contenido, f"chore: crear especificacion de API {destino}"):
            continue

        eliminar_archivo(repo, SPEC_SOURCE_PATH, sha, f"chore: eliminar plantilla {SPEC_SOURCE_PATH}")


if __name__ == '__main__':
    main()
