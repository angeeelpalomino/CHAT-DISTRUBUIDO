import json
import os
import threading
import time
import uuid
import psycopg
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session, url_for


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
ONLINE_TIMEOUT = 15
MAX_HISTORY = 200

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://chatuser:chat123@127.0.0.1:5432/chatdb",
)

DEFAULT_CONFIG = {
    "app_name": "Chat Distribuido",
    "welcome": "Bienvenidos a Sistemas Distribuidos",
    "max_message_length": 500,
    "rooms": [
        {"id": "general", "name": "General"},
        {"id": "sala-1", "name": "Sala 1"},
        {"id": "sala-2", "name": "Sala 2"},
        {"id": "sala-3", "name": "Sala 3"},
    ],
    "theme": {
        "accent": "#5865f2",
        "background": "#313338",
        "sidebar": "#1e1f22",
        "panel": "#2b2d31",
        "text": "#f2f3f5",
        "muted": "#b5bac1",
    },
}

app = Flask(
    __name__,
    template_folder=str(BASE_DIR / "templates"),
    static_folder=str(BASE_DIR / "static"),
)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


@app.after_request
def disable_browser_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

app.secret_key = os.environ.get(
    "CHAT_SECRET_KEY",
    "chat-distribuido-aula-cambiar-en-produccion",
)

state_lock = threading.RLock()
clients = {}
messages = {}
config_cache = DEFAULT_CONFIG.copy()
config_mtime = None


def now_text():
    return datetime.now().strftime("%H:%M:%S")


def get_db():
    return psycopg.connect(DATABASE_URL)


def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id VARCHAR(32) PRIMARY KEY,
                    type VARCHAR(20) NOT NULL,
                    username VARCHAR(30),
                    message TEXT NOT NULL,
                    room VARCHAR(100) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

    print("[DB] Base de datos lista")


