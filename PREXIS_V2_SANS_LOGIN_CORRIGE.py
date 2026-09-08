import os
import re
import json
import base64
import secrets
import sqlite3
import datetime
import subprocess
import platform
from urllib.parse import quote_plus

import requests
from flask import (
    Flask,
    jsonify,
    render_template_string,
    request
)
from cryptography.fernet import Fernet


# ============================================================
# PREXIS V2 // CLOUD OVERLORD
# ============================================================
#
# MODE SERVEUR :
#     python app.py
#
# MODE AGENT PC :
#     python app.py --agent
#
# LOCAL :
#     http://127.0.0.1:5000 (aucune connexion requise)
#
# RENDER :
#     PORT est fourni automatiquement.
#
# VARIABLES IMPORTANTES :
#
# SECRET_KEY=... (optionnel, non utilisé sans authentification)
#
# AI_API_KEY=...
# AI_BASE_URL=https://api.openai.com/v1
# AI_MODEL=...
#
# BRAVE_SEARCH_API_KEY=...
#
# FERNET_KEY=...
#
# DATABASE_URL=...
#
# PREXIS_SERVER_URL=https://ton-app.onrender.com
# AGENT_TOKEN=...
#
# ============================================================


# ============================================================
# 1. CONFIGURATION
# ============================================================

APP_NAME = "PREXIS"
APP_VERSION = "2.0"

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    secrets.token_hex(32)
)

PORT = int(os.environ.get("PORT", "5000"))

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

AI_API_KEY = os.environ.get("AI_API_KEY", "").strip()
AI_BASE_URL = os.environ.get(
    "AI_BASE_URL",
    "https://api.openai.com/v1"
).rstrip("/")

AI_MODEL = os.environ.get(
    "AI_MODEL",
    "gpt-4o-mini"
)

BRAVE_SEARCH_API_KEY = os.environ.get(
    "BRAVE_SEARCH_API_KEY",
    ""
).strip()


AGENT_TOKEN = os.environ.get(
    "AGENT_TOKEN",
    secrets.token_urlsafe(32)
)

PREXIS_SERVER_URL = os.environ.get(
    "PREXIS_SERVER_URL",
    "http://127.0.0.1:5000"
).rstrip("/")

FERNET_KEY = os.environ.get("FERNET_KEY", "").strip()


# ============================================================
# 2. CHIFFREMENT
# ============================================================

def get_fernet():
    """
    Génère une clé temporaire en développement si FERNET_KEY
    n'est pas définie.

    IMPORTANT :
    En production, définir FERNET_KEY dans Render.
    """

    global FERNET_KEY

    if not FERNET_KEY:
        FERNET_KEY = Fernet.generate_key().decode()

    try:
        return Fernet(FERNET_KEY.encode())
    except Exception:
        raise RuntimeError(
            "FERNET_KEY invalide. Génère une clé Fernet et "
            "place-la dans les variables d'environnement."
        )


fernet = get_fernet()


def encrypt_text(text):
    return fernet.encrypt(
        text.encode("utf-8")
    ).decode("utf-8")


def decrypt_text(text):
    try:
        return fernet.decrypt(
            text.encode("utf-8")
        ).decode("utf-8")
    except Exception:
        return "[DONNÉES CHIFFRÉES ILLISIBLES]"


# ============================================================
# 3. BASE DE DONNÉES
# ============================================================

USE_POSTGRES = DATABASE_URL.startswith("postgres")


