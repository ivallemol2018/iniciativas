"""Valida que los endpoints de las APIs BIAN del Excel existan en su plantilla BIAN.

Una API BIAN es una API BS de estilo REST que pertenece a un Service Domain. Para saber
si un endpoint esta en la plantilla se usa la misma logica que al generar el contrato
('update_spec_api'), asi validacion y generacion deciden siempre igual.
Ver docs/plan_validacion_endpoints_bian.md.
"""
import argparse
import logging
import os
import sys

import pandas as pd

import update_spec_api as spec
from validate_excel import CONFLUENCE_TEMPLATE_URL, EXPECTED_COLUMNS, comentar_pr


def leer_excel(file_path: str):
    """Excel con las 7 primeras columnas renombradas a EXPECTED_COLUMNS, como en
    'validate_excel.py' (que ya valido la cabecera)."""
    df = pd.read_excel(file_path, engine='openpyxl')
    columnas = [str(c) for c in df.columns]
    df.columns = list(EXPECTED_COLUMNS) + columnas[len(EXPECTED_COLUMNS):]
    return df


def validar_endpoints_bian(df, service_domains: list, cache: dict) -> tuple:
    """(errores, avisos) de las APIs BIAN del Excel. Cada error es un dict con 'fila',
    'api', 'service_domain', 'metodo', 'endpoint' y 'observacion'; cada aviso, un texto."""
    errores, avisos = [], []
    for api_name, grupo in df.groupby('API', sort=False):
        api_name = str(api_name).strip()
        api_type = spec.texto_o_vacio(grupo.iloc[0]['Tipo'])
        estilo = spec.texto_o_vacio(grupo.iloc[0]['Estilo']).lower()
        sd = spec.identificar_service_domain(api_name, api_type, service_domains)
        if not sd or estilo != 'rest':
            continue
        logging.info(f"Validando endpoints de '{api_name}' contra la plantilla BIAN de '{sd}'.")

        texto = spec.obtener_contrato_service_domain(sd, service_domains, cache)
        if texto is None:
            avisos.append(f"{api_name} (Service Domain {sd}): no se encontró la plantilla BIAN; "
                          "se generará con la plantilla genérica.")
            continue
        ruta = cache.get('rutas', {}).get(sd) or sd
        try:
            faltantes = spec.endpoints_faltantes_en_contrato(texto, grupo)
        except ValueError as error:
            avisos.append(f"{api_name} (Service Domain {sd}): la plantilla BIAN `{ruta}` no es válida ({error}); "
                          "se generará con la plantilla genérica.")
            continue

        for f in faltantes:
            if f['similar']:
                observacion = (f"La plantilla tiene `{f['metodo'].upper()} {f['similar']}`: "
                               "revise el nombre del path param")
            else:
                observacion = f"No existe en `{ruta}`"
            errores.append({'fila': f['indice'] + 2, 'api': api_name, 'service_domain': sd,
                            'metodo': f['metodo'].upper(), 'endpoint': f['endpoint'], 'observacion': observacion})

        con_endpoint = sum(1 for _, fila in grupo.iterrows()
                           if spec.texto_o_vacio(fila['Endpoint']) and spec.texto_o_vacio(fila['Metodo']))
        if faltantes and len(faltantes) == con_endpoint:
            avisos.append(f"{api_name} (Service Domain {sd}): ningún endpoint está en la plantilla BIAN; "
                          "se generará con la plantilla genérica.")
    return errores, avisos


def _celda(texto: str) -> str:
    return str(texto).replace('|', '\\|')


def construir_comentario(file_path: str, errores: list, avisos: list, modo: str, workflow_url: str | None) -> str:
    if errores:
        comentario = "### ❌ Endpoints no encontrados en la plantilla BIAN\n\n"
    else:
        comentario = "### ⚠️ Validación de endpoints BIAN\n\n"
    comentario += (f"📄 **Archivo validado:** {os.path.basename(file_path)} · "
                   f"🔎 Comparación de path params: `{modo}`\n\n")
    if errores:
        comentario += "| Fila | API | Service Domain | Método | Endpoint | Observación |\n"
        comentario += "|------|-----|----------------|--------|----------|-------------|\n"
        for e in errores:
            comentario += (f"| {e['fila']} | {_celda(e['api'])} | {_celda(e['service_domain'])} | {e['metodo']} "
                           f"| {_celda(e['endpoint'])} | {_celda(e['observacion'])} |\n")
        comentario += "\n"
    if avisos:
        comentario += "⚠️ **Avisos**\n" + ''.join(f"- {a}\n" for a in avisos) + "\n"
    if errores:
        comentario += ("📝 Corrige los endpoints en el Excel o confirma que deben agregarse a la plantilla BIAN."
                       f"\n\n📘 Manual y plantilla de ejemplo del Excel: {CONFLUENCE_TEMPLATE_URL}")
    if workflow_url:
        comentario += f"\n\n🔗 Detalle de la ejecución del workflow: {workflow_url}"
    return comentario


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', required=True, help='Archivo Excel a validar')
    args = parser.parse_args()

    owner = os.getenv('GITHUB_OWNER')
    repo = os.getenv('GITHUB_REPO')
    pr_number = os.getenv('PR_NUMBER')
    token = os.getenv('GITHUB_TOKEN')
    workflow_url = os.getenv('WORKFLOW_RUN_URL')
    if not all([owner, repo, pr_number, token]):
        logging.error("Faltan variables de entorno necesarias.")
        return 1

    carpetas = spec.carpetas_service_domain(spec.SERVICE_DOMAIN_PATHS)
    service_domains = spec.cargar_service_domains() if spec.SERVICE_DOMAIN_REPO and carpetas else []
    if not service_domains:
        logging.info("Validacion BIAN desactivada: falta el repositorio, las subcarpetas o el listado de Service Domains.")
        return 0

    try:
        df = leer_excel(args.file)
    except Exception as error:
        logging.error(f"No se pudo leer el archivo Excel: {error}")
        return 1

    cache = {'archivos': None, 'contratos': {}, 'carpetas': carpetas, 'rutas': {}}
    errores, avisos = validar_endpoints_bian(df, service_domains, cache)
    for e in errores:
        logging.error(f"Fila {e['fila']}: {e['metodo']} {e['endpoint']} ({e['api']}): {e['observacion']}")
    for a in avisos:
        logging.warning(a)

    if errores or avisos:
        comentar_pr(owner, repo, pr_number, token,
                    construir_comentario(args.file, errores, avisos, spec.MODO_PATH_PARAM, workflow_url))
    if errores:
        logging.error("Hay endpoints de APIs BIAN que no estan en su plantilla BIAN.")
        return 1
    logging.info("Validacion de endpoints BIAN completada sin errores.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
