import base64
import json
import os
import re
import unicodedata
import pandas as pd
import requests
import yaml
from pathlib import Path

from openpyxl.styles import Font, Border, Side, Alignment, PatternFill
from openpyxl.utils import get_column_letter


# ===============================================
# CONFIGURATION
# ===============================================
READMES_JSON_FILE = "readmes.json"
OUTPUT_EXCEL_FILE = "iniciativas_apis.xlsx"
ENDPOINT_FILE_PATTERN = "operation-mapping_*.xlsx"
PRODUCTIVO_FILE = ".github/workflows/data/reporte_api_productivo.xlsx"
SSB_CR_BQ_FILE = ".github/workflows/data/reporte_ssb_cr_bq_interno.xlsx"

# Repositorios git donde viven los contratos OpenAPI "BIAN". Cada entrada se
# escanea completa (todos los .yaml/.yml bajo "dir"), ya que el nombre del
# archivo incluye un sufijo variable (ej. "business-customer-offer-xxxxxxxxxx.yaml").
BIAN_CONTRACT_REPOS = [
    {"repo": "ivallemol2018/bcp-api-template-customer-offer", "dir": "api"},
    {"repo": "ivallemol2018/bpc-api-template-servicing-order", "dir": "api"},
]

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}

FINAL_COLUMNS = [
    "API",
    "Metodo",
    "Endpoint"
]


# ===============================================
# UTILITY FUNCTIONS
# ===============================================
def extract_apis_from_readme(content: str):
    rows = re.findall(
        r"^\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|$",
        content,
        flags=re.MULTILINE,
    )

    rows = [r for r in rows if not all(c.strip().startswith("-") for c in r)]
    if rows:
        rows = rows[1:]

    apis = []
    for r in rows:
        if "test" in r[0].lower():
            continue
        
        apis.append({
            "API": r[0].strip(),
            "Owner": r[1].strip(),
            "Estilo": r[2].strip(),
            "Tipo": r[3].strip(),
            "Exposicion": r[4].strip(),
            "Repositorio": r[5].strip(),
        })

    return apis


def read_endpoints_excel(folder: Path):
    excel_files = list(folder.glob(ENDPOINT_FILE_PATTERN))
    if not excel_files:
        return []

    df = pd.read_excel(excel_files[0], header=0)

    if df.shape[1] < 7:
        return[]

    endpoints = []
    for _, row in df.iterrows():
        endpoints.append({
            "API_KEY": str(row.iloc[0]).strip().upper(),
            "Metodo": row.iloc[4],
            "Endpoint": row.iloc[5],
            "Descripcion del Endpoint": row.iloc[6]
        })

    return endpoints


def normalize_text(value) -> str:
    text = "" if value is None else str(value)
    text = text.strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text


def normalize_endpoint(value) -> str:
    text = normalize_text(value)
    # Reemplaza cualquier path parameter (ej. {id}, {clienteId}) por un comodin generico
    text = re.sub(r"\{[^}]*\}", "{}", text)
    return text


def load_productive_keys(path: str):
    file = Path(path)
    if not file.exists():
        return set()

    df = pd.read_excel(file)

    keys = set()
    for _, row in df.iterrows():
        keys.add((
            normalize_text(row.get("API")),
            normalize_text(row.get("Metodo")),
            normalize_endpoint(row.get("Endpoint")),
        ))

    return keys


def to_kebab_case(value) -> str:
    text = normalize_text(value)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text


def pluralize(value) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        return text

    lower = text.lower()
    if lower.endswith(("s", "x", "z", "ch", "sh")):
        return text + "es"
    if lower.endswith("y") and len(text) > 1 and text[-2].lower() not in "aeiou":
        return text[:-1] + "ies"
    return text + "s"


def extract_path_segments(endpoint) -> list:
    path = "" if endpoint is None else str(endpoint).strip()
    path = path.split("?", 1)[0]
    return [s for s in path.split("/") if s.strip() != ""]


def get_recurso_y_subrecurso(endpoint):
    segments = extract_path_segments(endpoint)
    recurso = segments[0] if segments else ""

    subrecurso = ""
    for seg in segments[1:]:
        if not re.match(r"^\{.*\}$", seg.strip()):
            subrecurso = seg
            break

    return recurso, subrecurso


