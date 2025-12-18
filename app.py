import os
import uuid
import mysql.connector
import io
from PIL import Image
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_talisman import Talisman
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import time
from werkzeug.utils import secure_filename
import image_processor

load_dotenv()
last_cleanup_time = 0

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

# --- 1. ЗАЩИТА CSRF ---
csrf = CSRFProtect(app)

csp = {
    'default-src': '\'self\'',
    'style-src': [
        '\'self\'',
        'https://cdn.jsdelivr.net',
        '\'unsafe-inline\''  # РАЗРЕШАЕМ инлайновые стили для фильтров JS
    ],
    'script-src': [
        '\'self\'',
        'https://cdn.jsdelivr.net'
    ],
    'img-src': [
        '\'self\'',
        'data:',             # РАЗРЕШАЕМ предпросмотр через FileReader (base64)
        'blob:'
    ],
    'connect-src': [
        '\'self\'',
        'https://cdn.jsdelivr.net' # Чтобы Bootstrap не ругался на .map файлы
    ]
}

# Если работаешь локально (без https), оставь force_https=False
talisman = Talisman(app, content_security_policy=csp, force_https=False)



# --- 2. НАСТРОЙКИ ФАЙЛОВ ---
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 4000 * 4000
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- 3. НАСТРОЙКА LIMITER (Защита от перебора) ---
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["1000 per day"],
    storage_uri="memory://",
    strategy="fixed-window",
    swallow_errors=True
)


@limiter.request_filter
def ip_whitelist():
    # Не лимитируем статические файлы, чтобы не блокировать верстку
    return request.path.startswith('/static/')


@app.errorhandler(429)
def ratelimit_handler(e):
    # ОЧИСТКА: Удаляем все накопленные сообщения ("Неверный пароль" и т.д.)
    session.pop('_flashes', None)

    flash("Слишком много попыток! Пожалуйста, подождите немного.", "error")

    # ПРЯМОЙ ВЫВОД: Возвращаем шаблон напрямую, а не через redirect,
    # чтобы избежать ошибки "Too many redirects"
    if "register" in request.path:
        return render_template('register.html'), 429
    return render_template('login.html'), 429


# --- Вспомогательные функции ---
def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME')
    )


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def cleanup_old_files():
    global last_cleanup_time
    current_time = time.time()

    # Очищаем папку не чаще чем раз в 10 минут (600 секунд)
    if current_time - last_cleanup_time < 600:
        return

    print("Запуск плановой очистки временных файлов...")
    now = time.time()
    for f in os.listdir(app.config['UPLOAD_FOLDER']):
        # Удаляем только гостевые файлы старше 15 минут
        if f.startswith("guest_"):
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], f)
            if os.stat(file_path).st_mtime < now - 900:
                try:
                    os.remove(file_path)
                except OSError:
                    pass  # Файл может быть занят другим процессом

    last_cleanup_time = current_time

# --- МАРШРУТЫ ---

@app.route('/')
def index():
    return render_template('welcome.html')


