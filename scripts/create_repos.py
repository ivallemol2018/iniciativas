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

    if repo_name_lower.startswith(internal_prefixes):
        # === Crear rama "design" desde "main" ===
        print(f" Creando rama 'design' en '{final_name}'...")

        # 1. Obtener SHA de la rama main
        ref_main_url = f"https://api.github.com/repos/{org_name}/{final_name}/git/ref/heads/main"

        print(f"[DEBUG] === GET main ref ===")
        print(f"[DEBUG] URL: {ref_main_url}")

        ref_response = requests.get(ref_main_url, headers=headers)

        print(f"[DEBUG] Status Code (GET main): {ref_response.status_code}")

        try:
            ref_json = ref_response.json()
            print(f"[DEBUG] Response JSON (GET main):")
            print(json.dumps(ref_json, indent=2))
        except Exception:
            print(f"[DEBUG] Response JSON (GET main):")
            print(ref_response.text)

        if ref_response.status_code == 200:
            main_sha = ref_response.json()["object"]["sha"]

            print(f"[DEBUG] SHA main obtenida: {main_sha}")

            # 2. Crear rama design desde main
            create_ref_url = f"https://api.github.com/repos/{org_name}/{final_name}/git/refs"
            payload_ref = {
                "ref": "refs/heads/design",
                "sha": main_sha
            }

            print(f"[DEBUG] === POST create design branch ===")
            print(f"[DEBUG] URL: {create_ref_url}")
            print(f"[DEBUG] Payload: {json.dumps(payload_ref)}")

            create_ref_response = request.post(create_ref_url, headers=headers, json=payload_ref)

            print(f"[DEBUG] Status Code (POST create ref): {create_ref_response.status_code}")

            try:
                create_ref_json = create_ref_response.json()
                print(f"[DEBUG] Response JSON (POST create ref):")
                print(json.dumps(create_ref_json, indent=2))
            except Exception:
                print(f"[DEBUG] Response TEXT (POST create ref):")
                print(create_ref_response.text)

            # --- Evaluacion ---
            if create_ref_response.status_code == 201:
                print(f"Rama 'design' creada exitosamente en '{final_name}'.")

            elif create_ref_response.status_code == 422:
                # Diferenciar causa real del 422
                error_msg = ""
                try:
                    error_msg = create_ref_response.json().get("message","")
                except Exception:
                    error_msg = create_ref_response.text

                if "Reference already exists" in error_msg:
                    print(f" La rama 'design' ya existe en '{final_name}'." )
                elif "ruleset" in error_msg.lower():
                    print(f"Ruleset bloqueo la creacion de la rama 'design' en '{final_name}'.")
                    print(f"[ERROR] Detalle: {error_msg}")
                else:
                    print(f"Error 422 no esperado al crear rama design en '{final_name}'.")
                    print(f"[ERROR] Detalle: {error_msg}")
                continue

            else:
                print(f"Error al crear rama design: {create_ref_response.status_code}")
                print(f"[ERROR] Ver detalle arriba ")
                continue

        else:
            print(f"No se pudo obtener la rama main para '{final_name}'")

            print(f"[DEBUG] Status Code (GET main): {ref_response.status_code}")

            try:
                error_json = ref_response.json()
                print(f"[DEBUG] Error JSON (GET main):")
                print(json.dumps(error_json, indent=2))
            except Exception:
                print(f"[DEBUG] Error TEXT (GET main):")
                print(ref_response.text)

            continue

    print(f" Activando delete_branch_on merge y visibilidad...")
    patch_url = f"https://api.github.com/repos/{org_name}/{final_name}"
    patch_payload = {
        "delete_branch_on_merge": True,
        "visibility": "internal"
    }
    patch_response = request.patch(patch_url, headers=headers, json=patch_payload)
    if patch_response.status_code == 200:
        print("Actualizacion realizada correctamente.")
    else:
        print(f"Error al actualizar: {patch_response.status_code}")
        try:
            print(patch_response.json())
        except Exception:
            print(patch_response.text)
        continue

    print(f"Actualizando propiedades personalizadas...")
    patch_url = f"https://api.github.com/repos/{org_name}/{final_name}/properties/values"
    api_type_payload(
        "AsyncAPI" if api_type == "asyncapi"
        else "partner" if api_type == "private"
        else api_type
    )
    patch_payload = {
        "properties": [
            {"property_name": "api_type", "value": api_type_payload},
            {"property_name": "api_style", "value": api_style},
            {"property_name": "api_exposure", "value": api_exposure},
            {"property_name": "repo_creation_origin", "value": repo_creation_origin},
            {"property_name": "initiative_code", "value": initiative_code},
            
        ]
    }
    patch_response = requests.patch(patch_url, headers=headers, json=patch_payload)
    if patch_response.status_code == 204:
        print("Propiedades personalizadas actualizadas correctamente.")
    else:
        print(f"Error al actualizar propiedades: {patch_response.status_code}")
        try:
            print(patch_response.json())
        except Exception:
            print(patch_response.text)
        continue
    
    # Guardar resultado en variable de entorno REPOS_CREATION_RESULT
    result_list = []
    for item in repos_creados:
        result_list.append({
            "repo": item["repo"],
            "owner": item["owner"],
            "estado": "creado",
            "motivo": "No Aplica",
            "link": item.get("link", "No Aplica") or "No Aplica"
        })
    for item in repos_no_creados:
        result_list.append({
            "repo": item["repo"],
            "owner": item["owner"],
            "estado": "no creado",
            "motivo": item.get("link", "No Aplica") or "No Aplica",
            "link": "No Aplica"
        })
    github_env = os.getenv('GITHUB_ENV', '/github/env')
    with open(github_env, 'a') as env_file:
        env_file.write(f"REPOS_CREATION_RESULT={json.dumps(result_list)}\n")
    print("[LOG] Variable de entorno REPOS_CREATION_RESULT actualizada correctamente.")

        
    
    
    