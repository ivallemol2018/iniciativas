import argparse
import os
import re
import sys
import panda as pd
import requests
import unicodedata

MAX_FILE_SIZE_KB = 50
VALID_ESTILOS = ['REST', 'Event-Drive', 'GraphQL', 'PQL']
VALID_TIPOS = ['UX', 'BS', 'CR', 'DT', 'PU', 'PV', 'OP', 'Async', 'Subgraph', 'Graph', 'Operation']
EXPECTED_COLUMNS = [
    'API',
    'Estilo',
    'Tipo',
    'Owner',
    'Metodo',
    'Endpoint',
    'Descripcion del Endpoint'
]
METODO_RULES = {
    'REST': ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'],
    'EVENT-DRIVEN': ['Receive', 'Send'],
    'GRAPHQL': ['Query', 'Mutation', 'Subscription']
}
OWNER_API_ERROR_MSG = (
    "El valor en la columna 'API' ('{api}') no cumple el formato requerido para {contexto} "
    "o el código de 4 caracteres no corresponde al valor de la columna 'Owner' ('{owner}')."
)
API_FORMAT_ERROR_MSG = (
    "El valor en la columna 'API' ('{api}') no cumple el formato requerido para {contexto}."
)

CONFLUENCE_TEMPLATE_URL = "https://bcp-ti.atlassian.net/wiki/x/JAJzIg"


def normalizar(texto):
    texto = str(texto).strip().lower()
    texto = unicodedata.normalize('NFKD', texto)
    return ''.join([c for c in texto if not unicodedata.combining(c)])



def limpiar_metodo(metodo):
    # Convierte a string, elimina espacios y caracteres invisibles, y convierte a mayúsculas
    texto = str(metodo or '').strip()
    # Elimina cualquier carácter Unicode no imprimible excepto letras y dígitos
    texto = re.sub(r'[^A-Za-z0-9]', '', texto)
    return texto.upper()


def comentar_pr(owner, repo, pr_number, token, mensaje):
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
    headers = {'Authorization': f'token {token}'}
    data = {'body': mensaje}
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    print("[LOG] Comentario publicado en el PR.")


def validate_estilo(value):
    val = str(value).strip().upper()
    print(f"[LOG] Validando Estilo normalizado: '{val}'")
    return val in [v.upper() for v in VALID_ESTILOS]


def validate_tipo(value):
    val = str(value).strip().upper()
    return val in [v.upper() for v in VALID_TIPOS]


def validate_owner(value):
    return bool(re.fullmatch(r'[A-Za-z0-9]{4}', str(value).strip()))


def validate_api(row, styles_to_validate):
    estilo = str(row.get('Estilo', '')).strip()
    tipo = str(row.get('Tipo', '')).strip()
    owner = str(row.get('Owner', '')).strip()
    api = str(row.get('API', '')).strip()
    metodo = str(row.get('Metodo', '')).strip() if 'Metodo' in row else ''

    estilo_norm = estilo.upper()
    tipo_norm = tipo.upper()
    metodo_norm = metodo.capitalize()

    if estilo_norm in styles_to_validate:
        if estilo_norm == 'REST':
            if tipo_norm == 'UX':
                return True if re.match(rf'^API UX {owner} .+', api) else OWNER_API_ERROR_MSG.format(api=api, contexto="UX", owner=owner)
            elif tipo_norm == 'PV':
                return True if re.match(rf'^API PV {owner} .+', api) else OWNER_API_ERROR_MSG.format(api=api, contexto="PV", owner=owner)
            elif tipo_norm == 'PU':
                return True if re.match(r'^API .+', api) else API_FORMAT_ERROR_MSG.format(api=api, contexto="PU")
            elif tipo_norm == 'BS':
                return True if re.match(r'^API BS .+', api) else API_FORMAT_ERROR_MSG.format(api=api, contexto="BS")
            elif tipo_norm == 'CR':
                return True if re.match(r'^API CR .+', api) else API_FORMAT_ERROR_MSG.format(api=api, contexto="CR")
            elif tipo_norm == 'DT':
                return True if re.match(r'^API DT .+', api) else API_FORMAT_ERROR_MSG.format(api=api, contexto="DT")
            elif tipo_norm == 'OP':
                return True if re.match(r'^API .+', api) else API_FORMAT_ERROR_MSG.format(api=api, contexto="OP")
        elif estilo_norm == 'EVENT-DRIVEN':
            if tipo_norm == 'ASYNC':
                return True if re.match(r'^AsyncAPI .+', api) else API_FORMAT_ERROR_MSG.format(api=api, contexto="Async")
        elif estilo_norm == 'GRAPHQL':
            if tipo_norm == 'SUBGRAPH':
                return True if re.match(r'^API Subgraph .+', api) else API_FORMAT_ERROR_MSG.format(api=api, contexto="Subgraph")
            elif tipo_norm == 'GRAPH':
                return True if re.match(r'^API Graph .+', api) else API_FORMAT_ERROR_MSG.format(api=api, contexto="Graph")
        elif estilo_norm == 'PQL':
            if tipo_norm == 'OPERATION':
                if metodo_norm == 'Query':
                    return True if re.match(rf'^Query {owner} .+', api) else OWNER_API_ERROR_MSG.format(api=api, contexto="Query", owner=owner)
                elif metodo_norm == 'Mutation':
                    return True if re.match(rf'^Mutation {owner} .+', api) else OWNER_API_ERROR_MSG.format(api=api, contexto="Mutation", owner=owner)
                elif metodo_norm == 'Subscription':
                    return True if re.match(rf'^Subscription {owner} .+', api) else OWNER_API_ERROR_MSG.format(api=api, contexto="Subscription", owner=owner)
    return True


