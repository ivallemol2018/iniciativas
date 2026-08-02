import requests
import os
import json
import re
import sys

def comentar_pr(owner,repo, pr_number, token, mensaje):
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
    headers = {'Authorization': f'{token}'}
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
        
    except Exception as error:
        print(f"[ERROR] {error}")
        sys.exit(1)
        
if __name__ == "__main__":
    get_pr_info()
        