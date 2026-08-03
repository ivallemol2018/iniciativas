import os
import requests
import time
import sys
import json
import base64  # <-- Agregado para codificacion base64

# Entradas desde variables de entorno
token = os.getenv("GITHUB_TOKEN")
org_name = os.getenv("GITHUB_OWNER")
repo_info_raw_b64 = os.getenv("REPOS_TO_CREATE","")
repo_name_pr = os.getenv("GITHUB_REPO")
repo_creation_origin = os.getenv("INITIATIVE_CODE","").upper()

# Decodifica base64
repo_info_raw = base64.b64decode(repo_info_raw_b64).decode() if repo_info_raw_b64 else "[]"
try:
    repo_info_array = json.loads(repo_info_raw)
except json.JSONDecodeError:
    raise Exception("La variable repo_info_array no contiene un JSON valido.")

if not all([token, org_name, repo_info_array]):
    raise Exception("Faltan variables de entorno requeridas")
    
template_map = {
    "rest": "api-rest-template-repository",
    "event-driven": "asyncapi-template-repository",
    "graphql": "api-graphql-template-repository"
}

headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28"
}

# --- Flujo principal ---
repos_creados = []
repos_no_creados = []

for repo_info in repo_info_array:
    repo_name = repo_info["repo"]
    api_type = repo_info["api_type"]
    api_style = repo_info["api_style"]
    api_exposure = repo_info["api_exposure"]
    repo_owner = repo_info.get("owner","")
    repo_name_lower = repo_name.lower()
    # Definicion de prefijos
    external_prefixes = ("private-","public-","open-")
    internal_prefixes = ("channel-","business-","core-","data-")
    
    repo_owner_upper = repo_owner.upper()
    
    SCHEMA_PILOT_OWNERS = {
        "APTI",
        "TTIB",
        "APSA",
        "SIAT",
        "SCFI",
        "NTEL"
    }
    
    if repo_name_lower.startswith(external_prefixes):
        template_repo = "api-rest-template-repository"
    elif repo_name_lower.startswith(internal_prefixes):
        if repo_owner_upper in SCHEMA_PILOT_OWNERS:
            template_repo = "api-rest-template-repository"
        else:
            template_repo = "api-rest-internal-template-repository"
    else:
        template_repo = template_map.get(api_style)
        
    
    final_name = repo_name
    github_link = f"https://github.com/{org_name}/{final_name}"
    api_check_url = f"https://api.github.com/repos/{org_name}/{final_name}"
    check_reponse = requests.get(api_check_url, headers=headers)
    
    if check_reponse.status_code == 200:
        print(f"El repositorio '{final_name}' ya existe. Se verificara el team developer asignado.")
        continue
    
    # --- Creacion de repositorio ---
    print(f"Creando repositorio '{final_name}' desde template '{template_repo}'...")
    generate_url = f"https://api.github.com/repos/{org_name}/{template_repo}/generate"
    payload_template = {
        "owner": org_name,
        "name": final_name,
        "description": "Repositorio de API",
        "private": False,
        "include_all_branches": False
    }
    
    response_template = requests.post(generate_url, headers=headers,json=payload_template)
    repo_link= f"https://github.com/{org_name}/{final_name}"
    
    if response_template.status_code == 201:
        print(f"Repositorio {final_name} creado a partir de template {template_repo} exitosamente.")
        repos_creados.append({
            "repo": final_name,
            "owner": repo_owner,
            "link": repo_link
        })
        with open("repos_creados.txt", "a") as f:
            f.write(f"{final_name},{repo_owner}\n")
    else:
        print(f"Error al crear el repositorio {final_name}: {response_template.status_code}")
        repos_no_creados.append({
            "repo": final_name,
            "owner": repo_owner,
            "link": repo_link
        })
        continue
        
    time.sleep(30)  
        
    
    
    