def load_ssb_cr_bq_df(path: str):
    file = Path(path)
    if not file.exists():
        return pd.DataFrame(columns=["ssb", "tipo", "cr/bqs"])

    return pd.read_excel(file)


def find_ssb_cr_bq_match(api_value, metodo_value, endpoint_value, ssb_df):
    norm_api = normalize_text(api_value)
    norm_metodo = normalize_text(metodo_value)
    norm_endpoint = normalize_endpoint(endpoint_value)

    for _, row in ssb_df.iterrows():
        row_api = normalize_text(row.get("Api"))
        if not row_api or normalize_text(row.get("Api")) != norm_api:
            continue

        if normalize_text(row.get("Metodo")) != norm_metodo:
            continue

        if normalize_endpoint(row.get("Endpoint")) != norm_endpoint:
            continue

        return row.get("ssb"), row.get("tipo"), row.get("cr/bqs"), row.get("origen")

    return None, None, None, None


def extract_bian_service_name(title) -> str:
    """A partir de un info.title tipo 'API BS Customer Offer xxxxxxxxxx V1',
    descarta el token de version final ('V1') y el codigo/sufijo variable que
    lo precede, devolviendo 'API BS Customer Offer'."""
    tokens = [] if title is None else str(title).strip().split()
    if tokens and re.match(r"(?i)^v\d+$", tokens[-1]):
        tokens = tokens[:-1]
    if tokens:
        tokens = tokens[:-1]
    return " ".join(tokens)


def pascal_case_to_words(value) -> str:
    text = "" if value is None else str(value).strip()
    return re.sub(r"(?<!^)(?<![A-Z])(?=[A-Z])", " ", text)


def parse_bian_tag(tag):
    """Separa un tag tipo 'CR - CustomerOfferProcedure' en ('CR', 'Customer Offer Procedure')."""
    text = "" if tag is None else str(tag).strip()
    if " - " not in text:
        return None, None

    tipo_raw, nombre_raw = text.split(" - ", 1)
    return tipo_raw.strip(), pascal_case_to_words(nombre_raw.strip())


def build_bian_entries(spec: dict, service_name: str) -> list:
    entries = []
    if not spec:
        return entries

    paths = spec.get("paths") or {}
    for endpoint, operations in paths.items():
        if not isinstance(operations, dict):
            continue

        for metodo, operacion in operations.items():
            if metodo.lower() not in HTTP_METHODS or not isinstance(operacion, dict):
                continue

            tags = operacion.get("tags") or []
            if not tags:
                continue

            tipo, nombre = parse_bian_tag(tags[0])
            if tipo is None:
                continue

            entries.append({
                "service_name": service_name,
                "metodo": metodo,
                "endpoint": endpoint,
                "tipo": tipo,
                "nombre": nombre,
            })

    return entries


def list_yaml_files(repo: str, directory: str, headers: dict) -> list:
    url = f"https://api.github.com/repos/{repo}/contents/{directory}"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"No se pudo listar '{directory}' en '{repo}': {response.status_code}")
        return []

    items = response.json()
    return [
        item["path"] for item in items
        if item.get("type") == "file" and item["name"].lower().endswith((".yaml", ".yml"))
    ]


def fetch_yaml_file(repo: str, path: str, headers: dict):
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"No se pudo obtener '{path}' en '{repo}': {response.status_code}")
        return None

    content = base64.b64decode(response.json()["content"]).decode("utf-8")
    try:
        return yaml.safe_load(content)
    except yaml.YAMLError as error:
        print(f"Error al parsear YAML '{path}' en '{repo}': {error}")
        return None


def load_bian_entries(repos: list) -> list:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    entries = []
    for repo_config in repos:
        repo = repo_config["repo"]
        directory = repo_config.get("dir", "api")

        for file_path in list_yaml_files(repo, directory, headers):
            spec = fetch_yaml_file(repo, file_path, headers)
            if not spec:
                continue

            title = (spec.get("info") or {}).get("title")
            service_name = extract_bian_service_name(title)
            entries.extend(build_bian_entries(spec, service_name))

    return entries


def find_bian_match(api_value, metodo_value, endpoint_value, bian_entries: list):
    norm_api = normalize_text(api_value)
    norm_metodo = normalize_text(metodo_value)
    norm_endpoint = normalize_endpoint(endpoint_value)

    for entry in bian_entries:
        print(f"service_name: {entry["service_name"]}")
        print(f"service_name: {entry["metodo"]}")
        print(f"service_name: {entry["endpoint"]}")
        if normalize_text(entry["service_name"]) not in norm_api:
            continue
        if normalize_text(entry["metodo"]) != norm_metodo:
            continue
        if normalize_endpoint(entry["endpoint"]) != norm_endpoint:
            continue

        return entry["service_name"], entry["tipo"], entry["nombre"]

    return None, None, None


