import os
import json
import shutil
import zipfile
import hashlib
import secrets
import io
from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import FastAPI, File, UploadFile, Form, Depends, HTTPException, status, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# ---------- Конфиг ----------
CONFIG_FILE = "config.json"
FILES_DIR = "files"
UPLOAD_DIR = "uploads"
DEFAULT_CONFIG = {
    "admin_key": "admin123",
    "password": "HoL88Po1mOk",
    "version": "2.0",
    "files_checksum": "",
    "jwt_secret": secrets.token_hex(32),
    "downloads_count": 0
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        os.makedirs(FILES_DIR, exist_ok=True)
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=4)

config = load_config()

# ---------- JWT ----------
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, config["jwt_secret"], algorithm=ALGORITHM)

def verify_token(token: str):
    try:
        payload = jwt.decode(token, config["jwt_secret"], algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None

# ---------- Security ----------
security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return payload

# ---------- App ----------
app = FastAPI(title="Rage Server")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Helpers ----------
def compute_files_checksum():
    if not os.path.exists(FILES_DIR):
        return ""
    hash_md5 = hashlib.md5()
    for root, dirs, files in sorted(os.walk(FILES_DIR)):
        for fname in sorted(files):
            path = os.path.join(root, fname)
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
    return hash_md5.hexdigest()

def update_checksum():
    cfg = load_config()
    cfg["files_checksum"] = compute_files_checksum()
    save_config(cfg)

def safe_extract_zip(zip_path):
    """Распаковывает zip во временную папку, затем заменяет FILES_DIR."""
    temp_dir = os.path.join(UPLOAD_DIR, "temp_extract")
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        # Если распаковалось успешно, заменяем основную папку
        if os.path.exists(FILES_DIR):
            shutil.rmtree(FILES_DIR)
        shutil.move(temp_dir, FILES_DIR)
        update_checksum()
    except Exception as e:
        # Если ошибка, удаляем временную папку и пробрасываем исключение
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise e

# ---------- Models ----------
class AuthRequest(BaseModel):
    key: str

class ConfigUpdate(BaseModel):
    password: str

# ---------- API Endpoints ----------
@app.post("/api/auth")
async def auth(auth: AuthRequest):
    if auth.key != config["admin_key"]:
        return JSONResponse(status_code=401, content={"error": "Invalid key"})
    token = create_access_token({"sub": "admin"})
    return {"status": "ok", "token": token}

@app.get("/api/v1/config")
async def get_config(user=Depends(get_current_user)):
    return {
        "password": config["password"],
        "version": config["version"],
        "key": config["admin_key"]
    }

@app.post("/api/v1/config")
async def update_config(update: ConfigUpdate, user=Depends(get_current_user)):
    cfg = load_config()
    cfg["password"] = update.password
    save_config(cfg)
    return {"status": "ok"}

@app.get("/api/v1/files")
async def download_files(user=Depends(get_current_user)):
    # увеличиваем счетчик загрузок
    cfg = load_config()
    cfg["downloads_count"] = cfg.get("downloads_count", 0) + 1
    save_config(cfg)

    # Создаём архив в памяти
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zipf:
        if os.path.exists(FILES_DIR):
            for root, dirs, files in os.walk(FILES_DIR):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, FILES_DIR)
                    zipf.write(file_path, arcname)
    zip_buffer.seek(0)
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=files.zip"}
    )

@app.post("/api/v1/files")
async def upload_files(file: UploadFile = File(...), user=Depends(get_current_user)):
    # Проверка размера (50MB)
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 50MB)")
    # Сохраняем временный zip
    temp_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(temp_path, "wb") as f:
        f.write(content)
    # Распаковываем с безопасной заменой
    try:
        safe_extract_zip(temp_path)
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    return {"status": "ok"}

@app.get("/api/v1/status")
async def get_status(user=Depends(get_current_user)):
    files = []
    if os.path.exists(FILES_DIR):
        files = [f for f in os.listdir(FILES_DIR) if os.path.isfile(os.path.join(FILES_DIR, f))]
    return {
        "online": True,
        "version": config["version"],
        "files_count": len(files),
        "password": "****",
        "downloads_count": config.get("downloads_count", 0)
    }

@app.get("/api/v1/files/list")
async def list_files(user=Depends(get_current_user)):
    if not os.path.exists(FILES_DIR):
        return {"files": []}
    files = [f for f in os.listdir(FILES_DIR) if os.path.isfile(os.path.join(FILES_DIR, f))]
    return {"files": files}

