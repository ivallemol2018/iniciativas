import os
import requests
import sys

def cerrar_pr(owner, repo, pr_number, token):
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    headers = {'Authorization': f'token {token}'}
    data = {'state': 'closed'}
    response = requests.patch(url, headers=headers, json=data)
    if response.status_code == 200:
        print("[LOG] Pull Request cerrado correctamente.")
    else:
        print(f"[ERROR] No se pudo cerrar el Pull Request. Código de estado: {response.status_code}")
        print(f"[ERROR] Respuesta: {response.text}")
        sys.exit(1)

if __name__ == "__main__":
    owner = os.getenv('GITHUB_OWNER')
    repo = os.getenv('GITHUB_REPO')
    pr_number = os.getenv('PR_NUMBER')
    token = os.getenv('GITHUB_TOKEN')

    if not all([owner, repo, pr_number, token]):
        print("[ERROR] Faltan variables de entorno necesarias para cerrar el PR.")
        sys.exit(2)

    cerrar_pr(owner, repo, pr_number, token)
