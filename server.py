from flask import Flask, request, abort
import os, smtplib, json, ssl, logging
from email.message import EmailMessage

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

MAIL_HOST = os.getenv("MAIL_HOST", "mail.mailo.com")
MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))   # 587=STARTTLS, 465=SSL
MAIL_USER = os.getenv("MAIL_USER")
MAIL_PASS = os.getenv("MAIL_PASS")
MAIL_TO   = os.getenv("MAIL_TO", MAIL_USER)
HOOK_TOKEN = os.getenv("HOOK_TOKEN")

def coerce_json():
    """
    Récupère le payload quel que soit le format :
    - JSON direct
    - form-encoded (request.form)
    - enveloppe Hookdeck / chaîne JSON sous 'body', 'payload', 'data'
    - fallback: request.data
    """
    # 1) JSON direct
    data = request.get_json(silent=True) or {}
    if isinstance(data, dict) and data:
        return data

    # 2) Form-encoded -> dict
    if request.form:
        try:
            # Certains services envoient un champ 'payload' / 'data' contenant du JSON
            for key in ("payload", "data", "body"):
                if key in request.form:
                    maybe = request.form.get(key)
                    return json.loads(maybe) if maybe else {}
            return dict(request.form)
        except Exception:
            pass

    # 3) Enveloppes typiques: {'body': '{...}'}, {'event': {'body': '{...}'}}…
    raw = request.get_data(as_text=True) or ""
    try:
        j = json.loads(raw) if raw else {}
        # Essayons de dénicher une chaîne JSON imbriquée
        for key in ("body", "payload", "data"):
            if isinstance(j.get(key), str):
                return json.loads(j[key])
            if isinstance(j.get(key), dict):
                return j[key]
        return j
    except Exception:
        # Dernier recours: rien
        return {}

def extract_fields(payload: dict):
    """
    Cusdis envoie souvent:
      {
        "siteId": "...",
        "comment": {"id":"...","content":"...", "nickname":"..."},
        "pageId":"...", "pageTitle":"...", "pageUrl":"..."
      }
    On tolère aussi d'autres variantes (name/message/title/url).
    """
    if not isinstance(payload, dict):
        return ("Anonyme", "", "", "")

    c = payload.get("comment") or {}
    nickname = c.get("nickname") or payload.get("nickname") or payload.get("name") or "Anonyme"
    content  = c.get("content")  or payload.get("content")  or payload.get("message") or ""
    title    = payload.get("pageTitle") or payload.get("title") or ""
    url      = payload.get("pageUrl")   or payload.get("url")   or ""
    return (nickname, content, title, url)

@app.post("/hook")
def hook():
    # Sécurité simple via en-tête
    if HOOK_TOKEN and request.headers.get("X-Webhook-Token") != HOOK_TOKEN:
        abort(401)

    payload = coerce_json()
    app.logger.info("Payload reçu: %s", payload)

    nickname, content, title, url = extract_fields(payload)

    subject = f"[Blog] Nouveau commentaire par {nickname}" + (f" — {title}" if title else "")
    lines = [
        "Nouveau commentaire reçu.",
        "",
        f"Auteur : {nickname}",
        f"Page  : {title or '-'}",
        f"URL   : {url or '-'}",
        "",
        "Contenu :",
        content or "(vide)",
        "",
        "Payload brut :",
        json.dumps(payload, ensure_ascii=False, indent=2)
    ]
    body = "\n".join(lines)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = MAIL_USER
    msg["To"] = MAIL_TO
    msg.set_content(body)

    try:
        if MAIL_PORT == 465:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(MAIL_HOST, MAIL_PORT, context=ctx) as s:
                s.login(MAIL_USER, MAIL_PASS)
                s.send_message(msg)
        else:
            with smtplib.SMTP(MAIL_HOST, MAIL_PORT) as s:
                s.starttls()
                s.login(MAIL_USER, MAIL_PASS)
                s.send_message(msg)
    except Exception as e:
        app.logger.exception("Erreur envoi mail: %s", e)
        return f"ERROR: {e}", 500

    return "OK", 200

@app.get("/")
def health():
    return "OK", 200
