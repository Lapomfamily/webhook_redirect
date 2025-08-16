from flask import Flask, request, abort
import os, smtplib, json
from email.message import EmailMessage

app = Flask(__name__)

MAIL_HOST = os.getenv("MAIL_HOST", "mail.mailo.com")
MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
MAIL_USER = os.getenv("MAIL_USER")        # ex. monadressemail@mailo.com
MAIL_PASS = os.getenv("MAIL_PASS")        # mot de passe applicatif Mailo
MAIL_TO   = os.getenv("MAIL_TO", MAIL_USER)  # destinataire (souvent toi)
HOOK_TOKEN = os.getenv("HOOK_TOKEN")      # jeton partagé pour sécuriser le webhook

def extract_fields(payload: dict):
    # Tente d'abord le format Cusdis
    c = payload.get("comment", {}) if isinstance(payload, dict) else {}
    nickname = c.get("nickname") or payload.get("name") or "Anonyme"
    content  = c.get("content")  or payload.get("message") or ""
    title    = payload.get("pageTitle") or payload.get("title") or ""
    url      = payload.get("pageUrl") or payload.get("url") or ""
    return nickname, content, title, url

@app.post("/hook")
def hook():
    # Sécurité simple: en-tête secret
    if HOOK_TOKEN and request.headers.get("X-Webhook-Token") != HOOK_TOKEN:
        abort(401)

    payload = request.get_json(force=True, silent=True) or {}
    nickname, content, title, url = extract_fields(payload)

    subject = f"[Blog] Nouveau commentaire par {nickname}" + (f" sur « {title} »" if title else "")
    body = f"""Nouveau commentaire reçu.

Auteur : {nickname}
Page  : {title or '-'}
URL   : {url or '-'}

Contenu :
{content}

Payload brut :
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = MAIL_USER
    msg["To"] = MAIL_TO
    msg.set_content(body)

    with smtplib.SMTP(MAIL_HOST, MAIL_PORT) as s:
        s.starttls()
        s.login(MAIL_USER, MAIL_PASS)
        s.send_message(msg)

    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
