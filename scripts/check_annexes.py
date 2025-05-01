#!/usr/bin/env python3
import requests, json, os
from bs4 import BeautifulSoup
from github import Github  # pip install PyGithub

# —— CONFIGURACIÓN ——
BASE_URL       = "https://ec.europa.eu/growth/tools-databases/cosing/reference/annexes"
ANNEX_PAGES    = ["I","II","III","IV","V","VI"]
STATE_FILE     = "annexes_state.json"
GITHUB_TOKEN   = os.environ.get("GITHUB_TOKEN")
REPO_NAME      = "Maxi199588/cosmetic-checker"  # Ajusta a tu usuario/repo
BRANCH         = "main"


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def head_last_modified(url):
    r = requests.head(url, allow_redirects=True, timeout=10)
    r.raise_for_status()
    return r.headers.get("Last-Modified") or r.headers.get("ETag")


def download(url, dest):
    r = requests.get(url, timeout=20)
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
        except:
            repo.create_file(path, message, content, branch=BRANCH)


def main():
    state     = load_state()
    new_state = {}
    to_commit = []

    for anexo in ANNEX_PAGES:
        page_url = f"{BASE_URL}/list/{anexo}"
        r = requests.get(page_url, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Buscar enlace XLS por texto del link
        a_xls = None
        for link in soup.find_all("a"):
            if link.get_text(strip=True).lower() == "xls":
                a_xls = link
                break
        if not a_xls:
            print(f"[WARN] No encontré enlace XLS en Annex {anexo}")
            new_state[anexo] = state.get(anexo)
            continue

        href = a_xls["href"]
        if href.startswith("/"):
            href = "https://ec.europa.eu" + href

        lm = head_last_modified(href)
        new_state[anexo] = lm

        if state.get(anexo) != lm:
            print(f"[CHANGE] Annex {anexo}: {state.get(anexo)} -> {lm}")
            filename = f"COSING_Annex_{anexo}.xlsx"
            download(href, filename)
            to_commit.append(filename)

    save_state(new_state)

    if to_commit:
        commit_and_push(to_commit, "🔄 Auto-update COSING Anexos")
    else:
        print("✅ Sin cambios detectados.")


if __name__ == "__main__":
    main()
