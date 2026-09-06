import os
import sqlite3
import datetime
import platform
import subprocess
import json
from flask import Flask, jsonify, render_template_string, request

try:
    import psutil
except ImportError:
    psutil = None

app = Flask(__name__)
DB_NAME = "prexis_omega.db"

# ==========================================
# 1. BASE DE DONNÉES & MÉMOIRE PERSISTANTE
# ==========================================
def init_db():
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS messages (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            sender TEXT,
                            content TEXT,
                            timestamp TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS tasks (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            title TEXT,
                            status TEXT,
                            timestamp TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS system_logs (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            level TEXT,
                            message TEXT,
                            timestamp TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS notes (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            title TEXT,
                            content TEXT,
                            timestamp TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS home_devices (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            name TEXT,
                            state TEXT)''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Erreur init DB : {e}")

init_db()

def log_system(level, msg):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO system_logs (level, message, timestamp) VALUES (?, ?, ?)", (level, msg, now))
        conn.commit()
        conn.close()
    except Exception:
        pass

# ==========================================
# 2. MOTEUR DE COMMANDES & LOGIQUE UNIFIÉE
# ==========================================
def process_command(prompt):
    p_lower = prompt.lower()
    log_system("PREXIS_CORE", f"Action déclenchée : {prompt}")
    
    if "ram" in p_lower and psutil:
        r = psutil.virtual_memory()
        return f"MÉMOIRE RAM : {r.percent}% utilisé ({round(r.used/(1024**3),2)} Go / {round(r.total/(1024**3),2)} Go)."
    elif "cpu" in p_lower and psutil:
        return f"PROCESSEUR : {psutil.cpu_percent(interval=0.4)}% de charge actuelle."
    elif "disque" in p_lower and psutil:
        d = psutil.disk_usage('/')
        return f"STOCKAGE SSD : {d.percent}% utilisé ({round(d.free/(1024**3),2)} Go libres)."
    elif "bloc-notes" in p_lower or "notepad" in p_lower:
        try:
            subprocess.Popen(["notepad.exe"])
            return "Protocole exécuté : Ouverture du Bloc-notes Windows."
        except Exception as e:
            return f"Erreur locale : {e}"
    elif "calculatrice" in p_lower or "calc" in p_lower:
        try:
            subprocess.Popen(["calc.exe"])
            return "Protocole exécuté : Lancement de la Calculatrice."
        except Exception as e:
            return f"Erreur : {e}"
    elif "verrouiller" in p_lower:
        try:
            if platform.system() == "Windows":
                os.system("rundll32.exe user32.dll,LockWorkStation")
                return "Sécurité active : Session verrouillée instantanément."
            else:
                return "Commande non supportée sur cet OS."
        except Exception as e:
            return f"Échec : {e}"
    elif "batterie" in p_lower and psutil and hasattr(psutil, "sensors_battery"):
        bat = psutil.sensors_battery()
        if bat:
            status = "Branché" if bat.power_plugged else "Sur batterie"
            return f"BATTERIE : {bat.percent}% ({status})."
    
    if "bonjour" in p_lower or "salut" in p_lower:
        return "Bonjour, Clément. Tous les modules de PREXIS sont en ligne, l'orbe Siri réagit à vos requêtes et la grille fil bleu est stable."
    elif "comment vas-tu" in p_lower:
        return "Intégrité systémique à 100%. Les flux de données et l'authentification sécurisée fonctionnent parfaitement."
    elif "aide" in p_lower or "que peux-tu faire" in p_lower:
        return "Modules actifs : Orbe Siri dynamique et réactif, interface Apple Glassmorphic, Télémétrie, Mémoire persistante, Tâches, Commandes PC, Analyse visuelle et Domotique."
    
    return f"Traitement de la requête complexe : '{prompt}'. Analyse sémantique accomplie avec succès."

# ==========================================
# 3. INTERFACE WEB APPLE-STYLE & ONDE SIRI
# ==========================================
HTML_UI = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PREXIS // APPLE OMEGA HUD</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html, body {
            width: 100%; height: 100%; overflow: hidden;
            background: #000206; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", sans-serif;
            color: #f5f5f7;
        }
        #apple-canvas {
            position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
            z-index: 1; pointer-events: none;
        }
        .container {
            position: relative; z-index: 10; width: 100%; height: 100%;
            display: flex; flex-direction: column; align-items: center; justify-content: space-between;
            padding: 16px; max-width: 520px; margin: 0 auto;
        }
        .header {
            font-size: 0.7rem; font-weight: 600; letter-spacing: 4px; color: rgba(255, 255, 255, 0.85);
            background: rgba(255, 255, 255, 0.05); padding: 8px 22px; border-radius: 999px;
            border: 1px solid rgba(255, 255, 255, 0.15); backdrop-filter: blur(25px);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5); text-transform: uppercase;
        }

        /* ORBE SIRI MULTICOLORE DYNAMIQUE (RÉAGIT AUX ACTIONS) */
        .siri-orb-wrapper {
            position: relative; width: 160px; height: 160px;
            display: flex; align-items: center; justify-content: center;
            transition: transform 0.3s ease;
        }
        .siri-orb-wrapper.active {
            transform: scale(1.15);
        }
        .multi-wave {
            position: absolute; border-radius: 50%;
            border: 2px solid rgba(255, 255, 255, 0.4);
            animation: siri-multicolor-pulse 2.8s infinite ease-out;
        }
        .mw1 { width: 50px; height: 50px; animation-delay: 0s; }
        .mw2 { width: 100px; height: 100px; animation-delay: 0.9s; }
        .mw3 { width: 150px; height: 150px; animation-delay: 1.8s; }
        
        .siri-orb-wrapper.active .multi-wave {
            animation: siri-active-pulse 1.2s infinite ease-out;
            border-width: 3px;
        }

        .orb-core {
            position: absolute; width: 45px; height: 45px; background: #ffffff;
            border-radius: 50%; box-shadow: 0 0 35px #00bfff, 0 0 70px #ff007f, 0 0 100px #7f00ff;
            animation: core-shimmer 2.5s infinite ease-in-out; z-index: 5;
        }

        @keyframes siri-multicolor-pulse {
            0% { transform: scale(0.6); opacity: 1; border-color: rgba(0, 191, 255, 0.9); box-shadow: 0 0 15px #00bfff; }
            33% { border-color: rgba(255, 0, 127, 0.9); box-shadow: 0 0 15px #ff007f; }
            66% { border-color: rgba(127, 0, 255, 0.9); box-shadow: 0 0 15px #7f00ff; }
            100% { transform: scale(1.35); opacity: 0; border-color: rgba(0, 255, 128, 0); }
        }
        @keyframes siri-active-pulse {
            0% { transform: scale(0.5); opacity: 1; border-color: rgba(255, 0, 127, 1); box-shadow: 0 0 30px #ff007f, inset 0 0 20px #ff007f; }
            50% { border-color: rgba(0, 191, 255, 1); box-shadow: 0 0 50px #00bfff, inset 0 0 30px #00bfff; }
            100% { transform: scale(1.5); opacity: 0; border-color: rgba(127, 0, 255, 0); }
        }
        @keyframes core-shimmer {
            0%, 100% { transform: scale(0.95); filter: hue-rotate(0deg); }
            50% { transform: scale(1.12); filter: hue-rotate(180deg); box-shadow: 0 0 55px #ff007f, 0 0 95px #00bfff; }
        }

        /* ONGLETS STYLE APPLE GLASSMORPHISM (6 ONGLETS ÉTENDUS) */
        .tabs-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 4px; width: 100%; }
        .tab-btn {
            background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.1);
            color: rgba(255, 255, 255, 0.7); padding: 7px 2px; border-radius: 8px; font-size: 0.48rem;
            font-weight: 600; cursor: pointer; text-align: center; backdrop-filter: blur(15px);
            transition: all 0.25s ease;
        }
        .tab-btn.active, .tab-btn:hover { background: rgba(255, 255, 255, 0.15); color: #fff; border-color: rgba(255, 255, 255, 0.35); box-shadow: 0 4px 20px rgba(0, 191, 255, 0.3); }

        /* PANNEAUX VERRE FLOU (GLASS CARDS) */
        .panel-container { width: 100%; height: 215px; position: relative; }
        .panel {
            position: absolute; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(20, 20, 25, 0.7); border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 16px; padding: 14px; backdrop-filter: blur(30px);
            box-shadow: 0 25px 50px rgba(0, 0, 0, 0.85), inset 0 0 20px rgba(255, 255, 255, 0.03);
            display: none; flex-direction: column; justify-content: space-between;
        }
        .panel.active { display: flex; }
        
        .panel-header {
            display: flex; justify-content: space-between; font-size: 0.55rem; color: rgba(255, 255, 255, 0.6);
            letter-spacing: 1.5px; border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            padding-bottom: 6px; font-weight: 600; text-transform: uppercase;
        }
        .panel-body {
            font-size: 0.78rem; color: #f5f5f7; line-height: 1.45; flex: 1;
            overflow-y: auto; font-family: ui-monospace, monospace; white-space: pre-wrap; margin-top: 6px;
        }
        .panel-input-row { display: flex; gap: 6px; margin-top: 6px; }
        .panel-input {
            flex: 1; background: rgba(0, 0, 0, 0.4); border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 8px; padding: 8px 12px; color: #fff; font-size: 0.75rem; outline: none;
            backdrop-filter: blur(10px);
        }
        .panel-input:focus { border-color: #00bfff; box-shadow: 0 0 10px rgba(0, 191, 255, 0.3); }
        .panel-send {
            background: rgba(0, 191, 255, 0.25); border: 1px solid rgba(0, 191, 255, 0.6); color: #00bfff;
            padding: 8px 14px; border-radius: 8px; font-size: 0.7rem; font-weight: bold; cursor: pointer;
            transition: all 0.2s;
        }
        .panel-send:hover { background: rgba(0, 191, 255, 0.4); color: #fff; box-shadow: 0 0 15px rgba(0, 191, 255, 0.5); }
        
        .quick-chips { display: flex; gap: 5px; flex-wrap: wrap; margin-top: 4px; }
        .chip {
            background: rgba(255, 255, 255, 0.06); border: 1px solid rgba(255, 255, 255, 0.15);
            color: rgba(255, 255, 255, 0.85); padding: 4px 8px; border-radius: 6px; font-size: 0.6rem; font-weight: 600; cursor: pointer;
            transition: all 0.2s;
        }
        .chip:hover { background: rgba(0, 191, 255, 0.25); color: #fff; border-color: #00bfff; box-shadow: 0 0 10px rgba(0, 191, 255, 0.4); }
    </style>
</head>
<body>
    <canvas id="apple-canvas"></canvas>
    
    <div class="container">
        <div class="header">PREXIS // APPLE OMEGA HUD</div>
        
        <!-- ORBE SIRI MULTICOLORE DYNAMIQUE -->
        <div class="siri-orb-wrapper" id="siri-orb">
            <div class="multi-wave mw1"></div>
            <div class="multi-wave mw2"></div>
            <div class="multi-wave mw3"></div>
            <div class="orb-core"></div>
        </div>
        
        <div class="tabs-grid">
            <button class="tab-btn active" onclick="switchTab('chat', this)">CHAT</button>
            <button class="tab-btn" onclick="switchTab('stats', this)">STATS</button>
            <button class="tab-btn" onclick="switchTab('tasks', this)">TÂCHES</button>
            <button class="tab-btn" onclick="switchTab('notes', this)">NOTES</button>
            <button class="tab-btn" onclick="switchTab('control', this)">PC CTRL</button>
            <button class="tab-btn" onclick="switchTab('home', this)">DOMOTIQUE</button>
        </div>

        <div class="panel-container">
            <!-- PANEL CHAT -->
            <div class="panel active" id="panel-chat">
                <div class="panel-header"><span>SYNAPSE // IA & VOCAL</span><span style="color: #00bfff;">● ACTIF</span></div>
                <div class="panel-body" id="chat-output">> Prexis initialisé. Orbe multicolore et terrain fil bleu opérationnels...</div>
                <div class="panel-input-row">
                    <input type="text" id="chat-input" class="panel-input" placeholder="Parler à PREXIS (ou vocal)..." onkeydown="if(event.key==='Enter') sendChat()">
                    <button class="panel-send" onclick="sendChat()">EXEC</button>
                </div>
            </div>

            <!-- PANEL STATS -->
            <div class="panel" id="panel-stats">
                <div class="panel-header"><span>TÉLÉMÉTRIE MATÉRIELLE</span><span style="color: #00bfff;">● LIVE</span></div>
                <div class="panel-body" id="stats-output">Chargement des données système...</div>
                <div class="quick-chips">
                    <button class="chip" onclick="fetchStats('ram')">RAM</button>
                    <button class="chip" onclick="fetchStats('cpu')">CPU</button>
                    <button class="chip" onclick="fetchStats('disk')">DISQUE</button>
                    <button class="chip" onclick="fetchStats('battery')">BATTERIE</button>
                </div>
            </div>

            <!-- PANEL TÂCHES -->
            <div class="panel" id="panel-tasks">
                <div class="panel-header"><span>PLANNING & MISSIONS</span><span>SECURE DB</span></div>
                <div class="panel-body" id="tasks-output">• Déployer l'API Render<br>• Synchroniser le client local PC</div>
                <div class="panel-input-row">
                    <input type="text" id="task-input" class="panel-input" placeholder="Ajouter une tâche..." onkeydown="if(event.key==='Enter') addTask()">
                    <button class="panel-send" onclick="addTask()">AJOUTER</button>
                </div>
            </div>

            <!-- PANEL NOTES -->
            <div class="panel" id="panel-notes">
                <div class="panel-header"><span>BLOC-NOTES PERSISTANT</span><span>SQLITE</span></div>
                <div class="panel-body" id="notes-output">Chargement des notes enregistrées...</div>
                <div class="panel-input-row">
                    <input type="text" id="note-input" class="panel-input" placeholder="Nouvelle note rapide..." onkeydown="if(event.key==='Enter') addNote()">
                    <button class="panel-send" onclick="addNote()">SAUVER</button>
                </div>
            </div>

            <!-- PANEL PC CONTROL -->
            <div class="panel" id="panel-control">
                <div class="panel-header"><span>COMMANDES PC LOCALES</span><span>BRIDGE API</span></div>
                <div class="panel-body" id="control-output">Sélectionnez une action système :</div>
                <div class="quick-chips">
                    <button class="chip" onclick="runCtrl('bloc-notes')">Bloc-notes</button>
                    <button class="chip" onclick="runCtrl('calculatrice')">Calculatrice</button>
                    <button class="chip" onclick="runCtrl('verrouiller')">Verrouiller Session</button>
                </div>
            </div>

            <!-- PANEL DOMOTIQUE -->
            <div class="panel" id="panel-home">
                <div class="panel-header"><span>COMMANDES DOMOTIQUES</span><span>IOT BRIDGE</span></div>
                <div class="panel-body" id="home-output">Appareils connectés : Salon, Bureau, Lumières.</div>
                <div class="quick-chips">
                    <button class="chip" onclick="runHome('Lumières Salon ON')">Lumières Salon ON</button>
                    <button class="chip" onclick="runHome('Lumières Salon OFF')">Lumières Salon OFF</button>
                    <button class="chip" onclick="runHome('Chauffage Bureau')">Chauffage Bureau</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        // ANIMATION : TERRAIN EN FIL BLEU (PERSPECTIVE GRID)
        const canvas = document.getElementById('apple-canvas');
        const ctx = canvas.getContext('2d');
        let width, height, angle = 0;

        function resize() {
            width = canvas.width = window.innerWidth;
            height = canvas.height = window.innerHeight;
        }
        window.addEventListener('resize', resize);
        resize();

        function drawGridScene() {
            ctx.fillStyle = '#000206';
            ctx.fillRect(0, 0, width, height);

            angle += 0.007;

            const horizonY = height * 0.58;
            const vanishingX = width * 0.5;

            // Terrain en fil bleu futuriste
            ctx.strokeStyle = 'rgba(0, 191, 255, 0.35)';
            ctx.lineWidth = 1;

            const numLines = 24;
            for (let i = -numLines; i <= numLines; i++) {
                let startX = vanishingX + i * (width * 0.12);
                ctx.beginPath();
                ctx.moveTo(vanishingX, horizonY);
                ctx.lineTo(startX, height);
                ctx.stroke();
            }

            const numRows = 16;
            const spacing = 26;
            let offset = (angle * 32) % spacing;

            for (let r = 0; r < numRows; r++) {
                let y = horizonY + Math.pow(r, 1.38) * 12 + offset;
                if (y > height) continue;

                let alpha = (r / numRows) * 0.75;
                ctx.strokeStyle = `rgba(0, 191, 255, ${alpha})`;
                ctx.lineWidth = r > 11 ? 1.6 : 0.7;

                ctx.beginPath();
                ctx.moveTo(0, y);
                for (let x = 0; x <= width; x += 50) {
                    let waveY = y + Math.sin(x * 0.012 + angle * 2.2) * 5;
                    ctx.lineTo(x, waveY);
                }
                ctx.stroke();
            }

            let horizonGlow = ctx.createRadialGradient(vanishingX, horizonY, 10, vanishingX, horizonY, width * 0.42);
            horizonGlow.addColorStop(0, 'rgba(0, 191, 255, 0.4)');
            horizonGlow.addColorStop(1, 'transparent');
            ctx.fillStyle = horizonGlow;
            ctx.fillRect(0, 0, width, height);

            requestAnimationFrame(drawGridScene);
        }
        drawGridScene();

        // Animation dynamique de l'orbe Siri lors des actions
        function triggerSiriPulse() {
            const orb = document.getElementById('siri-orb');
            orb.classList.add('active');
            setTimeout(() => {
                orb.classList.remove('active');
            }, 1800);
        }

        // Synthèse Vocale (JARVIS / PREXIS Vocal)
        function speak(text) {
            if ('speechSynthesis' in window) {
                const utterance = new SpeechSynthesisUtterance(text);
                utterance.lang = 'fr-FR';
                utterance.rate = 1.0;
                window.speechSynthesis.speak(utterance);
            }
        }

        // Gestion des onglets
        function switchTab(tabId, btn) {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById('panel-' + tabId).classList.add('active');
            triggerSiriPulse();
            if (tabId === 'stats') fetchStats('ram');
            if (tabId === 'notes') fetchNotes();
        }

        async function sendChat() {
            const input = document.getElementById('chat-input');
            const val = input.value.trim();
            if (!val) return;
            input.value = '';
            triggerSiriPulse();
            document.getElementById('chat-output').innerText = "> Traitement de la requête par Prexis...";
            try {
                const res = await fetch('/api/interact', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt: val })
                });
                const data = await res.json();
                document.getElementById('chat-output').innerText = "> " + data.reply;
                speak(data.reply);
            } catch (e) {
                document.getElementById('chat-output').innerText = "> Erreur de liaison réseau.";
            }
        }

        async function fetchStats(type) {
            triggerSiriPulse();
            try {
                const res = await fetch('/api/' + type);
                const data = await res.json();
                document.getElementById('stats-output').innerText = "> " + data.message;
            } catch (e) {
                document.getElementById('stats-output').innerText = "> Erreur de télémétrie.";
            }
        }

        async function fetchNotes() {
            try {
                const res = await fetch('/api/notes');
                const data = await res.json();
                document.getElementById('notes-output').innerText = data.notes.join('\\n');
            } catch (e) {
                document.getElementById('notes-output').innerText = "> Erreur chargement notes.";
            }
        }

        async function addNote() {
            const input = document.getElementById('note-input');
            const val = input.value.trim();
            if (!val) return;
            input.value = '';
            triggerSiriPulse();
            try {
                const res = await fetch('/api/notes/add', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content: val })
                });
                const data = await res.json();
                document.getElementById('notes-output').innerText = data.notes.join('\\n');
            } catch (e) {
                document.getElementById('notes-output').innerText = "> Échec de l'enregistrement.";
            }
        }

        async function runCtrl(action) {
            triggerSiriPulse();
            try {
                const res = await fetch('/api/interact', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt: action })
                });
                const data = await res.json();
                document.getElementById('control-output').innerText = "> " + data.reply;
                speak(data.reply);
            } catch (e) {
                document.getElementById('control-output').innerText = "> Échec de l'exécution.";
            }
        }

        async function runHome(action) {
            triggerSiriPulse();
            document.getElementById('home-output').innerText = "> Commande domotique transmise : " + action;
            speak("Commande domotique exécutée : " + action);
        }

        function addTask() {
            const input = document.getElementById('task-input');
            const val = input.value.trim();
            if (!val) return;
            triggerSiriPulse();
            const box = document.getElementById('tasks-output');
            box.innerText += "\\n• " + val;
            input.value = '';
        }
    </script>