def get_db():
    """
    SQLite en local.
    PostgreSQL sur Render si DATABASE_URL est configurée.
    """

    if USE_POSTGRES:
        try:
            import psycopg
            from psycopg.rows import dict_row

            conn = psycopg.connect(
                DATABASE_URL,
                row_factory=dict_row
            )
            return conn

        except Exception as e:
            print("Erreur PostgreSQL :", e)
            raise

    conn = sqlite3.connect(
        "prexis_local.db",
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    return conn


def db_execute(query, params=(), fetch=False, many=False):
    conn = get_db()

    try:
        cur = conn.cursor()

        if many:
            cur.executemany(query, params)
        else:
            cur.execute(query, params)

        if fetch:
            rows = cur.fetchall()
        else:
            rows = None

        conn.commit()

        return rows

    finally:
        conn.close()


def normalize_sql(sql):
    """
    Permet d'utiliser la même logique pour SQLite et PostgreSQL.
    """

    if USE_POSTGRES:
        sql = sql.replace("?", "%s")

        sql = sql.replace(
            "INTEGER PRIMARY KEY AUTOINCREMENT",
            "SERIAL PRIMARY KEY"
        )

    return sql


def execute(query, params=(), fetch=False):
    return db_execute(
        normalize_sql(query),
        params,
        fetch=fetch
    )


def init_db():

    statements = [

        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            sender TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            memory TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS passwords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            site TEXT NOT NULL,
            pwd TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            last_seen TEXT,
            os TEXT,
            status TEXT
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS agent_commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER,
            command TEXT NOT NULL,
            argument TEXT,
            status TEXT NOT NULL,
            result TEXT,
            created_at TEXT NOT NULL
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            webhook TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    ]

    for statement in statements:
        execute(statement)


init_db()


# ============================================================
# 4. IDENTITÉ LOCALE SANS CONNEXION
# ============================================================

# PREXIS fonctionne sans identifiant ni mot de passe.
# LID 1 sert simplement de propriétaire logique des données
# dans la base afin de conserver la mémoire, les tâches et les notes.
def get_current_user_id():
    return 1


# ============================================================
# 5. UTILITAIRES
# ============================================================

def now_string():
    return datetime.datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def clean_text(value, maximum=12000):

    if value is None:
        return ""

    value = str(value).strip()

    return value[:maximum]


def is_local_agent_authorized():

    token = request.headers.get(
        "X-PREXIS-AGENT-TOKEN",
        ""
    )

    return secrets.compare_digest(
        token,
        AGENT_TOKEN
    )


# ============================================================
# 6. MÉMOIRE
# ============================================================

def get_memories(user_id, limit=20):

    rows = execute(
        """
        SELECT memory, created_at
        FROM memories
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (user_id, limit),
        fetch=True
    )

    return [
        {
            "memory": row["memory"],
            "created_at": row["created_at"]
        }
        for row in rows
    ]


def save_memory(user_id, memory):

    memory = clean_text(memory, 1000)

    if not memory:
        return

    execute(
        """
        INSERT INTO memories
        (user_id, memory, created_at)
        VALUES (?, ?, ?)
        """,
        (
            user_id,
            memory,
            now_string()
        )
    )


def detect_memory_request(prompt):

    p = prompt.lower()

    keywords = [
        "souviens-toi",
        "souviens toi",
        "mémorise",
        "retient",
        "retiens",
        "garde en mémoire",
        "n'oublie pas",
        "note que"
    ]

    return any(k in p for k in keywords)


def extract_memory(prompt):

    patterns = [
        r"souviens[- ]toi\s+(?:que\s+)?(.+)",
        r"mémorise\s+(?:que\s+)?(.+)",
        r"retiens\s+(?:que\s+)?(.+)",
        r"garde en mémoire\s+(?:que\s+)?(.+)",
        r"n'oublie pas\s+(?:que\s+)?(.+)"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            prompt,
            flags=re.IGNORECASE
        )

        if match:
            return match.group(1).strip()

    return prompt


# ============================================================
# 7. RECHERCHE WEB
# ============================================================

def web_search(query):

    query = clean_text(query, 500)

    if not query:
        return []

    if not BRAVE_SEARCH_API_KEY:
        return []

    try:

        response = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={
                "q": query,
                "count": 5,
                "safesearch": "moderate"
            },
            headers={
                "Accept": "application/json",
                "X-Subscription-Token":
                    BRAVE_SEARCH_API_KEY
            },
            timeout=12
        )

        response.raise_for_status()

        data = response.json()

        results = []

        for item in data.get(
            "web",
            {}
        ).get(
            "results",
            []
        )[:5]:

            results.append({
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "url": item.get("url", "")
            })

        return results

    except Exception as e:

        print("Recherche Web :", e)

        return []


def should_search_web(prompt):

    p = prompt.lower()

    keywords = [
        "recherche",
        "cherche sur internet",
        "sur le web",
        "actualités",
        "actualité",
        "aujourd'hui",
        "dernier",
        "dernière",
        "latest",
        "prix actuel",
        "météo",
        "news"
    ]

    return any(
        keyword in p
        for keyword in keywords
    )


# ============================================================
# 8. IA
# ============================================================

SYSTEM_PROMPT = """
Tu es PREXIS, un assistant personnel appelé parfois
PREXIS OVERLORD.

Tu réponds en français sauf si l'utilisateur demande une autre langue.

Ton comportement :
- précis
- utile
- naturel
- concis lorsque la question est simple
- détaillé lorsque nécessaire
- tu ne prétends jamais avoir exécuté une action si elle n'a pas réellement été exécutée
- tu ne prétends jamais avoir accès au PC local sans agent connecté
- tu ne prétends jamais avoir analysé une image si aucune image n'a été reçue
- tu ne fabriques pas de résultats de recherche Web

Tu peux utiliser le contexte mémoire fourni par PREXIS.

Quand une commande système pourrait être nécessaire,
tu dois la signaler comme une action à effectuer et ne pas
inventer son résultat.

Tu es l'intelligence centrale de PREXIS.
"""


def call_ai(prompt, memories=None, search_results=None,
            image_data=None):

    if not AI_API_KEY:

        return (
            "Le moteur IA n'est pas encore configuré. "
            "Ajoute AI_API_KEY et AI_MODEL dans les variables "
            "d'environnement de PREXIS."
        )

    memories = memories or []
    search_results = search_results or []

    memory_text = ""

    if memories:

        memory_text = "\n\nMÉMOIRE PREXIS :\n"

        for item in memories:
            memory_text += (
                "- " +
                item["memory"] +
                "\n"
            )

    web_text = ""

    if search_results:

        web_text = "\n\nRÉSULTATS WEB :\n"

        for item in search_results:

            web_text += (
                f"- {item['title']}\n"
                f"  {item['description']}\n"
                f"  {item['url']}\n"
            )

    full_prompt = (
        SYSTEM_PROMPT +
        memory_text +
        web_text +
        "\n\nDEMANDE UTILISATEUR :\n" +
        prompt
    )

    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json"
    }

    # Format compatible avec de nombreux fournisseurs
    # d'API utilisant le format Chat Completions.

    content = []

    content.append({
        "type": "text",
        "text": full_prompt
    })

    if image_data:

        content.append({
            "type": "image_url",
            "image_url": {
                "url": image_data
            }
        })

    payload = {
        "model": AI_MODEL,
        "messages": [
            {
                "role": "user",
                "content": content
            }
        ],
        "temperature": 0.7
    }

    try:

        response = requests.post(
            f"{AI_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=90
        )

        response.raise_for_status()

        data = response.json()

        choices = data.get("choices", [])

        if not choices:
            return "PREXIS : réponse IA vide."

        message = choices[0].get(
            "message",
            {}
        )

        result = message.get(
            "content",
            ""
        )

        if isinstance(result, list):

            result = "".join(
                part.get("text", "")
                for part in result
                if isinstance(part, dict)
            )

        result = str(result).strip()

        if not result:
            return "PREXIS : impossible de récupérer la réponse."

        return result

    except requests.HTTPError as e:

        print(
            "Erreur API IA :",
            e,
            getattr(e.response, "text", "")
        )

        return (
            "PREXIS : le serveur IA a refusé la requête. "
            "Vérifie AI_API_KEY, AI_BASE_URL et AI_MODEL."
        )

    except Exception as e:

        print("Erreur IA :", e)

        return (
            "PREXIS : impossible de contacter le moteur IA."
        )


# ============================================================
# 9. COMMANDES PRÉDEFINIES
# ============================================================

ALLOWED_AGENT_COMMANDS = {

    "open_browser": {
        "description": "Ouvrir le navigateur",
        "requires_confirmation": True
    },

    "get_system_info": {
        "description": "Informations système",
        "requires_confirmation": False
    },

    "get_hostname": {
        "description": "Nom du PC",
        "requires_confirmation": False
    },

    "open_folder": {
        "description": "Ouvrir un dossier",
        "requires_confirmation": True
    },

    "notify": {
        "description": "Afficher une notification",
        "requires_confirmation": False
    }
}


def execute_agent_command(command, argument=""):

    system = platform.system()

    command = command.strip()

    if command not in ALLOWED_AGENT_COMMANDS:

        return {
            "ok": False,
            "result": "Commande non autorisée."
        }

    if command == "get_hostname":

        return {
            "ok": True,
            "result": platform.node()
        }

    if command == "get_system_info":

        return {
            "ok": True,
            "result": json.dumps(
                {
                    "system": platform.system(),
                    "release": platform.release(),
                    "version": platform.version(),
                    "machine": platform.machine(),
                    "processor": platform.processor()
                },
                ensure_ascii=False,
                indent=2
            )
        }

    if command == "open_browser":

        url = argument.strip()

        if not url.startswith(
            ("http://", "https://")
        ):

            return {
                "ok": False,
                "result": "URL refusée."
            }

        try:

            if system == "Windows":

                subprocess.Popen(
                    ["cmd", "/c", "start", "", url]
                )

            elif system == "Darwin":

                subprocess.Popen(
                    ["open", url]
                )

            else:

                subprocess.Popen(
                    ["xdg-open", url]
                )

            return {
                "ok": True,
                "result": "Navigateur ouvert."
            }

        except Exception as e:

            return {
                "ok": False,
                "result": str(e)
            }

    if command == "open_folder":

        path = os.path.abspath(
            os.path.expanduser(argument)
        )

        # Protection simple : refuser les chemins trop
        # dangereux ou manifestement système.

        forbidden = [
            "/etc",
            "/boot",
            "/proc",
            "/sys",
            "C:\\Windows",
            "C:\\Program Files"
        ]

        for item in forbidden:

            if path.lower().startswith(
                item.lower()
            ):

                return {
                    "ok": False,
                    "result": "Dossier système refusé."
                }

        if not os.path.isdir(path):

            return {
                "ok": False,
                "result": "Dossier inexistant."
            }

        try:

            if system == "Windows":

                subprocess.Popen(
                    ["explorer", path]
                )

            elif system == "Darwin":

                subprocess.Popen(
                    ["open", path]
                )

            else:

                subprocess.Popen(
                    ["xdg-open", path]
                )

            return {
                "ok": True,
                "result": "Dossier ouvert."
            }

        except Exception as e:

            return {
                "ok": False,
                "result": str(e)
            }

    if command == "notify":

        message = clean_text(
            argument,
            500
        )

        if system == "Windows":

            try:

                import ctypes

                ctypes.windll.user32.MessageBoxW(
                    0,
                    message,
                    "PREXIS",
                    0x40
                )

                return {
                    "ok": True,
                    "result": "Notification affichée."
                }

            except Exception as e:

                return {
                    "ok": False,
                    "result": str(e)
                }

        return {
            "ok": True,
            "result": message
        }

    return {
        "ok": False,
        "result": "Commande non implémentée."
    }


# ============================================================
# 10. AGENT LOCAL
# ============================================================

def run_local_agent():

    print()
    print("=" * 60)
    print("PREXIS LOCAL AGENT")
    print("=" * 60)
    print("Serveur :", PREXIS_SERVER_URL)
    print("PC :", platform.node())
    print("OS :", platform.system())
    print("=" * 60)
    print()

    while True:

        try:

            headers = {
                "X-PREXIS-AGENT-TOKEN":
                    AGENT_TOKEN
            }

            heartbeat = requests.post(
                f"{PREXIS_SERVER_URL}/api/agent/heartbeat",
                headers=headers,
                json={
                    "name": platform.node(),
                    "os": platform.system()
                },
                timeout=10
            )

            if heartbeat.status_code != 200:

                print(
                    "Heartbeat :",
                    heartbeat.status_code
                )

            response = requests.get(
                f"{PREXIS_SERVER_URL}/api/agent/next",
                headers=headers,
                timeout=30
            )

            if response.status_code != 200:

                print(
                    "Serveur agent :",
                    response.status_code
                )

                import time
                time.sleep(5)
                continue

            data = response.json()

            command = data.get("command")

            if command:

                command_id = data.get(
                    "id"
                )

                result = execute_agent_command(
                    command.get("command", ""),
                    command.get("argument", "")
                )

                requests.post(
                    f"{PREXIS_SERVER_URL}/api/agent/result",
                    headers=headers,
                    json={
                        "id": command_id,
                        "ok": result["ok"],
                        "result": result["result"]
                    },
                    timeout=10
                )

            import time
            time.sleep(2)

        except KeyboardInterrupt:

            print(
                "\nPREXIS Agent arrêté."
            )
            break

        except Exception as e:

            print(
                "Agent erreur :",
                e
            )

            import time
            time.sleep(5)


# ============================================================
# 11. ROUTES WEB
# ============================================================

@app.route("/")
def index():

    return render_template_string(
        HTML_UI,
        app_name=APP_NAME,
        version=APP_VERSION
    )


# ============================================================
# 11. API CHAT
# ============================================================

@app.route(
    "/api/interact",
    methods=["POST"]
)
def interact():

    data = request.get_json(
        silent=True
    ) or {}

    prompt = clean_text(
        data.get("prompt", ""),
        12000
    )

    image_data = data.get(
        "image",
        None
    )

    if not prompt and not image_data:

        return jsonify({
            "ok": False,
            "error": "Question vide."
        }), 400

    user_id = get_current_user_id()

    # --------------------------------------------------------
    # MÉMOIRE
    # --------------------------------------------------------

    if prompt and detect_memory_request(prompt):

        memory = extract_memory(prompt)

        save_memory(
            user_id,
            memory
        )

        reply = (
            "C'est enregistré dans ma mémoire persistante."
        )

    else:

        memories = get_memories(
            user_id
        )

        # ----------------------------------------------------
        # RECHERCHE WEB
        # ----------------------------------------------------

        search_results = []

        if prompt and should_search_web(prompt):

            search_results = web_search(
                prompt
            )

        # ----------------------------------------------------
        # IA
        # ----------------------------------------------------

        reply = call_ai(
            prompt,
            memories=memories,
            search_results=search_results,
            image_data=image_data
        )

    # --------------------------------------------------------
    # HISTORIQUE
    # --------------------------------------------------------

    execute(
        """
        INSERT INTO messages
        (user_id, sender, content, timestamp)
        VALUES (?, ?, ?, ?)
        """,
        (
            user_id,
            "User",
            prompt or "[IMAGE]",
            now_string()
        )
    )

    execute(
        """
        INSERT INTO messages
        (user_id, sender, content, timestamp)
        VALUES (?, ?, ?, ?)
        """,
        (
            user_id,
            "Prexis",
            reply,
            now_string()
        )
    )

    return jsonify({
        "ok": True,
        "reply": reply,
        "state": "speaking"
    })


# ============================================================
# 13. HISTORIQUE
# ============================================================

@app.route("/api/messages")
def get_messages():

    rows = execute(
        """
        SELECT sender, content, timestamp
        FROM messages
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 50
        """,
        (
            get_current_user_id(),
        ),
        fetch=True
    )

    rows = list(reversed(rows))

    return jsonify({
        "ok": True,
        "messages": [
            {
                "sender": row["sender"],
                "content": row["content"],
                "timestamp": row["timestamp"]
            }
            for row in rows
        ]
    })


# ============================================================
# 14. MÉMOIRE API
# ============================================================

@app.route("/api/memory")
def memory():

    return jsonify({
        "ok": True,
        "memories": get_memories(
            get_current_user_id()
        )
    })


@app.route(
    "/api/memory/add",
    methods=["POST"]
)
def memory_add():

    data = request.get_json(
        silent=True
    ) or {}

    text = clean_text(
        data.get("memory", ""),
        1000
    )

    if not text:

        return jsonify({
            "ok": False,
            "error": "Mémoire vide."
        }), 400

    save_memory(
        get_current_user_id(),
        text
    )

    return jsonify({
        "ok": True
    })


# ============================================================
# 15. TÂCHES
# ============================================================

@app.route("/api/tasks")
def get_tasks():

    rows = execute(
        """
        SELECT id, title, status, timestamp
        FROM tasks
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 50
        """,
        (
            get_current_user_id(),
        ),
        fetch=True
    )

    return jsonify({
        "ok": True,
        "tasks": [
            {
                "id": row["id"],
                "title": row["title"],
                "status": row["status"],
                "timestamp": row["timestamp"]
            }
            for row in rows
        ]
    })


@app.route(
    "/api/tasks/add",
    methods=["POST"]
)
def add_task():

    data = request.get_json(
        silent=True
    ) or {}

    title = clean_text(
        data.get("title", ""),
        500
    )

    if not title:

        return jsonify({
            "ok": False
        }), 400

    execute(
        """
        INSERT INTO tasks
        (user_id, title, status, timestamp)
        VALUES (?, ?, ?, ?)
        """,
        (
            get_current_user_id(),
            title,
            "En cours",
            now_string()
        )
    )

    return get_tasks()


@app.route(
    "/api/tasks/<int:task_id>/done",
    methods=["POST"]
)
def task_done(task_id):

    execute(
        """
        UPDATE tasks
        SET status = ?
        WHERE id = ?
        AND user_id = ?
        """,
        (
            "Terminée",
            task_id,
            get_current_user_id()
        )
    )

    return jsonify({
        "ok": True
    })


# ============================================================
# 16. NOTES
# ============================================================

@app.route("/api/notes")
def get_notes():

    rows = execute(
        """
        SELECT id, content, timestamp
        FROM notes
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 50
        """,
        (
            get_current_user_id(),
        ),
        fetch=True
    )

    return jsonify({
        "ok": True,
        "notes": [
            {
                "id": row["id"],
                "content": row["content"],
                "timestamp": row["timestamp"]
            }
            for row in rows
        ]
    })


@app.route(
    "/api/notes/add",
    methods=["POST"]
)
def add_note():

    data = request.get_json(
        silent=True
    ) or {}

    content = clean_text(
        data.get("content", ""),
        3000
    )

    if not content:

        return jsonify({
            "ok": False
        }), 400

    execute(
        """
        INSERT INTO notes
        (user_id, content, timestamp)
        VALUES (?, ?, ?)
        """,
        (
            get_current_user_id(),
            content,
            now_string()
        )
    )

    return get_notes()


# ============================================================
# 17. COFFRE
# ============================================================

@app.route("/api/passwords")
def get_passwords():

    rows = execute(
        """
        SELECT id, site, pwd, timestamp
        FROM passwords
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 50
        """,
        (
            get_current_user_id(),
        ),
        fetch=True
    )

    return jsonify({
        "ok": True,
        "passwords": [
            {
                "id": row["id"],
                "site": row["site"],
                "password": decrypt_text(
                    row["pwd"]
                ),
                "timestamp": row["timestamp"]
            }
            for row in rows
        ]
    })


@app.route(
    "/api/passwords/add",
    methods=["POST"]
)
def add_password():

    data = request.get_json(
        silent=True
    ) or {}

    site = clean_text(
        data.get("site", ""),
        300
    )

    password = str(
        data.get("pwd", "")
    )

    if not site or not password:

        return jsonify({
            "ok": False,
            "error": "Site et mot de passe requis."
        }), 400

    encrypted = encrypt_text(
        password
    )

    execute(
        """
        INSERT INTO passwords
        (user_id, site, pwd, timestamp)
        VALUES (?, ?, ?, ?)
        """,
        (
            get_current_user_id(),
            site,
            encrypted,
            now_string()
        )
    )

    return jsonify({
        "ok": True
    })


# ============================================================
# 18. RECHERCHE WEB API
# ============================================================

@app.route(
    "/api/search",
    methods=["POST"]
)
def search_api():

    data = request.get_json(
        silent=True
    ) or {}

    query = clean_text(
        data.get("query", ""),
        500
    )

    results = web_search(
        query
    )

    return jsonify({
        "ok": True,
        "results": results
    })


# ============================================================
# 19. VISION
# ============================================================

@app.route(
    "/api/vision",
    methods=["POST"]
)
def vision():

    data = request.get_json(
        silent=True
    ) or {}

    image = data.get(
        "image",
        ""
    )

    prompt = clean_text(
        data.get(
            "prompt",
            "Analyse cette image."
        ),
        3000
    )

    if not image:

        return jsonify({
            "ok": False,
            "error": "Image manquante."
        }), 400

    reply = call_ai(
        prompt,
        memories=get_memories(
            get_current_user_id()
        ),
        image_data=image
    )

    return jsonify({
        "ok": True,
        "reply": reply
    })


# ============================================================
# 20. DOMOTIQUE
# ============================================================

@app.route("/api/devices")
def devices():

    rows = execute(
        """
        SELECT id, name, webhook, created_at
        FROM devices
        ORDER BY id DESC
        """,
        fetch=True
    )

    return jsonify({
        "ok": True,
        "devices": [
            {
                "id": row["id"],
                "name": row["name"],
                "created_at": row["created_at"]
            }
            for row in rows
        ]
    })


@app.route(
    "/api/devices/add",
    methods=["POST"]
)
def device_add():

    data = request.get_json(
        silent=True
    ) or {}

    name = clean_text(
        data.get("name", ""),
        200
    )

    webhook = clean_text(
        data.get("webhook", ""),
        1000
    )

    if not name or not webhook:

        return jsonify({
            "ok": False,
            "error": "Nom et webhook requis."
        }), 400

    execute(
        """
        INSERT INTO devices
        (name, webhook, created_at)
        VALUES (?, ?, ?)
        """,
        (
            name,
            webhook,
            now_string()
        )
    )

    return jsonify({
        "ok": True
    })


@app.route(
    "/api/devices/<int:device_id>/command",
    methods=["POST"]
)
def device_command(device_id):

    data = request.get_json(
        silent=True
    ) or {}

    command = clean_text(
        data.get("command", ""),
        1000
    )

    rows = execute(
        """
        SELECT webhook
        FROM devices
        WHERE id = ?
        """,
        (
            device_id,
        ),
        fetch=True
    )

    if not rows:

        return jsonify({
            "ok": False,
            "error": "Appareil inconnu."
        }), 404

    webhook = rows[0]["webhook"]

    try:

        response = requests.post(
            webhook,
            json={
                "command": command
            },
            timeout=10
        )

        return jsonify({
            "ok": response.ok,
            "status": response.status_code
        })

    except Exception as e:

        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


# ============================================================
# 21. AGENT LOCAL : HEARTBEAT
# ============================================================

@app.route(
    "/api/agent/heartbeat",
    methods=["POST"]
)
def agent_heartbeat():

    if not is_local_agent_authorized():

        return jsonify({
            "ok": False,
            "error": "Agent non autorisé."
        }), 403

    data = request.get_json(
        silent=True
    ) or {}

    name = clean_text(
        data.get("name", "PC"),
        200
    )

    os_name = clean_text(
        data.get("os", "Unknown"),
        100
    )

    rows = execute(
        """
        SELECT id
        FROM agents
        WHERE token = ?
        """,
        (
            AGENT_TOKEN,
        ),
        fetch=True
    )

    if rows:

        execute(
            """
            UPDATE agents
            SET name = ?,
                last_seen = ?,
                os = ?,
                status = ?
            WHERE token = ?
            """,
            (
                name,
                now_string(),
                os_name,
                "online",
                AGENT_TOKEN
            )
        )

    else:

        execute(
            """
            INSERT INTO agents
            (token, name, last_seen, os, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                AGENT_TOKEN,
                name,
                now_string(),
                os_name,
                "online"
            )
        )

    return jsonify({
        "ok": True
    })


# ============================================================
# 22. AGENT LOCAL : COMMANDES
# ============================================================

@app.route(
    "/api/agent/command",
    methods=["POST"]
)
def create_agent_command():

    data = request.get_json(
        silent=True
    ) or {}

    command = clean_text(
        data.get("command", ""),
        100
    )

    argument = clean_text(
        data.get("argument", ""),
        1000
    )

    if command not in ALLOWED_AGENT_COMMANDS:

        return jsonify({
            "ok": False,
            "error": "Commande non autorisée."
        }), 400

    rows = execute(
        """
        SELECT id
        FROM agents
        WHERE token = ?
        AND status = ?
        """,
        (
            AGENT_TOKEN,
            "online"
        ),
        fetch=True
    )

    if not rows:

        return jsonify({
            "ok": False,
            "error": "Aucun agent local connecté."
        }), 503

    agent_id = rows[0]["id"]

    execute(
        """
        INSERT INTO agent_commands
        (agent_id, command, argument, status, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            agent_id,
            command,
            argument,
            "pending",
            now_string()
        )
    )

    return jsonify({
        "ok": True,
        "message": "Commande envoyée à l'agent local."
    })


@app.route(
    "/api/agent/next"
)
def agent_next():

    if not is_local_agent_authorized():

        return jsonify({
            "ok": False
        }), 403

    rows = execute(
        """
        SELECT id, command, argument
        FROM agent_commands
        WHERE status = ?
        ORDER BY id ASC
        LIMIT 1
        """,
        (
            "pending",
        ),
        fetch=True
    )

    if not rows:

        return jsonify({
            "ok": True,
            "command": None
        })

    row = rows[0]

    execute(
        """
        UPDATE agent_commands
        SET status = ?
        WHERE id = ?
        """,
        (
            "running",
            row["id"]
        )
    )

    return jsonify({
        "ok": True,
        "command": {
            "id": row["id"],
            "command": row["command"],
            "argument": row["argument"]
        }
    })


@app.route(
    "/api/agent/result",
    methods=["POST"]
)
def agent_result():

    if not is_local_agent_authorized():

        return jsonify({
            "ok": False
        }), 403

    data = request.get_json(
        silent=True
    ) or {}

    command_id = data.get(
        "id"
    )

    result = clean_text(
        data.get(
            "result",
            ""
        ),
        5000
    )

    success = bool(
        data.get(
            "ok",
            False
        )
    )

    execute(
        """
        UPDATE agent_commands
        SET status = ?,
            result = ?
        WHERE id = ?
        """,
        (
            "done" if success else "error",
            result,
            command_id
        )
    )

    return jsonify({
        "ok": True
    })


# ============================================================
# 23. STATUT SYSTÈME
# ============================================================

@app.route("/api/status")
def status():

    agent_rows = execute(
        """
        SELECT name, last_seen, os, status
        FROM agents
        WHERE token = ?
        """,
        (
            AGENT_TOKEN,
        ),
        fetch=True
    )

    agent = None

    if agent_rows:

        agent = {
            "name": agent_rows[0]["name"],
            "last_seen": agent_rows[0]["last_seen"],
            "os": agent_rows[0]["os"],
            "status": agent_rows[0]["status"]
        }

    return jsonify({
        "ok": True,
        "prexis": APP_NAME,
        "version": APP_VERSION,
        "ai": bool(AI_API_KEY),
        "web_search": bool(
            BRAVE_SEARCH_API_KEY
        ),
        "database": (
            "PostgreSQL"
            if USE_POSTGRES
            else "SQLite"
        ),
        "agent": agent
    })


# ============================================================
# 24. INTERFACE PRINCIPALE
# ============================================================

HTML_UI = r"""
<!DOCTYPE html>
<html lang="fr">

<head>

<meta charset="UTF-8">

<meta
name="viewport"
content="width=device-width,
initial-scale=1,
maximum-scale=1,
user-scalable=no,
viewport-fit=cover">

<meta name="theme-color" content="#020108">

<title>
PREXIS // CLOUD OVERLORD
</title>

<style>

/* =========================================================
   RESET
========================================================= */

*{
margin:0;
padding:0;
box-sizing:border-box;
-webkit-tap-highlight-color:transparent;
}

html,
body{
width:100%;
height:100%;
overflow:hidden;
background:#020108;
color:#f5f5f7;
font-family:
-apple-system,
BlinkMacSystemFont,
"SF Pro Display",
"Helvetica Neue",
sans-serif;
}

button,
input,
textarea{
font-family:inherit;
}


/* =========================================================
   BACKGROUND
========================================================= */

#canvas-bg{
position:fixed;
inset:0;
width:100vw;
height:100vh;
z-index:0;
pointer-events:none;
}

.noise{
position:fixed;
inset:0;
z-index:1;
pointer-events:none;
opacity:.04;
background-image:
url("data:image/svg+xml,%3Csvg viewBox='0 0 180 180' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.5'/%3E%3C/svg%3E");
}


/* =========================================================
   APP
========================================================= */

.app{
position:relative;
z-index:5;
width:100%;
height:100%;
display:flex;
flex-direction:column;
align-items:center;
padding:
env(safe-area-inset-top)
12px
env(safe-area-inset-bottom)
12px;
}

.shell{
width:100%;
max-width:520px;
height:100%;
display:flex;
flex-direction:column;
}


/* =========================================================
   TOP BAR
========================================================= */

.topbar{
height:52px;
display:flex;
align-items:center;
justify-content:space-between;
gap:10px;
}

.brand{
font-size:12px;
font-weight:900;
letter-spacing:3px;
}

.status-pill{
display:flex;
align-items:center;
gap:7px;
padding:8px 12px;
border-radius:999px;
background:rgba(255,255,255,.07);
border:1px solid rgba(255,255,255,.13);
backdrop-filter:blur(25px);
font-size:9px;
letter-spacing:1px;
}

.status-dot{
width:7px;
height:7px;
border-radius:50%;
background:#00ff9d;
box-shadow:0 0 12px #00ff9d;
}


/* =========================================================
   ORBE
========================================================= */

.orb-zone{
flex:0 0 290px;
display:flex;
align-items:center;
justify-content:center;
position:relative;
}

.orb{
width:270px;
height:270px;
position:relative;
display:flex;
align-items:center;
justify-content:center;
cursor:pointer;
touch-action:manipulation;
}

.orb::before{
content:"";
position:absolute;
width:90px;
height:90px;
border-radius:50%;
background:
radial-gradient(
circle,
rgba(255,255,255,.95),
rgba(255,0,160,.7) 30%,
rgba(90,0,255,.45) 65%,
transparent 75%
);
filter:blur(4px);
box-shadow:
0 0 45px #ff007f,
0 0 100px #7a00ff,
0 0 170px #00c8ff;
animation:core 1.8s infinite ease-in-out;
z-index:5;
}

.core-glass{
position:absolute;
width:65px;
height:65px;
border-radius:50%;
z-index:8;
background:
radial-gradient(
circle at 35% 30%,
white,
#ff58b0 28%,
#8b00ff 70%,
#160026
);
box-shadow:
0 0 35px #ff007f,
0 0 80px #7200ff;
animation:core 1.8s infinite ease-in-out;
}

.wave{
position:absolute;
border-radius:50%;
border:3px solid;
opacity:.9;
pointer-events:none;
animation:wave 2.4s infinite
cubic-bezier(.1,.7,.2,1);
}

.w1{
width:75px;
height:75px;
border-color:#ff007f;
animation-delay:0s;
}

.w2{
width:125px;
height:125px;
border-color:#8b00ff;
animation-delay:.45s;
}

.w3{
width:180px;
height:180px;
border-color:#00bfff;
animation-delay:.9s;
}

.w4{
width:235px;
height:235px;
border-color:#ff00ff;
animation-delay:1.35s;
}

.w5{
width:270px;
height:270px;
border-color:#ff0080;
animation-delay:1.8s;
}

.orb.listening .wave{
animation:
activeWave .65s infinite
cubic-bezier(.1,.9,.2,1);
}

.orb.thinking .wave{
animation:
thinkingWave .8s infinite
linear;
}

.orb.speaking .wave{
animation:
speakingWave .55s infinite
cubic-bezier(.1,.8,.2,1);
}

.orb.error .wave{
animation:
errorWave .4s infinite;
border-color:#ff3355;
}

@keyframes wave{

0%{
transform:scale(.25);
opacity:1;
filter:hue-rotate(0deg);
}

100%{
transform:scale(1.8);
opacity:0;
filter:hue-rotate(280deg);
}
}

@keyframes activeWave{

0%{
transform:scale(.25);
opacity:1;
}

50%{
transform:scale(1.2);
opacity:.8;
}

100%{
transform:scale(2.2);
opacity:0;
}
}

@keyframes thinkingWave{

0%{
transform:scale(.5) rotate(0deg);
opacity:.9;
}

50%{
transform:scale(1.15) rotate(180deg);
opacity:1;
}

100%{
transform:scale(1.9) rotate(360deg);
opacity:0;
}
}

@keyframes speakingWave{

0%{
transform:scale(.5);
opacity:1;
}

50%{
transform:scale(1.5);
opacity:.8;
}

100%{
transform:scale(2.4);
opacity:0;
}
}

@keyframes errorWave{

0%,100%{
transform:scale(.4);
opacity:1;
}

50%{
transform:scale(1.8);
opacity:0;
}
}

@keyframes core{

0%,100%{
transform:scale(.88);
filter:hue-rotate(0deg);
}

50%{
transform:scale(1.18);
filter:hue-rotate(180deg);
}
}

.orb-label{
position:absolute;
bottom:-3px;
font-size:9px;
font-weight:800;
letter-spacing:2px;
opacity:.6;
}


/* =========================================================
   NAVIGATION
========================================================= */

.nav{
display:grid;
grid-template-columns:
repeat(6,1fr);
gap:5px;
margin-bottom:8px;
}

.nav button{
min-width:0;
padding:9px 2px;
border-radius:12px;
border:1px solid rgba(255,255,255,.1);
background:rgba(255,255,255,.045);
color:rgba(255,255,255,.65);
font-size:8px;
font-weight:800;
cursor:pointer;
backdrop-filter:blur(25px);
}

.nav button.active{
background:
rgba(255,0,127,.22);
border-color:
rgba(255,0,127,.6);
color:white;
box-shadow:
0 0 18px rgba(255,0,127,.25);
}


/* =========================================================
   PANELS
========================================================= */

.panel{
flex:1;
min-height:0;
position:relative;
border-radius:23px;
border:1px solid rgba(255,255,255,.13);
background:
linear-gradient(
135deg,
rgba(255,255,255,.085),
rgba(255,255,255,.025)
);
backdrop-filter:blur(35px);
-webkit-backdrop-filter:blur(35px);
box-shadow:
0 25px 70px rgba(0,0,0,.6);
overflow:hidden;
display:none;
flex-direction:column;
}

.panel.active{
display:flex;
}

.panel-header{
height:47px;
display:flex;
align-items:center;
justify-content:space-between;
padding:0 15px;
border-bottom:1px solid rgba(255,255,255,.08);
font-size:9px;
letter-spacing:1.5px;
font-weight:800;
}

.panel-content{
flex:1;
min-height:0;
overflow-y:auto;
padding:12px;
}


/* =========================================================
   CHAT
========================================================= */

.messages{
display:flex;
flex-direction:column;
gap:9px;
}

.message{
max-width:90%;
padding:11px 13px;
border-radius:17px;
font-size:12px;
line-height:1.45;
white-space:pre-wrap;
word-break:break-word;
}

.message.user{
align-self:flex-end;
background:
linear-gradient(
135deg,
rgba(255,0,127,.35),
rgba(115,0,255,.25)
);
border:1px solid rgba(255,0,127,.3);
}

.message.ai{
align-self:flex-start;
background:rgba(255,255,255,.06);
border:1px solid rgba(255,255,255,.1);
}

.message.system{
align-self:center;
font-size:9px;
opacity:.5;
}

.chat-input{
display:flex;
gap:7px;
padding:10px;
border-top:1px solid rgba(255,255,255,.08);
}

.chat-input input{
flex:1;
min-width:0;
padding:12px;
border-radius:15px;
border:1px solid rgba(255,255,255,.12);
background:rgba(0,0,0,.35);
color:white;
outline:none;
font-size:12px;
}

.icon-btn{
width:43px;
height:43px;
border:1px solid rgba(255,255,255,.12);
border-radius:14px;
background:rgba(255,255,255,.07);
color:white;
cursor:pointer;
font-size:16px;
}

.send-btn{
width:60px;
border:0;
border-radius:14px;
background:
linear-gradient(
135deg,
#ff007f,
#7200ff
);
color:white;
font-size:9px;
font-weight:900;
}


/* =========================================================
   LISTES
========================================================= */

.list{
display:flex;
flex-direction:column;
gap:7px;
}

.item{
padding:12px;
border-radius:15px;
background:rgba(255,255,255,.045);
border:1px solid rgba(255,255,255,.07);
}

.item-title{
font-size:12px;
}

.item-meta{
font-size:9px;
opacity:.45;
margin-top:5px;
}

.add-row{
display:flex;
gap:6px;
padding:10px;
border-top:1px solid rgba(255,255,255,.08);
}

.add-row input{
flex:1;
min-width:0;
padding:11px;
border-radius:13px;
border:1px solid rgba(255,255,255,.12);
background:rgba(0,0,0,.3);
color:white;
outline:none;
}

.add-row button{
padding:0 13px;
border:0;
border-radius:13px;
background:rgba(255,0,127,.35);
color:white;
font-weight:800;
}


/* =========================================================
   TOOLS
========================================================= */

.tools-grid{
display:grid;
grid-template-columns:
repeat(2,1fr);
gap:8px;
}

.tool{
padding:16px 10px;
border-radius:17px;
border:1px solid rgba(255,255,255,.1);
background:rgba(255,255,255,.05);
color:white;
font-size:10px;
font-weight:800;
cursor:pointer;
}

.tool:active{
transform:scale(.97);
}


/* =========================================================
   MODAL IMAGE
========================================================= */

.modal{
position:fixed;
inset:0;
z-index:100;
display:none;
align-items:center;
justify-content:center;
padding:20px;
background:rgba(0,0,0,.75);
backdrop-filter:blur(20px);
}

.modal.show{
display:flex;
}

.modal-card{
width:100%;
max-width:450px;
padding:20px;
border-radius:25px;
background:#111019;
border:1px solid rgba(255,255,255,.15);
}

.modal-card h3{
margin-bottom:15px;
}

.modal-card textarea{
width:100%;
height:100px;
padding:12px;
border-radius:14px;
background:#050509;
color:white;
border:1px solid rgba(255,255,255,.15);
resize:none;
outline:none;
}

.modal-actions{
display:flex;
gap:8px;
margin-top:10px;
}

.modal-actions button{
flex:1;
padding:12px;
border-radius:13px;
border:0;
background:rgba(255,255,255,.08);
color:white;
}

.modal-actions button.primary{
background:
linear-gradient(
135deg,
#ff007f,
#7200ff
);
}


/* =========================================================
   DESKTOP
========================================================= */

@media(min-width:700px){

.app{
padding:20px;
}

.shell{
max-width:650px;
}

.orb-zone{
flex-basis:320px;
}

.orb{
width:290px;
height:290px;
}

.w5{
width:290px;
height:290px;
}

}

</style>

</head>

<body>

<canvas id="canvas-bg"></canvas>
<div class="noise"></div>

<div class="app">

<div class="shell">

<!-- ======================================================
     TOP
======================================================= -->

<div class="topbar">

<div class="brand">
PREXIS
</div>

<div class="status-pill">

<div class="status-dot"></div>

<span id="system-status">
CLOUD ONLINE
</span>

</div>

</div>


<!-- ======================================================
     ORBE
======================================================= -->

<div class="orb-zone">

<div
class="orb"
id="orb"
onclick="startVoice()"
>

<div class="wave w1"></div>
<div class="wave w2"></div>
<div class="wave w3"></div>
<div class="wave w4"></div>
<div class="wave w5"></div>

<div class="core-glass"></div>

<div class="orb-label"
id="orb-label">
OVERLORD
</div>

</div>

</div>


<!-- ======================================================
     NAV
======================================================= -->

<div class="nav">

<button
class="active"
onclick="showPanel('chat',this)">
CHAT
</button>

<button
onclick="showPanel('tasks',this)">
TÂCHES
</button>

<button
onclick="showPanel('notes',this)">
NOTES
</button>

<button
onclick="showPanel('memory',this)">
MÉMOIRE
</button>

<button
onclick="showPanel('tools',this)">
OUTILS
</button>

<button
onclick="showPanel('system',this)">
SYSTÈME
</button>

</div>


<!-- ======================================================
     CHAT
======================================================= -->

<section
class="panel active"
id="panel-chat">

<div class="panel-header">

<span>SYNAPSE // JARVIS</span>

<span id="voice-state">
● PRÊT
</span>

</div>

<div
class="panel-content"
id="chat-content">

<div
class="messages"
id="messages">

<div class="message system">
PREXIS V2 // CLOUD OVERLORD
</div>

<div class="message ai">
Bonjour. Je suis PREXIS.
Touche l'orbe pour parler ou écris directement ta question.
</div>

</div>

</div>

<div class="chat-input">

<button
class="icon-btn"
onclick="startVoice()">
🎙️
</button>

<button
class="icon-btn"
onclick="openVision()">
👁️
</button>

<input
id="chat-input"
placeholder="Parle à PREXIS..."
autocomplete="off"
onkeydown="
if(event.key==='Enter'){
sendChat();
}
">

<button
class="send-btn"
onclick="sendChat()">
ENVOYER
</button>

</div>

</section>


<!-- ======================================================
     TÂCHES
======================================================= -->

<section
class="panel"
id="panel-tasks">

<div class="panel-header">
<span>MISSIONS CLOUD</span>
<span>SYNC</span>
</div>

<div
class="panel-content"
id="tasks-content">
</div>

<div class="add-row">

<input
id="task-input"
placeholder="Nouvelle tâche..."
onkeydown="
if(event.key==='Enter'){
addTask();
}
">

<button
onclick="addTask()">
+
</button>

</div>

</section>


<!-- ======================================================
     NOTES
======================================================= -->

<section
class="panel"
id="panel-notes">

<div class="panel-header">
<span>BLOC-NOTES</span>
<span>PERSISTANT</span>
</div>

<div
class="panel-content"
id="notes-content">
</div>

<div class="add-row">

<input
id="note-input"
placeholder="Nouvelle note..."
onkeydown="
if(event.key==='Enter'){
addNote();
}
">

<button
onclick="addNote()">
+
</button>

</div>

</section>


<!-- ======================================================
     MEMOIRE
======================================================= -->

<section
class="panel"
id="panel-memory">

<div class="panel-header">
<span>MÉMOIRE PREXIS</span>
<span>LONG TERME</span>
</div>

<div
class="panel-content"
id="memory-content">
</div>

<div class="add-row">

<input
id="memory-input"
placeholder="Mémoriser..."
onkeydown="
if(event.key==='Enter'){
addMemory();
}
">

<button
onclick="addMemory()">
+
</button>

</div>

</section>


<!-- ======================================================
     OUTILS
======================================================= -->

<section
class="panel"
id="panel-tools">

<div class="panel-header">
<span>OUTILS OVERLORD</span>
<span>LIVE</span>
</div>

<div class="panel-content">

<div class="tools-grid">

<button
class="tool"
onclick="runTool('météo actuelle')">
🌦️ MÉTÉO
</button>

<button
class="tool"
onclick="runTool('Quelle heure est-il ?')">
🕐 HEURE
</button>

<button
class="tool"
onclick="openVision()">
👁️ VISION
</button>

<button
class="tool"
onclick="searchWebPrompt()">
🔎 RECHERCHE
</button>

<button
class="tool"
onclick="askSystemInfo()">
💻 PC LOCAL
</button>

<button
class="tool"
onclick="vibrate()">
📳 VIBRATION
</button>

<button
class="tool"
onclick="speakLast()">
🔊 RELIRE
</button>

</div>

</div>

</section>


<!-- ======================================================
     SYSTEME
======================================================= -->

<section
class="panel"
id="panel-system">

<div class="panel-header">
<span>SYSTÈME</span>
<span>DIAGNOSTIC</span>
</div>

<div
class="panel-content"
id="system-content">

Chargement...

</div>

</section>

</div>

</div>


<!-- ======================================================
     VISION MODAL
======================================================= -->

<div
class="modal"
id="vision-modal">

<div class="modal-card">

<h3>
👁️ Vision Overlord
</h3>

<input
type="file"
id="vision-file"
accept="image/*"
capture="environment"
style="
width:100%;
margin-bottom:12px;
color:white;
">

<textarea
id="vision-prompt"
placeholder="Que veux-tu que PREXIS analyse ?">
Analyse cette image et décris ce que tu observes.
</textarea>

<div class="modal-actions">

<button
onclick="closeVision()">
ANNULER
</button>

<button
class="primary"
onclick="analyzeVision()">
ANALYSER
</button>

</div>

</div>

</div>


<script>

/* =========================================================
   VARIABLES
========================================================= */

let lastReply = "";
let recognition = null;


/* =========================================================
   BACKGROUND
========================================================= */

const canvas =
document.getElementById(
"canvas-bg"
);

const ctx =
canvas.getContext("2d");

let width = 0;
let height = 0;
let tick = 0;

function resizeCanvas(){

width =
canvas.width =
window.innerWidth;

height =
canvas.height =
window.innerHeight;

}

window.addEventListener(
"resize",
resizeCanvas
);

resizeCanvas();


function background(){

ctx.fillStyle =
"#020108";

ctx.fillRect(
0,
0,
width,
height
);

tick += .008;

const horizon =
height * .55;

for(
let i=-18;
i<=18;
i++
){

const x =
width / 2 +
i * 45 +
Math.sin(
tick + i * .3
) * 30;

const mix =
Math.sin(
tick + i
) * 127 + 128;

ctx.strokeStyle =
`rgba(
${255-mix},
40,
${mix},
.18
)`;

ctx.lineWidth = 1;

ctx.beginPath();

ctx.moveTo(
width/2,
horizon
);

ctx.lineTo(
x,
height
);

ctx.stroke();

}

requestAnimationFrame(
background
);

}

background();


/* =========================================================
   ORBE
========================================================= */

function setOrbState(
state,
label
){

const orb =
document.getElementById(
"orb"
);

orb.classList.remove(
"listening",
"thinking",
"speaking",
"error"
);

if(state){

orb.classList.add(
state
);

}

document.getElementById(
"orb-label"
).innerText =
label ||
"OVERLORD";

}


/* =========================================================
   VIBRATION
========================================================= */

function vibrate(){

if(
navigator.vibrate
){

navigator.vibrate(
[
80,
40,
80,
40,
160
]
);

}

setOrbState(
"speaking",
"IMPULSION"
);

setTimeout(
()=>{
setOrbState(
"",
"OVERLORD"
);
},
900
);

}


/* =========================================================
   PANELS
========================================================= */

function showPanel(
id,
button
){

document
.querySelectorAll(
".nav button"
)
.forEach(
b=>b.classList.remove(
"active"
)
);

document
.querySelectorAll(
".panel"
)
.forEach(
p=>p.classList.remove(
"active"
)
);

button.classList.add(
"active"
);

document
.getElementById(
"panel-"+id
)
.classList.add(
"active"
);

if(id==="tasks")
loadTasks();

if(id==="notes")
loadNotes();

if(id==="memory")
loadMemory();

if(id==="system")
loadSystem();

}


/* =========================================================
   CHAT
========================================================= */

function addMessage(
type,
text
){

const container =
document.getElementById(
"messages"
);

const div =
document.createElement(
"div"
);

div.className =
"message " + type;

div.textContent =
text;

container.appendChild(
div
);

const content =
document.getElementById(
"chat-content"
);

content.scrollTop =
content.scrollHeight;

}


async function sendChat(
customPrompt
){

const input =
document.getElementById(
"chat-input"
);

const prompt =
customPrompt ||
input.value.trim();

if(!prompt)
return;

if(!customPrompt)
input.value = "";

addMessage(
"user",
prompt
);

setOrbState(
"thinking",
"RÉFLEXION"
);

document.getElementById(
"voice-state"
).innerText =
"● RÉFLEXION";

try{

const response =
await fetch(
"/api/interact",
{
method:"POST",
headers:{
"Content-Type":
"application/json"
},
body:JSON.stringify({
prompt:prompt
})
}
);

const data =
await response.json();

if(!response.ok){

throw new Error(
data.error ||
"Erreur serveur"
);

}

lastReply =
data.reply;

addMessage(
"ai",
data.reply
);

setOrbState(
"speaking",
"RÉPONSE"
);

speak(
data.reply
);

setTimeout(
()=>{
setOrbState(
"",
"OVERLORD"
);

document.getElementById(
"voice-state"
).innerText =
"● PRÊT";

},
1800
);

}
catch(error){

console.error(
error
);

addMessage(
"system",
"Erreur : " +
error.message
);

setOrbState(
"error",
"ERREUR"
);

}

}


/* =========================================================
   VOIX
========================================================= */

function startVoice(){

if(
!(
"webkitSpeechRecognition"
in window
) &&
!(
"SpeechRecognition"
in window
)
){

alert(
"La reconnaissance vocale n'est pas disponible dans ce navigateur."
);

return;

}

const SpeechRecognition =
window.SpeechRecognition ||
window.webkitSpeechRecognition;

if(recognition){

try{
recognition.stop();
}catch(e){}

}

recognition =
new SpeechRecognition();

recognition.lang =
"fr-FR";

recognition.continuous =
false;

recognition.interimResults =
false;

recognition.maxAlternatives =
1;

setOrbState(
"listening",
"ÉCOUTE"
);

document.getElementById(
"voice-state"
).innerText =
"● ÉCOUTE";

recognition.onresult =
function(event){

const text =
event.results[0][0].transcript;

document.getElementById(
"chat-input"
).value =
text;

setOrbState(
"thinking",
"TRAITEMENT"
);

sendChat();

};

recognition.onerror =
function(event){

console.log(
"Voice error:",
event.error
);

setOrbState(
"error",
"VOIX"
);

};

recognition.onend =
function(){

if(
document.getElementById(
"voice-state"
).innerText
==="● ÉCOUTE"
){

document.getElementById(
"voice-state"
).innerText =
"● PRÊT";

setOrbState(
"",
"OVERLORD"
);

}

};

recognition.start();

}


function speak(text){

if(
!("speechSynthesis" in window)
)
return;

window.speechSynthesis.cancel();

const utterance =
new SpeechSynthesisUtterance(
text
);

utterance.lang =
"fr-FR";

utterance.pitch =
0.55;

utterance.rate =
0.95;

const voices =
window.speechSynthesis
.getVoices();

const preferred =
voices.find(
voice =>
voice.lang
.toLowerCase()
.startsWith("fr") &&
(
voice.name
.toLowerCase()
.includes("thomas") ||
voice.name
.toLowerCase()
.includes("nicolas") ||
voice.name
.toLowerCase()
.includes("paul")
)
);

if(preferred)
utterance.voice =
preferred;

utterance.onstart =
()=>{
setOrbState(
"speaking",
"JARVIS"
);
};

utterance.onend =
()=>{
setOrbState(
"",
"OVERLORD"
);
};

window.speechSynthesis.speak(
utterance
);

}


function speakLast(){

if(lastReply){

speak(
lastReply
);

}

}


/* =========================================================
   TÂCHES
========================================================= */

async function loadTasks(){

const container =
document.getElementById(
"tasks-content"
);

container.innerHTML =
"Chargement...";

try{

const response =
await fetch(
"/api/tasks"
);

const data =
await response.json();

container.innerHTML =
"";

if(
!data.tasks.length
){

container.innerHTML =
"<div class='item'>Aucune mission.</div>";

return;

}

data.tasks.forEach(
task=>{

const item =
document.createElement(
"div"
);

item.className =
"item";

item.innerHTML = `
<div class="item-title">
${escapeHtml(task.title)}
</div>

<div class="item-meta">
${escapeHtml(task.status)}
 ·
${escapeHtml(task.timestamp)}
</div>
`;

item.onclick =
async()=>{
if(task.status !== "Terminée"){
await fetch(
"/api/tasks/" +
task.id +
"/done",
{
method:"POST"
}
);
loadTasks();
}
};

container.appendChild(
item
);

}
);

}
catch(error){

container.innerHTML =
"Impossible de charger les tâches.";

}

}


async function addTask(){

const input =
document.getElementById(
"task-input"
);

const title =
input.value.trim();

if(!title)
return;

input.value = "";

await fetch(
"/api/tasks/add",
{
method:"POST",
headers:{
"Content-Type":
"application/json"
},
body:JSON.stringify({
title:title
})
);

loadTasks();

}


/* =========================================================
   NOTES
========================================================= */

async function loadNotes(){

const container =
document.getElementById(
"notes-content"
);

container.innerHTML =
"Chargement...";

try{

const response =
await fetch(
"/api/notes"
);

const data =
await response.json();

container.innerHTML =
"";

data.notes.forEach(
note=>{

const item =
document.createElement(
"div"
);

item.className =
"item";

item.innerHTML = `
<div class="item-title">
${escapeHtml(note.content)}
</div>

<div class="item-meta">
${escapeHtml(note.timestamp)}
</div>
`;

container.appendChild(
item
);

}
);

}
catch(error){

container.innerHTML =
"Impossible de charger les notes.";

}

}


async function addNote(){

const input =
document.getElementById(
"note-input"
);

const content =
input.value.trim();

if(!content)
return;

input.value = "";

await fetch(
"/api/notes/add",
{
method:"POST",
headers:{
"Content-Type":
"application/json"
},
body:JSON.stringify({
content:content
})
);

loadNotes();

}


/* =========================================================
   MEMOIRE
========================================================= */

async function loadMemory(){

const container =
document.getElementById(
"memory-content"
);

container.innerHTML =
"Chargement...";

try{

const response =
await fetch(
"/api/memory"
);

const data =
await response.json();

container.innerHTML =
"";

if(!data.memories.length){

container.innerHTML =
"<div class='item'>Aucune mémoire.</div>";

return;

}

data.memories.forEach(
memory=>{

const item =
document.createElement(
"div"
);

item.className =
"item";

item.innerHTML = `
<div class="item-title">
🧠 ${escapeHtml(memory.memory)}
</div>

<div class="item-meta">
${escapeHtml(memory.created_at)}
</div>
`;

container.appendChild(
item
);

}
);

}
catch(error){

container.innerHTML =
"Erreur mémoire.";

}

}


async function addMemory(){

const input =
document.getElementById(
"memory-input"
);

const memory =
input.value.trim();

if(!memory)
return;

input.value = "";

await fetch(
"/api/memory/add",
{
method:"POST",
headers:{
"Content-Type":
"application/json"
},
body:JSON.stringify({
memory:memory
})
);

loadMemory();

}


/* =========================================================
   OUTILS
========================================================= */

function runTool(
prompt
){

showChat();

sendChat(
prompt
);

}


function searchWebPrompt(){

const query =
prompt(
"Que veux-tu rechercher sur le Web ?"
);

if(query){

showChat();

sendChat(
"Recherche sur le Web : " +
query
);

}

}


function askSystemInfo(){

showChat();

sendChat(
"Donne-moi les informations disponibles concernant le PC local connecté à PREXIS."
);

}


/* =========================================================
   SYSTEM
========================================================= */

async function loadSystem(){

const container =
document.getElementById(
"system-content"
);

container.innerHTML =
"Diagnostic...";

try{

const response =
await fetch(
"/api/status"
);

const data =
await response.json();

let agentStatus =
"NON CONNECTÉ";

if(
data.agent &&
data.agent.status ===
"online"
){

agentStatus =
"🟢 " +
data.agent.name +
" (" +
data.agent.os +
")";

}

container.innerHTML = `

<div class="item">

<div class="item-title">
PREXIS ${escapeHtml(data.version)}
</div>

<div class="item-meta">
Base : ${escapeHtml(data.database)}
</div>

</div>

<div class="item">

<div class="item-title">
🧠 IA
</div>

<div class="item-meta">
${data.ai ? "🟢 CONFIGURÉE" : "🔴 NON CONFIGURÉE"}
</div>

</div>

<div class="item">

<div class="item-title">
🔎 Recherche Web
</div>

<div class="item-meta">
${data.web_search ? "🟢 ACTIVE" : "⚪ NON CONFIGURÉE"}
</div>

</div>

<div class="item">

<div class="item-title">
💻 Agent local
</div>

<div class="item-meta">
${agentStatus}
</div>

</div>
`;

}
catch(error){

container.innerText =
"Diagnostic indisponible.";

}

}


/* =========================================================
   VISION
========================================================= */

function openVision(){

document
.getElementById(
"vision-modal"
)
.classList.add(
"show"
);

}


function closeVision(){

document
.getElementById(
"vision-modal"
)
.classList.remove(
"show"
);

}


async function analyzeVision(){

const file =
document.getElementById(
"vision-file"
).files[0];

const prompt =
document.getElementById(
"vision-prompt"
).value.trim() ||
"Analyse cette image.";

if(!file){

alert(
"Choisis une image."
);

return;

}

setOrbState(
"thinking",
"VISION"
);

closeVision();

showChat();

addMessage(
"user",
"👁️ Analyse d'une image"
);

try{

const base64 =
await fileToDataURL(
file
);

const response =
await fetch(
"/api/vision",
{
method:"POST",
headers:{
"Content-Type":
"application/json"
},
body:JSON.stringify({
image:base64,
prompt:prompt
})
}
);

const data =
await response.json();

if(!response.ok){

throw new Error(
data.error ||
"Erreur vision"
);

}

lastReply =
data.reply;

addMessage(
"ai",
data.reply
);

speak(
data.reply
);

}
catch(error){

addMessage(
"system",
"Vision : " +
error.message
);

setOrbState(
"error",
"VISION"
);

}

}


function fileToDataURL(file){

return new Promise(
(resolve,reject)=>{

const reader =
new FileReader();

reader.onload =
()=>{
resolve(
reader.result
);
};

reader.onerror =
reject;

reader.readAsDataURL(
file
);

}
);


/* =========================================================
   CHAT TAB
========================================================= */

function showChat(){

const button =
document.querySelector(
".nav button"
);

document
.querySelectorAll(
".nav button"
)
.forEach(
b=>b.classList.remove(
"active"
)
);

document
.querySelectorAll(
".panel"
)
.forEach(
p=>p.classList.remove(
"active"
)
);

button.classList.add(
"active"
);

document
.getElementById(
"panel-chat"
)
.classList.add(
"active"
);

}


/* =========================================================
   HTML SECURITY
========================================================= */

function escapeHtml(
value
){

return String(value)
.replaceAll(
"&",
"&amp;"
)
.replaceAll(
"<",
"&lt;"
)
.replaceAll(
">",
"&gt;"
)
.replaceAll(
'"',
"&quot;"
)
.replaceAll(
"'",
"&#039;"
);

}


/* =========================================================
   INITIALISATION
========================================================= */

window
.speechSynthesis
?.getVoices();

setInterval(
()=>{
loadSystem();
},
15000
);

</script>

</body>
</html>
"""


# ============================================================
# 25. LANCEMENT
# ============================================================

if __name__ == "__main__":

    import sys

    if "--agent" in sys.argv:

        run_local_agent()

    else:

        print()
        print("=" * 65)
        print(" PREXIS V2 // CLOUD OVERLORD")
        print("=" * 65)
        print(
            " Local : "
            f"http://127.0.0.1:{PORT}"
        )
        print(
            " Database :",
            "PostgreSQL"
            if USE_POSTGRES
            else "SQLite"
        )
        print(
            " IA :",
            "ACTIVE"
            if AI_API_KEY
            else "NON CONFIGURÉE"
        )
        print(
            " Web :",
            "ACTIVE"
            if BRAVE_SEARCH_API_KEY
            else "NON CONFIGURÉE"
        )
        print("=" * 65)
        print()

        app.run(
            host="0.0.0.0",
            port=PORT,
            debug=False
        )