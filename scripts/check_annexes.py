#!/usr/bin/env python3
import requests
import json
import os
from github import Github  # pip install PyGithub

# —— CONFIGURACIÓN ——
# Prefijo de la URL donde están los XLS de los anexos
STATIC_BASE_URL = "https://ec.europa.eu/growth/tools-databases/cosing/assets/data"
ANNEX_PAGES     = ["II", "III", "IV", "V", "VI"]  # I no tiene XLS
STATE_FILE      = "annexes_state.json"
GITHUB_TOKEN    = os.environ.get("GITHUB_TOKEN")
REPO_NAME       = "Maxi199588/cosmetic-checker"  # Ajusta a tu usuario/repo
BRANCH          = "main"


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def head_last_modified(url):
    r = requests.head(url, allow_redirects=True, timeout=10)
    r.raise_for_status()
    # Usa Last-Modified o ETag como sello
    return r.headers.get("Last-Modified") or r.headers.get("ETag")


def download(url, dest):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    with open(dest, "wb") as f:
        f.write(r.content)


def commit_and_push(files, message):
    gh   = Github(GITHUB_TOKEN)
    repo = gh.get_repo(REPO_NAME)
    for path in files:
        with open(path, "rb") as f:
            content = f.read()
        try:
            existing = repo.get_contents(path, ref=BRANCH)
            repo.update_file(path, message, content, existing.sha, branch=BRANCH)
        except Exception:
            repo.create_file(path, message, content, branch=BRANCH)


def main():
    state     = load_state()
    new_state = {}
    to_commit = []

    for anexo in ANNEX_PAGES:
        # Construye la URL estática del XLS (versión 2)
        href = f"{STATIC_BASE_URL}/COSING_Annex_{anexo}_v2.xlsx"
        lm = head_last_modified(href)
        new_state[anexo] = lm

        # Si cambió, descargamos
        if state.get(anexo) != lm:
            print(f"[CHANGE] Annex {anexo}: {state.get(anexo)} -> {lm}")
            filename = os.path.join("RESTRICCIONES", f"COSING_Annex_{anexo}_v2.xlsx")
            download(href, filename)
            to_commit.append(filename)

    # Guardamos estado actualizado
    save_state(new_state)

    # Commit si hay archivos nuevos o actualizados
    if to_commit:
        commit_and_push(to_commit, "🔄 Auto-update COSING Anexos")
    else:
        print("✅ Sin cambios detectados.")


if __name__ == "__main__":
    main()