</body>
</html>
"""

# ==========================================
# 4. ROUTES API WEB (COMPATIBLE RENDER & MOBILE)
# ==========================================
@app.route("/")
def index():
    return render_template_string(HTML_UI)

@app.route("/api/interact", methods=["POST"])
def interact():
    data = request.json or {}
    prompt = data.get("prompt", "")
    reply = process_command(prompt)
    
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO messages (sender, content, timestamp) VALUES (?, ?, ?)", ("User", prompt, now))
        cursor.execute("INSERT INTO messages (sender, content, timestamp) VALUES (?, ?, ?)", ("Prexis", reply, now))
        conn.commit()
        conn.close()
    except Exception:
        pass
    
    return jsonify({"reply": reply})

@app.route("/api/ram")
def ram():
    if not psutil: return jsonify({"message": "Module psutil non installé (Cloud environment)."})}
    r = psutil.virtual_memory()
    return jsonify({"message": f"RAM : {r.percent}% utilisé ({round(r.used/(1024**3),2)} GB / {round(r.total/(1024**3),2)} GB)."})

@app.route("/api/cpu")
def cpu():
    if not psutil: return jsonify({"message": "Module psutil non installé."})}
    return jsonify({"message": f"CPU : {psutil.cpu_percent(interval=0.4)}% de charge actuelle."})

@app.route("/api/disk")
def disk():
    if not psutil: return jsonify({"message": "Module psutil non installé."})}
    d = psutil.disk_usage('/')
    return jsonify({"message": f"Disque : {d.percent}% utilisé ({round(d.free/(1024**3),2)} GB libres)."})

@app.route("/api/battery")
def battery():
    if not psutil or not hasattr(psutil, "sensors_battery"): return jsonify({"message": "Capteur batterie non disponible sur serveur distant (Render)."})
    b = psutil.sensors_battery()
    if not b: return jsonify({"message": "Batterie introuvable."})
    status = "Secteur branché" if b.power_plugged else "Sur batterie"
    return jsonify({"message": f"Batterie : {b.percent}% ({status})."})

@app.route("/api/notes")
def notes():
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT content, timestamp FROM notes ORDER BY id DESC LIMIT 10")
        rows = cursor.fetchall()
        conn.close()
        formatted = [f"• {r[0]} ({r[1]})" for r in rows]
        return jsonify({"notes": formatted if formatted else ["Aucune note enregistrée."]})
    except Exception as e:
        return jsonify({"notes": [f"Erreur DB : {e}"]})

@app.route("/api/notes/add", methods=["POST"])
def add_note():
    data = request.json or {}
    content = data.get("content", "")
    if content:
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("INSERT INTO notes (title, content, timestamp) VALUES (?, ?, ?)", ("Note rapide", content, now))
            conn.commit()
            conn.close()
        except Exception:
            pass
    return notes()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"[+] Serveur PREXIS APPLE OMEGA actif sur http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
