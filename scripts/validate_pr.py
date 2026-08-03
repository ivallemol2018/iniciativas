import requests
import os
import json
import re
import sys

def comentar_pr(owner,repo, pr_number, token, mensaje):
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
    headers = {'Authorization': f'token {token}'}
    data = {'body': mensaje}
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    print("[LOG] Comentario publicado en el PR.")
    
def get_pr_info():
    try:
        owner = os.getenv('GITHUB_OWNER')
        repo = os.getenv('GITHUB_REPO')
        pr_number = os.getenv('PR_NUMBER')
        token = os.getenv('GITHUB_TOKEN')
        workflow_url = os.getenv('WORKFLOW_RUN_URL')
        github_env = os.getenv('GITHUB_ENV', '/github/env')
        print(f"[LOG] OWNER: {owner}, REPO: {repo}, PR_NUMBER: {pr_number}")
        
        if not all([owner, repo, pr_number, token]):
            raise Exception("Faltan variables de entorno necesarias")
            
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
        headers = {'Authorization': f'token {token}'}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        pr_data = response.json()
        print("[LOG] PR data obtenida correctamente")
         print(f"[LOG] Token: {token}")
        
        title = pr_data.get('title', '')
        body = pr_data.get('body', '')
        created_at = pr_data.get('created_at')
        number = pr_data.get('number')
        branch_name = pr_data.get('head', {}).get('ref','')
        print(f"[LOG] Titulo: {title}")
        print(f"[LOG] Rama de origen: {branch_name}")
        print(f"[LOG] Fecha de creacion: {created_at}")
        print(f"[LOG] Body: {body}")
        
        titulo_valido = bool(re.match(r'^D-\d{5,8}', title))
        print(f"[LOG] ¿Titulo valido?: {titulo_valido}")
        
        ticket_match = re.search(r'- \*\*Ticket\*\*: \*{0,3}((?:APIT-\d{4,8})|(?:UBAG-\d{1,9}))\*{0,3}', body)
        ticket_code = ticket_match.group(1) if ticket_match else None
        ticket_valido = bool(ticket_code)
        print(f"[LOG] ¿Ticket valido?: {ticket_valido}")
        
        # Exportar 
        if github_env:
            with open(github_env, 'a') as env_file:
                env_file.write(f'INITIATIVE_CODE={title}\n')
                env_file.write(f'TICKET_CODE={ticket_code if ticket_code else ""}\n')
            print("[LOG] Variable de entorno INITIATIVE_CODE y TICKET_CODE exportadas a GITHUB_ENV")
            
        if titulo_valido and ticket_valido:
            comment_body = (
                "### Informacion registrada del Pull Request\n"
                f"- **Titulo del PR:** `{title}`\n"
                f"- **Rama de origen:** `{branch_name}`\n"
                f"- **Codigo de ticket de solicitud:** `{ticket_code}`\n"
                f"- **Fecha de creacion:** `{created_at}`\n"
                "\n Validaciones correctas."
            )
        else:
            errores = []
            if not titulo_valido:
                errores.append("- El titulo no cumple el formato requerido. Ejemplo valido: D-04039")
            if not ticket_valido:
                errores.append("- El codigo del ticket no cumple el formato requerido. Ejemplos validos: APIT-6954 o UBAG-123.")
            comment_body = (
                "### Errores en el registro del Pull Request\n"
                f"- **Titulo del PR:** `{title}`\n"
                f"- **Rama de origen:** `{branch_name}`\n"
                f"- **Codigo de ticket de solicitud:** `{ticket_code}`\n"
                f"- **Fecha de creacion:** `{created_at}`\n"
                "\n" + "\n".join(errores)
            )
            
        comentar_pr(owner, repo, pr_number, token, comment_body)
    except Exception as error:
        print(f"[ERROR] {error}")
        sys.exit(1)
        
if __name__ == "__main__":
    get_pr_info()
        