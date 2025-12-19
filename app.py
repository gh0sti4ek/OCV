import os
import uuid
import mysql.connector
import io
import cv2
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
import image_processor # Импорт модуля обработки

load_dotenv()
last_cleanup_time = 0

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

# CSRF
csrf = CSRFProtect(app)

csp = {
    'default-src': '\'self\'',
    'style-src': ['\'self\'', 'https://cdn.jsdelivr.net', '\'unsafe-inline\''],
    'script-src': ['\'self\'', 'https://cdn.jsdelivr.net'],
    'img-src': ['\'self\'', 'data:', 'blob:'],
    'media-src': ['\'self\'', 'blob:'],
    'connect-src': ['\'self\'', 'https://cdn.jsdelivr.net']
}

talisman = Talisman(app, content_security_policy=csp, force_https=False)

# Настройка файлов
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'mp4', 'mov', 'avi'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
MAX_IMAGE_PIXELS = 4000 * 4000
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Настройка лимита
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
    return request.path.startswith('/static/')


@app.errorhandler(429)
def ratelimit_handler(e):
    session.pop('_flashes', None)
    flash("Слишком много попыток! Пожалуйста, подождите немного.", "error")
    if "register" in request.path:
        return render_template('register.html'), 429
    return render_template('login.html'), 429


# Подключение к БД
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
    if current_time - last_cleanup_time < 600:
        return
    now = time.time()
    for f in os.listdir(app.config['UPLOAD_FOLDER']):
        if f.startswith("guest_"):
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], f)
            if os.stat(file_path).st_mtime < now - 900:
                try:
                    os.remove(file_path)
                except OSError:
                    pass
    last_cleanup_time = current_time


# Маршруты

# Главная
@app.route('/')
def index():
    return render_template('welcome.html')

# Регистрация
@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("3 per hour", methods=["POST"])
def register():
    if 'user_id' in session: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username, password = request.form.get('username'), request.form.get('password')
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
                flash("Ошибка: имя занято", "error")
            finally:
                cursor.close(); db.close()
    return render_template('register.html')

# Логин
@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    if 'user_id' in session: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username, password = request.form.get('username'), request.form.get('password')
        db = get_db_connection()
        try:
            cursor = db.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()
            if user and check_password_hash(user['password'], password):
                session['user_id'], session['username'] = user['id'], user['username']
                return redirect(url_for('dashboard'))
            flash("Неверный логин или пароль", "error")
        finally:
            cursor.close(); db.close()
    return render_template('login.html')

# Логаут
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# Профиль, обработка фото и видео пользователя
@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session: return redirect(url_for('login'))
    db = get_db_connection()
    try:
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) as count FROM images WHERE user_id = %s", (session['user_id'],))
        if cursor.fetchone()['count'] > 100:
            flash("Лимит хранения (100) исчерпан.", "error")
            return redirect(url_for('dashboard'))

        # Проверка на фото или видео, проверка параметров и обработка

        if request.method == 'POST':
            file = request.files.get('file')
            if file and allowed_file(file.filename):
                file.seek(0, os.SEEK_END)
                file_size = file.tell()
                file.seek(0)

                ext = file.filename.rsplit('.', 1)[1].lower()
                is_video_ext = ext in {'mp4', 'mov', 'avi'}

                # Проверка размера (для видео максимум 50 мб, для фото 10 мб)
                if (is_video_ext and file_size > 50 * 1024 * 1024) or (
                        not is_video_ext and file_size > 10 * 1024 * 1024):
                    flash("Файл слишком большой!", "error")
                    return redirect(url_for('dashboard'))

                # Параметры обработки
                if 'auto_process' in request.form:
                    params = {'denoise_h': 10.0, 'saturation_factor': 1.2, 'sharpness_factor': 1.0,
                              'contrast_alpha': 1.1, 'brightness_beta': 5.0}
                else:
                    params = {
                        'denoise_h': float(request.form.get('denoise_h', 15.0)),
                        'saturation_factor': float(request.form.get('saturation_factor', 1.3)),
                        'sharpness_factor': float(request.form.get('sharpness_factor', 1.0)),
                        'contrast_alpha': float(request.form.get('contrast_alpha', 1.15)),
                        'brightness_beta': float(request.form.get('brightness_beta', 15))
                    }

                u_id = uuid.uuid4().hex

                if is_video_ext:
                    filename_orig = f"raw_{u_id}.{ext}"
                    filename_proc = f"proc_{u_id}.mp4"
                    p_in, p_out = os.path.join(app.config['UPLOAD_FOLDER'], filename_orig), os.path.join(
                        app.config['UPLOAD_FOLDER'], filename_proc)
                    file.save(p_in)

                    v_cap = cv2.VideoCapture(p_in)
                    v_w = v_cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                    v_h = v_cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                    v_cap.release()

                    # Проверка разрешения, максимум 720p

                    if v_w > 1280 or v_h > 720:
                        os.remove(p_in)
                        flash("Разрешение видео слишком высокое! Максимум 720p.", "error")
                        return redirect(url_for('dashboard'))

                    if image_processor.process_video(p_in, p_out, **params):
                        cursor.execute(
                            "INSERT INTO images (user_id, filename_original, filename_processed, brightness_beta, contrast_alpha) VALUES (%s,%s,%s,%s,%s)",
                            (session['user_id'], filename_orig, filename_proc, params['brightness_beta'],
                             params['contrast_alpha']))
                        db.commit()
                        flash("Видео готово!", "success")
                    else:
                        flash("Ошибка обработки видео", "error")

                # Обработка фото

                else:
                    file_data = file.read()
                    filename_orig = f"{u_id}.{ext}"
                    p_orig = os.path.join(app.config['UPLOAD_FOLDER'], filename_orig)
                    with open(p_orig, 'wb') as f:
                        f.write(file_data)

                    proc_io = image_processor.enhance_low_light_clahe(io.BytesIO(file_data), **params)
                    if proc_io:
                        filename_proc = f"proc_{u_id}.jpg"
                        p_proc = os.path.join(app.config['UPLOAD_FOLDER'], filename_proc)
                        with open(p_proc, 'wb') as f_out: f_out.write(proc_io.getbuffer())
                        cursor.execute(
                            "INSERT INTO images (user_id, filename_original, filename_processed, brightness_beta, contrast_alpha) VALUES (%s,%s,%s,%s,%s)",
                            (session['user_id'], filename_orig, filename_proc, params['brightness_beta'],
                             params['contrast_alpha']))
                        db.commit()
                        flash("Фото готово!", "success")

        cursor.execute("SELECT * FROM images WHERE user_id = %s ORDER BY upload_date DESC", (session['user_id'],))
        images = cursor.fetchall()
        return render_template('dashboard.html', images=images)
    finally:
        cursor.close(); db.close()

