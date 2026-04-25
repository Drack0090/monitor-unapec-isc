import os
import json
import hashlib
import requests
from bs4 import BeautifulSoup
from datetime import datetime

URL = "https://egresados.unapec.edu.do/ofertas-de-empleo/"
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_UNAPEC")
STATE_FILE = "isc_state.json"

KEYWORDS = ["ISC", "Ing. en Sistemas", "Ingeniería en Sistemas", "Sistemas Computacionales"]

def fetch_page():
    headers = {"User-Agent": "Mozilla/5.0 (compatible; JobMonitor/1.0)"}
    response = requests.get(URL, headers=headers, timeout=15)
    response.raise_for_status()
    return response.text

def parse_jobs(html):
    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    # Cada oferta está en un bloque con h3 (empresa) seguido de info
    # Buscamos todos los bloques de empleo
    content = soup.find("div", class_="container") or soup.find("main") or soup.body

    # Los empleos tienen estructura: h3 empresa, luego párrafos con título, tipo, carrera, descripción
    current_job = {}
    all_text_blocks = []

    # Estrategia: buscar h3 (empresas) y recopilar el texto que les sigue
    for tag in content.find_all(["h3", "p", "li", "div"]):
        text = tag.get_text(separator=" ", strip=True)
        if not text:
            continue
        all_text_blocks.append(text)

    # Parsear ofertas completas buscando bloques entre h3
    empresa_tags = content.find_all("h3")

    for h3 in empresa_tags:
        empresa = h3.get_text(strip=True)
        if not empresa or empresa in ["Recursos", "Subportales", "Instituciones Relacionadas"]:
            continue

        # Recopilar texto del bloque siguiente al h3
        siblings = []
        for sibling in h3.find_next_siblings():
            if sibling.name == "h3":
                break
            text = sibling.get_text(separator=" ", strip=True)
            if text:
                siblings.append(text)

        full_text = " | ".join(siblings)

        job = {
            "empresa": empresa,
            "contenido": full_text,
            "id": hashlib.md5(f"{empresa}:{full_text}".encode()).hexdigest()
        }
        jobs.append(job)

    return jobs

def filter_isc_jobs(jobs):
    isc_jobs = []
    for job in jobs:
        texto = f"{job['empresa']} {job['contenido']}"
        if any(kw.upper() in texto.upper() for kw in KEYWORDS):
            isc_jobs.append(job)
    return isc_jobs

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"known_ids": [], "jobs": []}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def send_discord_notification(new_jobs, removed_jobs):
    if not DISCORD_WEBHOOK:
        print("⚠️  No se configuró DISCORD_WEBHOOK_URL")
        return

    embeds = []

    for job in new_jobs:
        embeds.append({
            "title": f"🟢 Nueva oferta ISC — {job['empresa']}",
            "description": job["contenido"][:800] + ("..." if len(job["contenido"]) > 800 else ""),
            "color": 0x00FF7F,
            "url": URL,
            "footer": {"text": f"Detectado: {datetime.now().strftime('%d/%m/%Y %H:%M')}"}
        })

    for job in removed_jobs:
        embeds.append({
            "title": f"🔴 Oferta ISC eliminada — {job['empresa']}",
            "description": job["contenido"][:500] + ("..." if len(job["contenido"]) > 500 else ""),
            "color": 0xFF4444,
            "url": URL,
            "footer": {"text": f"Detectado: {datetime.now().strftime('%d/%m/%Y %H:%M')}"}
        })

    # Discord permite máx 10 embeds por mensaje
    for i in range(0, len(embeds), 10):
        payload = {
            "content": "📢 **Cambios detectados en ofertas ISC — UNAPEC**",
            "embeds": embeds[i:i+10]
        }
        r = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
        r.raise_for_status()
        print(f"✅ Notificación enviada a Discord ({len(embeds)} cambios)")

def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Iniciando monitoreo...")

    html = fetch_page()
    all_jobs = parse_jobs(html)
    isc_jobs = filter_isc_jobs(all_jobs)

    print(f"   Total ofertas en página: {len(all_jobs)}")
    print(f"   Ofertas ISC encontradas: {len(isc_jobs)}")

    state = load_state()
    known_ids = set(state.get("known_ids", []))
    old_jobs = {j["id"]: j for j in state.get("jobs", [])}

    current_ids = set(j["id"] for j in isc_jobs)
    current_jobs = {j["id"]: j for j in isc_jobs}

    new_ids = current_ids - known_ids
    removed_ids = known_ids - current_ids

    new_jobs = [current_jobs[i] for i in new_ids]
    removed_jobs = [old_jobs[i] for i in removed_ids if i in old_jobs]

    if new_jobs or removed_jobs:
        print(f"   🔔 Cambios: +{len(new_jobs)} nuevas, -{len(removed_jobs)} eliminadas")
        send_discord_notification(new_jobs, removed_jobs)
    else:
        print("   ✅ Sin cambios en ofertas ISC.")

    # Guardar estado actualizado
    save_state({
        "known_ids": list(current_ids),
        "jobs": isc_jobs,
        "last_check": datetime.now().isoformat()
    })

if __name__ == "__main__":
    main()