def validate_metodo(estilo, metodo):
    estilo_norm = str(estilo).strip().upper()
    metodo_norm = limpiar_metodo(metodo)
    if estilo_norm in METODO_RULES:
        valid_metodos = [limpiar_metodo(m) for m in METODO_RULES[estilo_norm]]
        if metodo_norm not in valid_metodos:
            return f"Valor inválido en columna 'Metodo': '{metodo_norm}'. Para Estilo '{estilo_norm}' los valores permitidos son: {', '.join(valid_metodos)}."
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', required=True, help='Archivo Excel a validar')
    parser.add_argument('--validate_styles', default='REST', help='Lista de estilos a validar separados por coma')
    args = parser.parse_args()

    file_path = args.file
    github_env = os.getenv('GITHUB_ENV', '/github/env')
    with open(github_env, 'a') as env_file:
        env_file.write(f'FILE_PATH={file_path}\n')
    print(f"[LOG] Variable de entorno FILE_PATH exportada a GITHUB_ENV: {file_path}")

    styles_to_validate = [s.strip().upper() for s in args.validate_styles.split(',')]

    owner = os.getenv('GITHUB_OWNER')
    repo = os.getenv('GITHUB_REPO')
    pr_number = os.getenv('PR_NUMBER')
    token = os.getenv('GITHUB_TOKEN')
    workflow_url = os.getenv('WORKFLOW_RUN_URL')

    if not all([owner, repo, pr_number, token]):
        print("[ERROR] Faltan variables de entorno necesarias.")
        sys.exit(1)

    file_size_kb = os.path.getsize(file_path) / 1024
    print(f"[LOG] Peso del archivo Excel: {file_size_kb:.0f} KB")
    if file_size_kb > MAX_FILE_SIZE_KB:
        error_msg = (
            f"❌ El archivo Excel pesa {file_size_kb:.0f} KB, lo cual excede el límite máximo permitido de {MAX_FILE_SIZE_KB} KB."
        )
        comentar_pr(owner, repo, pr_number, token, error_msg)
        print("[ERROR] El archivo Excel excede el peso permitido.")
        sys.exit(1)

    try:
        df = pd.read_excel(file_path, engine='openpyxl')
    except Exception as e:
        print(f"[ERROR] No se pudo leer el archivo Excel: {e}")
        sys.exit(1)

    # --- Validación de cabecera (orden y equivalencia normalizada de las 7 primeras columnas)
    actual_columns = [str(col) for col in df.columns]
    expected_len = len(EXPECTED_COLUMNS)
    expected_normalized = [normalizar(col) for col in EXPECTED_COLUMNS]
    actual_normalized = [normalizar(col) for col in actual_columns[:expected_len]]

    if actual_normalized != expected_normalized:
        error_msg = (
            "❌ El archivo Excel no tiene la cabecera esperada o el orden de las columnas es incorrecto.\n\n"
            f"- Se esperaban las primeras {expected_len} columnas con los siguientes nombres y orden:\n"
            f" {', '.join(EXPECTED_COLUMNS)}\n"
            f"- Se encontraron las primeras {expected_len} columnas con los nombres:\n"
            f" {', '.join(actual_columns[:expected_len])}\n\n"
            "\n\n⚠️ Debido a estos errores, el Pull Request será cerrado automáticamente."
            "\n\n📝 Por favor, corrige los errores en el archivo Excel y crea un nuevo Pull Request con el archivo corregido."
            f"\n\n📘 Si necesitas conocer el manual de como llenar el Excel o descargar una plantilla ejemplo, ve al siguiente enlace {CONFLUENCE_TEMPLATE_URL}"
        )
        comentar_pr(owner, repo, pr_number, token, error_msg)
        print("[ERROR] Cabecera del archivo Excel inválida o columnas fuera de orden.")
        sys.exit(1)

    # --- NUEVO: Estandarizar los nombres de las primeras 7 columnas a los esperados ---
    # Garantizamos que el resto del código pueda acceder por las claves exactas en EXPECTED_COLUMNS
    df.columns = list(EXPECTED_COLUMNS) + list(actual_columns[expected_len:])
    print(f"[LOG] Columnas estandarizadas (primeras {expected_len}): {list(df.columns)[:expected_len]}")

    errors = []
    for idx, row in df.iterrows():
        row_num = idx + 2  # Considerando que el header es la fila 1
        fila_errores = []

        # Validar que todas las columnas esperadas tengan valor
        for col in EXPECTED_COLUMNS:
            valor = str(row.get(col, '')).strip()
            if valor == '':
                fila_errores.append(f"Valor vacío en columna '{col}'.")

        estilo = str(row.get('Estilo', '')).strip()
        tipo = str(row.get('Tipo', '')).strip()
        owner_val = str(row.get('Owner', '')).strip()
        api_val = str(row.get('API', '')).strip()
        metodo_val = str(row.get('Metodo', '')).strip() if 'Metodo' in row else ''
        endpoint_val = str(row.get('Endpoint', '')).strip()
        descripcion_val = str(row.get('Descripcion del Endpoint', '')).strip()

        print(f"[LOG] Fila {row_num} leída: Estilo='{estilo}', Tipo='{tipo}', Owner='{owner_val}', API='{api_val}', Metodo='{metodo_val}'")

        # Validar SIEMPRE Estilo, Tipo y Owner
        if not validate_estilo(estilo):
            fila_errores.append(f"Valor inválido en columna 'Estilo': '{estilo}'. Valores permitidos: {', '.join(VALID_ESTILOS)}.")
        if not validate_tipo(tipo):
            fila_errores.append(f"Valor inválido en columna 'Tipo': '{tipo}'. Valores permitidos: {', '.join(VALID_TIPOS)}.")
        if not validate_owner(owner_val):
            fila_errores.append(f"Valor inválido en columna 'Owner': '{owner_val}'. Debe ser una palabra de 4 caracteres alfanuméricos.")

        # Validar Metodo según Estilo
        metodo_error = validate_metodo(estilo, metodo_val)
        if metodo_error:
            fila_errores.append(metodo_error)

        # Solo validar API si NO hubo errores anteriores en la fila
        if not fila_errores:
            api_validation = validate_api(row, styles_to_validate)
            if api_validation is not True:
                fila_errores.append(api_validation if isinstance(api_validation, str) else API_FORMAT_ERROR_MSG.format(api=api_val, contexto=f"Estilo {estilo}"))

        # Validaciones adicionales para API
        if api_val != '':
            # No debe contener espacios al final
            if re.search(r'\s$', str(row.get('API', ''))):
                fila_errores.append("El valor en la columna 'API' no debe contener espacios al final.")
            # No debe contener caracteres especiales (solo letras, números y espacios)
            if re.search(r'[^A-Za-z0-9 ]', api_val):
                fila_errores.append("El valor en la columna 'API' no debe contener caracteres especiales. Solo se permiten letras, números y espacios.")
            # Sufijo V[1-9][0-9]* solo para REST y Event-Driven
            estilo_norm = estilo.strip().upper()
            if estilo_norm in ['REST', 'EVENT-DRIVEN']:
                if not re.search(r'V[1-9][0-9]*$', api_val):
                    fila_errores.append("El valor en la columna 'API' debe terminar con 'V' seguido de un número entero mayor o igual a 1. Ejemplo válido: 'API BS Clientes V1'.")

        for err in fila_errores:
            print(f"[ERROR] Fila {row_num}: {err}")  # Log detallado por error de validación
            errors.append((row_num, err))

    if errors:
        comment = f"### ❌ Errores encontrados en la validación del archivo Excel:\n\n"
        comment += f"📄 **Archivo validado:** {os.path.basename(file_path)}\n\n"
        comment += "| Fila | Descripción del error |\n"
        comment += "|------|-----------------------|\n"
        for fila, desc in errors:
            comment += f"| {fila} | {desc} |\n"
        comment += (
            "\n⚠️ Debido a estos errores, **el Pull Request será cerrado automáticamente**."
            "\n\n📝 Por favor, corrige los errores en el archivo Excel y **crea un nuevo Pull Request con el archivo corregido**."
            f"\n\n📘 Si necesitas conocer el manual de como llenar el Excel o descargar una plantilla ejemplo, ve al siguiente enlace {CONFLUENCE_TEMPLATE_URL}"
        )
        if workflow_url:
            comment += f"\n\n🔗 Si deseas, puedes revisar los detalles de la ejecución del workflow en el siguiente enlace: {workflow_url}"
        comentar_pr(owner, repo, pr_number, token, comment)
        print("[ERROR] Se encontraron errores en la validación del Excel.")
        sys.exit(1)
    else:
        comment = f"✅ Validación del archivo Excel completada sin errores.\n\n"
        comment += f"📄 **Archivo validado:** {os.path.basename(file_path)}"
        print("[LOG] Validación completada sin errores.")


if __name__ == "__main__":
    main()
