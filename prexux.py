import json
import os
import platform
from flask import Flask, jsonify, render_template_string, request

# Essai d'import de psutil, gestion propre si non installé
try:
    import psutil
except ImportError:
    psutil = None

app = Flask(__name__)

MEMORY_FILE = "prexus_memory.json"

def load_memory():
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"user_name": "", "facts": []}

def save_memory(data):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Code HTML / CSS / JS intégré
HTML_CODE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PREXUS - SPACE HUD OS</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html, body {
            width: 100%; height: 100%; overflow: hidden;
            background-color: #030712;
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif;
            color: #ffffff;
        }
        .space-bg {
            position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
            background: 
                radial-gradient(circle at 50% 35%, rgba(0, 150, 255, 0.15) 0%, rgba(3, 7, 18, 0.85) 70%, #030712 100%),
                linear-gradient(rgba(0, 242, 254, 0.04) 1px, transparent 1px),
                linear-gradient(90deg, rgba(0, 242, 254, 0.04) 1px, transparent 1px);
            background-size: 100% 100%, 35px 35px, 35px 35px;
            z-index: 1;
        }
        .ui-wrapper {
            position: relative; z-index: 10; width: 100%; height: 100%;
            display: flex; flex-direction: column; align-items: center; justify-content: space-between;
            padding: 15px 20px;
        }
        h1 {
            font-size: 0.95rem; font-weight: 600; letter-spacing: 6px;
            color: rgba(255, 255, 255, 0.95); text-transform: uppercase;
            background: rgba(255, 255, 255, 0.05); padding: 6px 18px; border-radius: 30px;
            backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(0, 242, 254, 0.25);
            box-shadow: 0 0 20px rgba(0, 242, 254, 0.15);
        }
        #globe-container {
            width: 270px; height: 270px; position: relative;
            display: flex; align-items: center; justify-content: center;
        }
        canvas { background: transparent !important; }
        .hud-target {
            position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
            width: 220px; height: 220px; border: 1px dashed rgba(0, 242, 254, 0.2);
            border-radius: 50%; pointer-events: none;
        }
        .data-orbit-tag {
            position: absolute; font-size: 0.6rem; font-weight: 500; color: #00f2fe;
            background: rgba(3, 7, 18, 0.6); border: 1px solid rgba(0, 242, 254, 0.3);
            padding: 4px 8px; border-radius: 15px; letter-spacing: 1px; pointer-events: none;
            backdrop-filter: blur(15px); -webkit-backdrop-filter: blur(15px);
        }
        #tag-top { top: 5px; right: 0px; }
        #tag-bottom { bottom: 5px; left: 0px; }
        .controls-panel { width: 100%; max-width: 420px; display: flex; flex-direction: column; gap: 8px; }
        .main-tabs { display: flex; gap: 6px; width: 100%; }
        .main-btn {
            flex: 1; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(0, 242, 254, 0.2);
            color: rgba(255, 255, 255, 0.6); padding: 8px 4px; border-radius: 10px;
            font-size: 0.62rem; font-weight: 600; letter-spacing: 1px; cursor: pointer;
            backdrop-filter: blur(15px); -webkit-backdrop-filter: blur(15px); transition: all 0.2s ease;
        }
        .main-btn.active, .main-btn:hover {
            background: rgba(0, 242, 254, 0.25); color: #ffffff; border-color: #00f2fe;
            box-shadow: 0 0 12px rgba(0, 242, 254, 0.3);
        }
        .sub-tabs-container {
            background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(0, 242, 254, 0.15);
            border-radius: 12px; padding: 6px; display: flex; gap: 6px; min-height: 40px;
            align-items: center; justify-content: center;
        }
        .sub-btn {
            flex: 1; background: rgba(0, 242, 254, 0.05); border: 1px solid rgba(0, 242, 254, 0.15);
            color: #00f2fe; padding: 6px 4px; border-radius: 8px; font-size: 0.65rem;
            font-weight: 600; cursor: pointer; transition: all 0.2s ease;
        }
        .sub-btn:hover { background: rgba(0, 242, 254, 0.2); border-color: #00f2fe; }
        .chat-box {
            width: 100%; max-width: 420px; background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(0, 242, 254, 0.25); border-radius: 16px; padding: 12px 14px;
            backdrop-filter: blur(25px); -webkit-backdrop-filter: blur(25px);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
        }
        .console-header {
            display: flex; justify-content: space-between; font-size: 0.6rem; color: #00f2fe;
            letter-spacing: 1.5px; margin-bottom: 6px; border-bottom: 1px solid rgba(0, 242, 254, 0.15);
            padding-bottom: 4px;
        }
        .ai-response { font-size: 0.85rem; color: #ffffff; line-height: 1.4; min-height: 36px; font-family: 'Courier New', Courier, monospace; }
        .chat-input-wrapper { display: flex; gap: 8px; margin-top: 8px; }
        .chat-input {
            flex: 1; background: rgba(0, 0, 0, 0.4); border: 1px solid rgba(0, 242, 254, 0.3);
            border-radius: 8px; padding: 8px 10px; color: #ffffff; font-size: 0.8rem; outline: none;
        }
        .chat-send-btn {
            background: rgba(0, 242, 254, 0.2); border: 1px solid #00f2fe; color: #00f2fe;
            padding: 8px 12px; border-radius: 8px; font-size: 0.75rem; font-weight: bold; cursor: pointer;
        }
    </style>
</head>
<body>
    <div class="space-bg"></div>
    <div class="ui-wrapper">
        <h1>PREXUS CORE</h1>
        <div id="globe-container">
            <div class="hud-target"></div>
            <div class="data-orbit-tag" id="tag-top">NET // ONLINE</div>
            <div class="data-orbit-tag" id="tag-bottom">FEED: READY</div>
        </div>
        <div class="controls-panel">
            <div class="main-tabs">
                <button class="main-btn active" onclick="switchMainTab('ia', this)">IA CHAT</button>
                <button class="main-btn" onclick="switchMainTab('perf', this)">PERF</button>
                <button class="main-btn" onclick="switchMainTab('apps', this)">APPS</button>
                <button class="main-btn" onclick="switchMainTab('power', this)">POWER</button>
            </div>
            <div class="sub-tabs-container" id="subTabs"></div>
        </div>
        <div class="chat-box">
            <div class="console-header">
                <span>PREXUS_OS_v4.0</span>
                <span id="status-indicator">● ONLINE</span>
            </div>
            <p class="ai-response" id="aiText">> Noyau PREXUS prêt...</p>
            <div class="chat-input-wrapper">
                <input type="text" id="userInput" class="chat-input" placeholder="Parler à PREXUS..." onkeydown="if(event.key==='Enter') sendChatMessage()">
                <button class="chat-send-btn" onclick="sendChatMessage()">OK</button>
            </div>
        </div>
    </div>
    <script>
        const container = document.getElementById('globe-container');
        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 1000);
        camera.position.z = 220;
        const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
        renderer.setSize(270, 270);
        renderer.setClearColor(0x000000, 0);
        container.appendChild(renderer.domElement);
        const geometry = new THREE.IcosahedronGeometry(60, 2);
        const wireframeMaterial = new THREE.MeshBasicMaterial({ color: 0x00f2fe, wireframe: true, transparent: true, opacity: 0.85 });
        const globe = new THREE.Mesh(geometry, wireframeMaterial);
        scene.add(globe);
        const ring1Geo = new THREE.RingGeometry(78, 79.5, 64);
        const ring1Mat = new THREE.MeshBasicMaterial({ color: 0x00f2fe, side: THREE.DoubleSide, transparent: true, opacity: 0.9 });
        const ring1 = new THREE.Mesh(ring1Geo, ring1Mat);
        ring1.rotation.x = Math.PI / 3;
        scene.add(ring1);
        let rotSpeed = 0.005;
        function animate() {
            requestAnimationFrame(animate);
            globe.rotation.y += rotSpeed;
            ring1.rotation.z += rotSpeed * 2;
            renderer.render(scene, camera);
        }
        animate();
        const menuData = {
            ia: [
                { label: 'MON PROFIL', action: () => sendQuickChat("Qui suis-je ?") },
                { label: 'MÉMOIRE', action: () => sendQuickChat("Que sais-tu sur moi ?") },
                { label: 'EFFACER', action: () => executeAction('/api/clear_memory') }
            ],
            perf: [
                { label: 'RAM', action: () => executeAction('/api/ram') },
                { label: 'CPU', action: () => executeAction('/api/cpu') },
                { label: 'SYSTEME', action: () => executeAction('/api/sys') }
            ],
            apps: [
                { label: 'CHROME', action: () => executeAction('/api/app/chrome') },
                { label: 'CALCULATRICE', action: () => executeAction('/api/app/calc') },
                { label: 'BLOC-NOTES', action: () => executeAction('/api/app/notepad') }
            ],
            power: [
                { label: 'VERROUILLER', action: () => executeAction('/api/power/lock') },
                { label: 'VEILLE', action: () => executeAction('/api/power/sleep') }
            ]
        };
        function switchMainTab(category, btn) {
            document.querySelectorAll('.main-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const subContainer = document.getElementById('subTabs');
            subContainer.innerHTML = '';
            menuData[category].forEach(item => {
                const subBtn = document.createElement('button');
                subBtn.className = 'sub-btn';
                subBtn.innerText = item.label;
                subBtn.onclick = item.action;
                subContainer.appendChild(subBtn);
            });
        }
        switchMainTab('ia', document.querySelector('.main-btn'));
        let isProcessing = false;
        async function typeWriter(text, speed = 20) {
            const el = document.getElementById('aiText');
            el.innerText = "> ";
            for (let i = 0; i < text.length; i++) {
                el.innerText += text.charAt(i);
                await new Promise(r => setTimeout(r, speed));
            }
        }
        async function sendChatMessage() {
            const input = document.getElementById('userInput');
            const text = input.value.trim();
            if (!text || isProcessing) return;
            input.value = '';
            await handleIaResponse('/api/ask', { text: text });
        }
        async function sendQuickChat(text) {
            if (isProcessing) return;
            await handleIaResponse('/api/ask', { text: text });
        }
        async function executeAction(url) {
            if (isProcessing) return;
            await handleIaResponse(url, null);
        }
        async function handleIaResponse(url, bodyData) {
            isProcessing = true;
            const statusEl = document.getElementById('status-indicator');
            const tagBottom = document.getElementById('tag-bottom');
            rotSpeed = 0.035;
            wireframeMaterial.color.setHex(0xff0055);
            ring1Mat.color.setHex(0xff0055);
            statusEl.innerText = "● PROCESSING...";
            statusEl.style.color = "#ff0055";
            const options = bodyData ? {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(bodyData)
            } : { method: 'GET' };
            try {
                const response = await fetch(url, options);
                const data = await response.json();
                await new Promise(r => setTimeout(r, 400));
                wireframeMaterial.color.setHex(0x00f2fe);
                ring1Mat.color.setHex(0x00f2fe);
                rotSpeed = 0.012;
                statusEl.innerText = "● ONLINE";
                statusEl.style.color = "#00f2fe";
                if (data.tag) tagBottom.innerText = data.tag;
                await typeWriter(data.message);
            } catch (err) {
                wireframeMaterial.color.setHex(0x00f2fe);
                ring1Mat.color.setHex(0x00f2fe);
                statusEl.innerText = "● ONLINE";
                statusEl.style.color = "#00f2fe";
                await typeWriter("Erreur de connexion avec le serveur.");
            }
            rotSpeed = 0.005;
            isProcessing = false;
        }
    </script>
</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(HTML_CODE)

@app.route("/api/ask", methods=["POST"])
def ask_ai():
    user_input = request.json.get("text", "").strip() if request.json else ""
    memory = load_memory()
    low_input = user_input.lower()
    if "je m'appelle" in low_input or "mon nom est" in low_input:
        name = user_input.split()[-1].capitalize()
        memory["user_name"] = name
        save_memory(memory)
        reply = f"Compris. Content de te revoir {name} !"
    elif "souviens-toi" in low_input or "retiens" in low_input:
        memory["facts"].append(user_input)
        save_memory(memory)
        reply = "Information sauvegardée dans ma mémoire à long terme."
    elif "qui suis-je" in low_input or "mon prénom" in low_input:
        name = memory.get("user_name")
        reply = f"Tu es {name}." if name else "Je ne connais pas encore ton prénom. Dis-moi 'Je m'appelle...' !"
    elif "que sais-tu" in low_input or "mémoire" in low_input:
        facts = memory.get("facts", [])
        name = memory.get("user_name", "Inconnu")
        reply = f"Utilisateur : {name}. Données enregistrées : {', '.join(facts) if facts else 'Aucune'}."
    else:
        name = memory.get("user_name")
        prefix = f"{name}, " if name else ""
        reply = f"{prefix}commande analysée avec succès."
    return jsonify({"message": f"PREXUS : {reply}", "tag": "AI: CHAT"})

@app.route("/api/clear_memory")
def clear_memory():
    save_memory({"user_name": "", "facts": []})
    return jsonify({"message": "PREXUS : Mémoire réinitialisée.", "tag": "MEM: RESET"})

@app.route("/api/ram")
def get_ram():
    if not psutil:
        return jsonify({"message": "RAM : Installe psutil ('pip install psutil') pour voir les infos.", "tag": "RAM: N/A"})
    ram = psutil.virtual_memory()
    used_gb = round(ram.used / (1024**3), 1)
    total_gb = round(ram.total / (1024**3), 1)
    return jsonify({"message": f"RAM : {ram.percent}% ({used_gb} GB / {total_gb} GB)", "tag": f"RAM: {ram.percent}%"})

@app.route("/api/cpu")
def get_cpu():
    if not psutil:
        return jsonify({"message": "CPU : Installe psutil ('pip install psutil') pour voir les infos.", "tag": "CPU: N/A"})
    cpu = psutil.cpu_percent(interval=0.5)
    return jsonify({"message": f"CPU : Charge à {cpu}% ({psutil.cpu_count()} cœurs).", "tag": f"CPU: {cpu}%"})

@app.route("/api/sys")
def get_sys():
    return jsonify({"message": f"SYSTEME : {platform.node()} sous {platform.system()} {platform.release()}.", "tag": "OS: OK"})

@app.route("/api/app/<app_name>")
def launch_app(app_name):
    if app_name == "chrome":
        os.system("start chrome")
        msg = "Lancement de Google Chrome..."
    elif app_name == "calc":
        os.system("start calc")
        msg = "Lancement de la Calculatrice..."
    elif app_name == "notepad":
        os.system("start notepad")
        msg = "Lancement du Bloc-notes..."
    else:
        msg = "Application inconnue."
    return jsonify({"message": f"PREXUS : {msg}", "tag": "APP: OPEN"})

@app.route("/api/power/<action>")
def power_action(action):
    if action == "lock":
        os.system("rundll32.exe user32.dll,LockWorkStation")
        msg = "Verrouillage de la session..."
    elif action == "sleep":
        os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
        msg = "Mise en veille du système..."
    else:
        msg = "Action inconnue."
    return jsonify({"message": f"PREXUS : {msg}", "tag": "PWR: EXEC"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