# ---------- GUI (HTML) ----------
HTML_LOGIN = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Rage Admin</title>
    <style>
        body { background: #1a1a2e; color: #eee; font-family: 'Segoe UI', Consolas, monospace; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-box { background: #16213e; padding: 40px; border-radius: 8px; box-shadow: 0 0 20px #e94560; width: 300px; }
        input { width: 100%; padding: 12px; margin: 10px 0; background: #0f3460; border: none; color: #fff; border-radius: 4px; font-size: 16px; }
        button { width: 100%; padding: 12px; background: #e94560; border: none; color: #fff; font-weight: bold; border-radius: 4px; cursor: pointer; font-size: 16px; }
        button:hover { background: #c73652; }
        .error { color: #e94560; margin-top: 10px; text-align: center; }
        .title { text-align: center; font-size: 24px; margin-bottom: 20px; color: #e94560; }
    </style>
</head>
<body>
    <div class="login-box">
        <div class="title">RAGE ADMIN</div>
        <input type="text" id="key" placeholder="Введите ключ доступа">
        <button onclick="login()">Войти</button>
        <div id="error" class="error"></div>
    </div>
    <script>
        async function login() {
            const key = document.getElementById('key').value;
            const resp = await fetch('/api/auth', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({key: key})
            });
            const data = await resp.json();
            if (resp.ok) {
                localStorage.setItem('token', data.token);
                window.location.href = '/dashboard';
            } else {
                document.getElementById('error').innerText = 'Неверный ключ!';
            }
        }
    </script>
</body>
</html>
"""

HTML_DASHBOARD = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Панель управления</title>
    <style>
        body { background: #1a1a2e; color: #eee; font-family: 'Segoe UI', Consolas, monospace; padding: 20px; }
        .container { max-width: 1000px; margin: 0 auto; }
        .card { background: #16213e; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 0 10px rgba(233,69,96,0.3); }
        h2 { color: #e94560; margin-top: 0; }
        .row { display: flex; flex-wrap: wrap; gap: 20px; }
        .col { flex: 1; min-width: 200px; }
        .btn { background: #e94560; border: none; color: #fff; padding: 10px 20px; border-radius: 4px; cursor: pointer; margin-right: 10px; }
        .btn:hover { background: #c73652; }
        .btn-secondary { background: #0f3460; }
        .btn-secondary:hover { background: #1a4a7a; }
        input[type="file"] { display: none; }
        .file-label { background: #0f3460; padding: 10px 20px; border-radius: 4px; cursor: pointer; display: inline-block; }
        .file-label:hover { background: #1a4a7a; }
        .file-list { list-style: none; padding: 0; }
        .file-list li { background: #0f3460; margin: 5px 0; padding: 8px; border-radius: 4px; }
        .status-item { display: inline-block; margin-right: 20px; }
        .password-container { display: flex; align-items: center; gap: 10px; }
        .password-container input { background: #0f3460; border: none; color: #fff; padding: 8px; border-radius: 4px; width: 200px; }
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); justify-content: center; align-items: center; }
        .modal-content { background: #16213e; padding: 30px; border-radius: 8px; width: 300px; }
        .modal-content input { width: 100%; margin: 10px 0; }
        .modal-content button { width: 100%; }
        .close { float: right; cursor: pointer; font-size: 24px; color: #e94560; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Панель управления</h1>
        <div id="status" class="card">
            <h2>Статус</h2>
            <div id="statusData">Загрузка...</div>
        </div>
        <div class="card">
            <h2>Пароль локера</h2>
            <div class="password-container">
                <input type="password" id="passwordDisplay" value="****" disabled>
                <button class="btn btn-secondary" onclick="togglePassword()">Показать</button>
                <button class="btn" onclick="openChangePassword()">Сменить пароль</button>
            </div>
        </div>
        <div class="card">
            <h2>Загрузка ZIP</h2>
            <input type="file" id="zipFile" accept=".zip" onchange="document.getElementById('fileName').innerText = this.files[0].name">
            <label class="file-label" for="zipFile">Выбрать архив</label>
            <span id="fileName">Файл не выбран</span>
            <button class="btn" onclick="uploadZip()" style="margin-left: 10px;">Загрузить</button>
            <div id="uploadStatus"></div>
        </div>
        <div class="card">
            <h2>Файлы в resources</h2>
            <ul id="fileList" class="file-list">Загрузка...</ul>
            <button class="btn" onclick="downloadZip()">Скачать текущий ZIP</button>
        </div>
    </div>

    <!-- Модалка смены пароля -->
    <div id="passwordModal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeModal()">&times;</span>
            <h3>Новый пароль</h3>
            <input type="text" id="newPassword" placeholder="Введите новый пароль">
            <button onclick="changePassword()">Сохранить</button>
        </div>
    </div>

    <script>
        const token = localStorage.getItem('token');
        if (!token) window.location.href = '/';

        async function apiFetch(url, options = {}) {
            const resp = await fetch(url, {
                ...options,
                headers: { 'Authorization': `Bearer ${token}`, ...options.headers }
            });
            if (resp.status === 401) {
                localStorage.removeItem('token');
                window.location.href = '/';
            }
            return resp;
        }

        async function loadStatus() {
            const resp = await apiFetch('/api/v1/status');
            const data = await resp.json();
            document.getElementById('statusData').innerHTML = `
                <span class="status-item">Версия: ${data.version}</span>
                <span class="status-item">Файлов: ${data.files_count}</span>
                <span class="status-item">Загрузок: ${data.downloads_count}</span>
                <span class="status-item">Статус: ${data.online ? '🟢 Онлайн' : '🔴 Офлайн'}</span>
            `;
        }

        async function loadFileList() {
            const resp = await apiFetch('/api/v1/files/list');
            if (resp.ok) {
                const data = await resp.json();
                const ul = document.getElementById('fileList');
                ul.innerHTML = data.files.map(f => `<li>${f}</li>`).join('');
            } else {
                document.getElementById('fileList').innerHTML = 'Ошибка загрузки';
            }
        }

        let passwordVisible = false;
        function togglePassword() {
            const input = document.getElementById('passwordDisplay');
            if (passwordVisible) {
                input.type = 'password';
                input.value = '****';
                passwordVisible = false;
            } else {
                apiFetch('/api/v1/config').then(resp => resp.json()).then(data => {
                    input.type = 'text';
                    input.value = data.password;
                    passwordVisible = true;
                });
            }
        }

        function openChangePassword() {
            document.getElementById('passwordModal').style.display = 'flex';
        }

        function closeModal() {
            document.getElementById('passwordModal').style.display = 'none';
        }

        async function changePassword() {
            const newPass = document.getElementById('newPassword').value;
            if (!newPass) return alert('Введите пароль');
            const resp = await apiFetch('/api/v1/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({password: newPass})
            });
            if (resp.ok) {
                alert('Пароль изменён');
                closeModal();
                document.getElementById('passwordDisplay').value = '****';
                passwordVisible = false;
                document.getElementById('passwordDisplay').type = 'password';
            } else {
                alert('Ошибка');
            }
        }

        async function uploadZip() {
            const fileInput = document.getElementById('zipFile');
            if (!fileInput.files.length) return alert('Выберите ZIP');
            const file = fileInput.files[0];
            const formData = new FormData();
            formData.append('file', file);
            const resp = await apiFetch('/api/v1/files', {
                method: 'POST',
                body: formData
            });
            const result = await resp.json();
            if (resp.ok) {
                document.getElementById('uploadStatus').innerText = '✅ Загружено и распаковано';
                loadFileList();
                loadStatus();
            } else {
                document.getElementById('uploadStatus').innerText = '❌ Ошибка: ' + (result.error || 'неизвестная');
            }
        }

        async function downloadZip() {
            const resp = await apiFetch('/api/v1/files');
            if (resp.ok) {
                const blob = await resp.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'files.zip';
                document.body.appendChild(a);
                a.click();
                a.remove();
                loadStatus();
            } else {
                alert('Ошибка скачивания');
            }
        }

        loadStatus();
        loadFileList();

        window.onclick = function(event) {
            const modal = document.getElementById('passwordModal');
            if (event.target == modal) closeModal();
        }
    </script>
</body>
</html>
"""

# ---------- Корневые страницы ----------
@app.get("/")
async def root():
    return HTMLResponse(HTML_LOGIN)

@app.get("/dashboard")
async def dashboard():
    return HTMLResponse(HTML_DASHBOARD)

# ---------- Запуск ----------
if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)