def save_message(packet):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO messages
                    (id, type, username, message, room)
                VALUES
                    (%s, %s, %s, %s, %s)
                """,
                (
                    packet["id"],
                    packet["type"],
                    packet.get("user"),
                    packet["message"],
                    packet["room"],
                ),
            )


def load_messages(room_id, limit=200):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    type,
                    username,
                    message,
                    room,
                    created_at
                FROM messages
                WHERE room = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (room_id, limit),
            )

            rows = cur.fetchall()

    history = []

    for row in reversed(rows):
        history.append({
            "id": row[0],
            "type": row[1],
            "user": row[2],
            "message": row[3],
            "room": row[4],
            "time": row[5].strftime("%H:%M:%S"),
        })

    return history


def slugify_room(value):
    text = str(value or "").strip().lower()
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ñ": "n",
        " ": "-",
        "_": "-",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return "".join(
        character
        for character in text
        if character.isalnum() or character == "-"
    ).strip("-")


def normalize_rooms(raw_rooms):
    normalized = []
    used_ids = set()

    for index, room in enumerate(raw_rooms or []):
        if isinstance(room, dict):
            name = str(room.get("name", "")).strip()
            room_id = slugify_room(room.get("id") or name)
        else:
            name = str(room).strip()
            room_id = slugify_room(name)

        if not name:
            continue
        if not room_id:
            room_id = f"sala-{index + 1}"
        if room_id in used_ids:
            continue

        used_ids.add(room_id)
        normalized.append({"id": room_id, "name": name})

    general = next(
        (room for room in normalized if room["id"] == "general"),
        None,
    )
    if general is None:
        normalized.insert(0, {"id": "general", "name": "General"})
    else:
        normalized.remove(general)
        normalized.insert(0, general)

    return normalized


def validated_config(raw):
    config = {
        "app_name": str(
            raw.get("app_name", DEFAULT_CONFIG["app_name"])
        ).strip() or DEFAULT_CONFIG["app_name"],
        "welcome": str(
            raw.get("welcome", DEFAULT_CONFIG["welcome"])
        ).strip(),
        "max_message_length": max(
            1,
            min(
                int(
                    raw.get(
                        "max_message_length",
                        DEFAULT_CONFIG["max_message_length"],
                    )
                ),
                5000,
            ),
        ),
        "rooms": normalize_rooms(
            raw.get("rooms", DEFAULT_CONFIG["rooms"])
        ),
        "theme": {
            **DEFAULT_CONFIG["theme"],
            **(
                raw.get("theme", {})
                if isinstance(raw.get("theme"), dict)
                else {}
            ),
        },
    }
    return config


def load_config(force=False):
    global config_cache, config_mtime

    try:
        current_mtime = CONFIG_PATH.stat().st_mtime_ns
    except OSError:
        current_mtime = None

    if not force and current_mtime == config_mtime:
        return config_cache

    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        new_config = validated_config(raw)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"[CONFIG ERROR] {exc}")
        return config_cache

    with state_lock:
        valid_rooms = {room["id"] for room in new_config["rooms"]}
        for room_id in valid_rooms:
            messages.setdefault(room_id, [])
        for client in clients.values():
            if client["room"] not in valid_rooms:
                client["room"] = "general"

        config_cache = new_config
        config_mtime = current_mtime

    print("[CONFIG] Configuracion actualizada")
    return config_cache


def asset_version():
    paths = [
        BASE_DIR / "templates" / "index.html",
        BASE_DIR / "templates" / "login.html",
        BASE_DIR / "static" / "style.css",
        BASE_DIR / "static" / "app.js",
    ]
    values = []
    for path in paths:
        try:
            values.append(path.stat().st_mtime_ns)
        except OSError:
            values.append(0)
    return str(max(values))


def add_system_message(room_id, text):
    packet = {
        "id": uuid.uuid4().hex,
        "type": "system",
        "message": text,
        "time": now_text(),
        "room": room_id,
    }
    messages.setdefault(room_id, []).append(packet)
    messages[room_id] = messages[room_id][-MAX_HISTORY:]


def active_client(update_seen=True):
    client_id = session.get("client_id")
    if not client_id:
        return None

    with state_lock:
        client = clients.get(client_id)
        if client and update_seen:
            client["last_seen"] = time.time()
        return client


def state_for_client(client):
    config = load_config()
    current_time = time.time()

    with state_lock:
        online_clients = [
            value
            for value in clients.values()
            if current_time - value["last_seen"] <= ONLINE_TIMEOUT
        ]

        room_counts = {
            room["id"]: sum(
                1
                for value in online_clients
                if value["room"] == room["id"]
            )
            for room in config["rooms"]
        }

        room_list = [
            {
                **room,
                "online": room_counts.get(room["id"], 0),
            }
            for room in config["rooms"]
        ]

        user_list = sorted(
            [
                {
                    "user": value["username"],
                    "room": value["room"],
                    "online": True,
                }
                for value in online_clients
            ],
            key=lambda value: value["user"].lower(),
        )

        room_id = client["room"]
        history = list(messages.get(room_id, []))

    room_name = next(
        (
            room["name"]
            for room in config["rooms"]
            if room["id"] == room_id
        ),
        room_id,
    )

    return {
        "ok": True,
        "username": client["username"],
        "current_room": room_id,
        "current_room_name": room_name,
        "rooms": room_list,
        "users": user_list,
        "messages": history,
        "config": config,
        "asset_version": asset_version(),
    }


def cleanup_loop():
    while True:
        time.sleep(3)
        cutoff = time.time() - ONLINE_TIMEOUT
        expired = []

        with state_lock:
            for client_id, client in list(clients.items()):
                if client["last_seen"] < cutoff:
                    expired.append(clients.pop(client_id))

            for client in expired:
                add_system_message(
                    client["room"],
                    f'{client["username"]} se desconecto',
                )

        for client in expired:
            print(f'[WEB DISCONNECTED] {client["username"]}')


@app.get("/")
def index():
    if active_client() is None:
        return redirect(url_for("login"))
    return render_template(
        "index.html",
        asset_version=asset_version(),
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    config = load_config()
    error = ""

    if request.method == "POST":
        username = str(request.form.get("username", "")).strip()
        if not username:
            error = "Escribe tu nombre"
        elif len(username) > 30:
            error = "El nombre no puede superar 30 caracteres"
        else:
            client_id = uuid.uuid4().hex
            session.clear()
            session["client_id"] = client_id
            session.permanent = True

            with state_lock:
                clients[client_id] = {
                    "username": username,
                    "room": "general",
                    "last_seen": time.time(),
                }
                add_system_message(
                    "general",
                    f"{username} se ha conectado",
                )

            print(f"[WEB CONNECTED] {username}")
            return redirect(url_for("index"))

    return render_template(
        "login.html",
        config=config,
        error=error,
        asset_version=asset_version(),
    )


@app.post("/logout")
def logout():
    client_id = session.pop("client_id", None)
    if client_id:
        with state_lock:
            client = clients.pop(client_id, None)
            if client:
                add_system_message(
                    client["room"],
                    f'{client["username"]} se desconecto',
                )
                print(f'[WEB DISCONNECTED] {client["username"]}')
    return redirect(url_for("login"))


@app.get("/api/state")
def api_state():
    client = active_client()
    if client is None:
        return jsonify({"ok": False, "login_required": True}), 401
    return jsonify(state_for_client(client))


@app.post("/api/join")
def api_join():
    client = active_client()
    if client is None:
        return jsonify({"ok": False, "login_required": True}), 401

    config = load_config()
    data = request.get_json(silent=True) or {}
    room_id = slugify_room(data.get("room"))
    valid_rooms = {room["id"] for room in config["rooms"]}
    if room_id not in valid_rooms:
        return jsonify({"ok": False, "error": "La sala no existe"}), 400

    with state_lock:
        previous_room = client["room"]
        if previous_room != room_id:
            client["room"] = room_id
            add_system_message(
                room_id,
                f'{client["username"]} entro a la sala',
            )

    return jsonify({"ok": True, "room": room_id})


@app.post("/api/leave")
def api_leave():
    client = active_client()
    if client is None:
        return jsonify({"ok": False, "login_required": True}), 401

    with state_lock:
        client["room"] = "general"
        add_system_message(
            "general",
            f'{client["username"]} regreso a General',
        )

    return jsonify({"ok": True, "room": "general"})


@app.post("/api/send")
def api_send():
    client = active_client()
    if client is None:
        return jsonify({"ok": False, "login_required": True}), 401

    config = load_config()
    data = request.get_json(silent=True) or {}
    text = str(data.get("message", "")).strip()
    if not text:
        return jsonify({"ok": False, "error": "Mensaje vacio"}), 400
    if len(text) > config["max_message_length"]:
        return jsonify({
            "ok": False,
            "error": (
                "El mensaje supera "
                f'{config["max_message_length"]} caracteres'
            ),
        }), 400

    with state_lock:
        room_id = client["room"]
        packet = {
            "id": uuid.uuid4().hex,
            "type": "message",
            "user": client["username"],
            "message": text,
            "time": now_text(),
            "room": room_id,
        }
        messages.setdefault(room_id, []).append(packet)
        messages[room_id] = messages[room_id][-MAX_HISTORY:]

    return jsonify({"ok": True})


@app.get("/health")
def health():
    return jsonify({"ok": True, "time": now_text()})


if __name__ == "__main__":
    load_config(force=True)
    threading.Thread(target=cleanup_loop, daemon=True).start()
    print("[WEB SERVER] http://0.0.0.0:5000")
    print("[WEB LAN] Comparte http://TU_IP:5000")
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        threaded=True,
        use_reloader=False,
    )