# ===============================================
# MAIN PROCESS
# ===============================================
with open(READMES_JSON_FILE, "r", encoding="utf-8") as f:
    readme_data = json.load(f)

rows = []

for readme in readme_data["readmes"]:
    folder = Path(readme["folder"])
    content = readme["content"]

    initiative_match = re.search(r"Codigo de iniciativa:\s(.+)", content)
    ticket_match = re.search(r"Codigo de ticket:\s(.+)", content)

    iniciativa = initiative_match.group(1).strip() if initiative_match else None
    ticket = ticket_match.group(1).strip() if ticket_match else None

    apis = extract_apis_from_readme(content)
    endpoints = read_endpoints_excel(folder)

    for api in apis:
        api_key = api["API"].strip().upper()
        api_endpoints = [e for e in endpoints if e["API_KEY"] == api_key]

        if not api_endpoints:
            rows.append({
                "Iniciativa": iniciativa,
                "Ticket": ticket,
                **api,
                "Metodo": None,
                "Endpoint": None,
                "Descripcion del Endpoint": None
            })
            continue

        for ep in api_endpoints:
            rows.append({
                "Iniciativa": iniciativa,
                "Ticket": ticket,
                **api,
                "Metodo": ep["Metodo"],
                "Endpoint": ep["Endpoint"],
                "Descripcion del Endpoint": ep["Descripcion del Endpoint"]
            })

df = pd.DataFrame(rows)[FINAL_COLUMNS]
df = df.drop_duplicates().reset_index(drop=True)

ssb_cr_bq_df = load_ssb_cr_bq_df(SSB_CR_BQ_FILE)
ssb_matches = df.apply(
    lambda row: find_ssb_cr_bq_match(row["API"], row["Metodo"], row["Endpoint"], ssb_cr_bq_df),
    axis=1
)
df["SBB"] = ssb_matches.apply(lambda m: m[0])
df["Tipo CR"] = ssb_matches.apply(lambda m: m[1])
df["Nombre CR/BQ"] = ssb_matches.apply(lambda m: m[2])
df["Origen"] = ssb_matches.apply(lambda m: m[3])

productive_keys = load_productive_keys(PRODUCTIVO_FILE)

df["Produccion"] = df.apply(
    lambda row: "SI" if (
        normalize_text(row["API"]),
        normalize_text(row["Metodo"]),
        normalize_endpoint(row["Endpoint"]),
    ) in productive_keys else "NO",
    axis=1
)

bian_entries = load_bian_entries(BIAN_CONTRACT_REPOS)
bian_matches = df.apply(
    lambda row: find_bian_match(row["API"], row["Metodo"], row["Endpoint"], bian_entries),
    axis=1
)
df["Service Name Bian"] = bian_matches.apply(lambda m: m[0])
df["Tipo Bian"] = bian_matches.apply(lambda m: m[1])
df["Nombre CR/BQ Bian"] = bian_matches.apply(lambda m: m[2])


# ===============================================
# EXPORT TO EXCEL (EXECUTE STYLE)
# ===============================================
with pd.ExcelWriter(OUTPUT_EXCEL_FILE, engine="openpyxl") as writer:
    df.to_excel(writer, index=False, sheet_name="APIs")
    ws = writer.book["APIs"]

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    # Header style (blue like image)
    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(bold=True, color="FFFFFF")

    thin  = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center")

    # Body cells
    for r in range(2, ws.max_row + 1):
        for c in range(1, ws.max_column + 1):
            ws.cell(row=r, column=c).border = border
            ws.cell(row=r, column=c).alignment = Alignment(vertical="center")

    # Autp column width (safe)
    for idx, col_name in enumerate(df.columns, start=1):
        col_letter = get_column_letter(idx)
        max_len = max(
            len(col_name),
            df[col_name].fillna("").astype(str).map(len).max()
        )
        ws.column_dimensions[col_letter].width = min(max_len + 4, 80)

print(f"Excel generado exitosamente: {OUTPUT_EXCEL_FILE}")