@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("3 per hour", methods=["POST"])  # Лимит только на POST
def register():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username and password:
            hashed_pw = generate_password_hash(password)
            db = get_db_connection()
            cursor = db.cursor()
            try:
                cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, hashed_pw))
                db.commit()
                flash("Регистрация успешна!", "success")
                return redirect(url_for('login'))
            except mysql.connector.Error:
                flash("Ошибка: возможно, имя уже занято", "error")
            finally:
                cursor.close()
                db.close()
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])  # Лимит только на попытки входа
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()
        cursor.close()
        db.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('dashboard'))

        flash("Неверный логин или пароль", "error")
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db_connection()
    cursor = db.cursor(dictionary=True)

    if request.method == 'POST':
        file = request.files.get('file')

        if file and allowed_file(file.filename):
            try:
                # Читаем файл ОДИН раз
                file_stream = file.read()

                # ПРОВЕРКА РАЗРЕШЕНИЯ (Защита от Image Bomb)
                with Image.open(io.BytesIO(file_stream)) as img:
                    width, height = img.size
                    if width * height > MAX_IMAGE_PIXELS:
                        flash(f"Изображение слишком большое ({width}x{height}). Максимум 4000x4000.", "error")
                        return redirect(request.url)

                    # Получаем формат для сохранения оригинала в правильном расширении
                    img_format = img.format.lower()

                # Валидация параметров
                params = {
                    'denoise_h': max(0.0, min(float(request.form.get('denoise_h', 15.0)), 20.0)),
                    'saturation_factor': max(0.5, min(float(request.form.get('saturation_factor', 1.3)), 2.0)),
                    'sharpness_factor': max(0.0, min(float(request.form.get('sharpness_factor', 1.0)), 3.0)),
                    'contrast_alpha': max(1.0, min(float(request.form.get('contrast_alpha', 1.15)), 3.0)),
                    'brightness_beta': max(-100.0, min(float(request.form.get('brightness_beta', 15)), 100.0))
                }

                # Сохранение оригинала (используем безопасное расширение от Pillow)
                filename_uuid = f"{uuid.uuid4().hex}.{img_format}"
                path_original = os.path.join(app.config['UPLOAD_FOLDER'], filename_uuid)

                with open(path_original, 'wb') as f:
                    f.write(file_stream)

                # Обработка (передаем уже считанный поток байтов)
                processed_io = image_processor.enhance_low_light_clahe(io.BytesIO(file_stream), **params)

                if processed_io:
                    filename_processed = f"proc_{filename_uuid}"
                    path_processed = os.path.join(app.config['UPLOAD_FOLDER'], filename_processed)
                    with open(path_processed, 'wb') as f_out:
                        f_out.write(processed_io.getbuffer())

                    cursor.execute(
                        "INSERT INTO images (user_id, filename_original, filename_processed, brightness_beta, contrast_alpha) VALUES (%s, %s, %s, %s, %s)",
                        (session['user_id'], filename_uuid, filename_processed, params['brightness_beta'],
                         params['contrast_alpha'])
                    )
                    db.commit()
                    flash("Готово!", "success")

            except Exception as e:
                flash("Ошибка при обработке файла.", "error")
                print(f"Error: {e}")
        else:
            flash("Неверный формат файла.", "error")

    cursor.execute("SELECT * FROM images WHERE user_id = %s ORDER BY upload_date DESC", (session['user_id'],))
    images = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template('dashboard.html', images=images)


@app.route('/guest', methods=['GET', 'POST'])
def guest_mode():
    cleanup_old_files()
    processed_url = None

    if request.method == 'POST':
        file = request.files.get('file')

        if file and allowed_file(file.filename):
            try:
                # 1. Читаем один раз в память
                file_stream = file.read()

                # 2. Проверка разрешения (Image Bomb protection)
                with Image.open(io.BytesIO(file_stream)) as img:
                    width, height = img.size
                    if width * height > MAX_IMAGE_PIXELS:
                        flash(f"Изображение слишком большое. Максимум 4000x4000.", "error")
                        return redirect(request.url)

                # 3. Валидация параметров (оставляем как было)
                params = {
                    'denoise_h': max(0.0, min(float(request.form.get('denoise_h', 15.0)), 20.0)),
                    'saturation_factor': max(0.5, min(float(request.form.get('saturation_factor', 1.3)), 2.0)),
                    'sharpness_factor': max(0.0, min(float(request.form.get('sharpness_factor', 1.0)), 3.0)),
                    'contrast_alpha': max(1.0, min(float(request.form.get('contrast_alpha', 1.15)), 3.0)),
                    'brightness_beta': max(-100.0, min(float(request.form.get('brightness_beta', 15)), 100.0))
                }

                # 4. Обработка (передаем io.BytesIO(file_stream))
                processed_io = image_processor.enhance_low_light_clahe(io.BytesIO(file_stream), **params)

                if processed_io:
                    filename = f"guest_{uuid.uuid4().hex}.jpg"
                    path_processed = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    with open(path_processed, 'wb') as f_out:
                        f_out.write(processed_io.getbuffer())
                    processed_url = filename
            except Exception as e:
                flash(f"Ошибка при обработке: {e}", "error")
        else:
            flash("Выберите корректный файл изображения!", "error")

    return render_template('guest.html', processed_url=processed_url)


@app.route('/compare/<int:image_id>')
def compare(image_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM images WHERE id = %s AND user_id = %s", (image_id, session['user_id']))
    image = cursor.fetchone()
    cursor.close()
    db.close()
    if not image:
        flash("Доступ запрещен", "error")
        return redirect(url_for('dashboard'))
    return render_template('compare.html', image=image)


if __name__ == '__main__':
    app.run(debug=False)