# Гость, обработка фото
@app.route('/guest', methods=['GET', 'POST'])
def guest_mode():
    cleanup_old_files()
    processed_url = None
    if request.method == 'POST':
        file = request.files.get('file')
        if file and allowed_file(file.filename):
            try:
                ext = file.filename.rsplit('.', 1)[1].lower()
                if ext in {'mp4', 'mov', 'avi'}:
                    flash("Видео доступно только зарегистрированным пользователям!", "error")
                    return redirect(url_for('guest_mode'))

                file_stream = file.read()
                with Image.open(io.BytesIO(file_stream)) as img:
                    if img.width * img.height > MAX_IMAGE_PIXELS:
                        flash("Изображение слишком большое!", "error")
                        return redirect(request.url)

                # Обработка фото

                if 'auto_process' in request.form:
                    params = {'denoise_h': 10.0, 'saturation_factor': 1.2, 'sharpness_factor': 1.0,
                              'contrast_alpha': 1.1, 'brightness_beta': 5.0}
                else:
                    params = {
                        'denoise_h': max(0.0, min(float(request.form.get('denoise_h', 15.0)), 20.0)),
                        'saturation_factor': max(0.5, min(float(request.form.get('saturation_factor', 1.3)), 2.0)),
                        'sharpness_factor': max(0.0, min(float(request.form.get('sharpness_factor', 1.0)), 3.0)),
                        'contrast_alpha': max(1.0, min(float(request.form.get('contrast_alpha', 1.15)), 3.0)),
                        'brightness_beta': max(-100.0, min(float(request.form.get('brightness_beta', 15)), 100.0))
                    }

                proc_io = image_processor.enhance_low_light_clahe(io.BytesIO(file_stream), **params)
                if proc_io:
                    filename = f"guest_{uuid.uuid4().hex}.jpg"
                    with open(os.path.join(app.config['UPLOAD_FOLDER'], filename), 'wb') as f: f.write(
                        proc_io.getbuffer())
                    processed_url = filename
            except Exception as e:
                flash("Ошибка обработки", "error")
        else:
            flash("Выберите фото!", "error")
    return render_template('guest.html', processed_url=processed_url)

# Сравнение фото
@app.route('/compare/<int:image_id>')
def compare(image_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM images WHERE id = %s AND user_id = %s", (image_id, session['user_id']))
    image = cursor.fetchone()
    cursor.close();
    db.close()
    if not image: return redirect(url_for('dashboard'))
    return render_template('compare.html', image=image)

# Удаление фото и видео
@app.route('/delete/<int:image_id>', methods=['POST'])
def delete_image(image_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    db = get_db_connection()
    try:
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT filename_original, filename_processed FROM images WHERE id = %s AND user_id = %s",
                       (image_id, session['user_id']))
        image = cursor.fetchone()
        if image:
            cursor.execute("DELETE FROM images WHERE id = %s", (image_id,))
            db.commit()
            for key in ['filename_original', 'filename_processed']:
                f_p = os.path.join(app.config['UPLOAD_FOLDER'], image[key])
                if os.path.exists(f_p): os.remove(f_p)
            flash("Удалено", "success")
    finally:
        cursor.close(); db.close()
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=False)