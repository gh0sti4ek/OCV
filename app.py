import os
import uuid
import mysql.connector
import io
from PIL import Image
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

import image_processor  # Ваш модуль обработки OpenCV

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

# --- 1. ЗАЩИТА CSRF ---
csrf = CSRFProtect(app)

# --- 2. НАСТРОЙКИ ФАЙЛОВ ---
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # Лимит 10МБ
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
            file_content = file.read()
            try:
                # Проверка изображения
                img = Image.open(io.BytesIO(file_content))
                img.verify()
                file.seek(0)

                # Валидация параметров (защита сервера)
                params = {
                    'denoise_h': max(0.0, min(float(request.form.get('denoise_h', 15.0)), 20.0)),
                    'saturation_factor': max(0.5, min(float(request.form.get('saturation_factor', 1.3)), 2.0)),
                    'sharpness_factor': max(0.0, min(float(request.form.get('sharpness_factor', 1.0)), 3.0)),
                    'contrast_alpha': max(1.0, min(float(request.form.get('contrast_alpha', 1.15)), 3.0)),
                    'brightness_beta': max(-100.0, min(float(request.form.get('brightness_beta', 15)), 100.0))
                }

                ext = file.filename.rsplit('.', 1)[1].lower()
                filename_original = f"{uuid.uuid4().hex}.{ext}"
                path_original = os.path.join(app.config['UPLOAD_FOLDER'], filename_original)

                with open(path_original, 'wb') as f:
                    f.write(file_content)

                with open(path_original, 'rb') as f_in:
                    processed_io = image_processor.enhance_low_light_clahe(f_in, **params)

                if processed_io:
                    filename_processed = f"proc_{filename_original}"
                    path_processed = os.path.join(app.config['UPLOAD_FOLDER'], filename_processed)
                    with open(path_processed, 'wb') as f_out:
                        f_out.write(processed_io.getbuffer())

                    cursor.execute(
                        "INSERT INTO images (user_id, filename_original, filename_processed, brightness_beta, contrast_alpha) VALUES (%s, %s, %s, %s, %s)",
                        (session['user_id'], filename_original, filename_processed, params['brightness_beta'],
                         params['contrast_alpha'])
                    )
                    db.commit()
                    flash("Изображение успешно обработано!", "success")
            except Exception as e:
                flash(f"Ошибка: {e}", "error")
        else:
            flash("Недопустимый формат!", "error")

    cursor.execute("SELECT * FROM images WHERE user_id = %s ORDER BY upload_date DESC", (session['user_id'],))
    images = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template('dashboard.html', images=images)


@app.route('/guest', methods=['GET', 'POST'])
def guest_mode():
    processed_url = None
    if request.method == 'POST':
        file = request.files.get('file')
        if file and allowed_file(file.filename):
            try:
                file_content = file.read()
                params = {
                    'denoise_h': max(0.0, min(float(request.form.get('denoise_h', 15.0)), 20.0)),
                    'saturation_factor': max(0.5, min(float(request.form.get('saturation_factor', 1.3)), 2.0)),
                    'sharpness_factor': max(0.0, min(float(request.form.get('sharpness_factor', 1.0)), 3.0)),
                    'contrast_alpha': max(1.0, min(float(request.form.get('contrast_alpha', 1.15)), 3.0)),
                    'brightness_beta': max(-100.0, min(float(request.form.get('brightness_beta', 15)), 100.0))
                }

                processed_io = image_processor.enhance_low_light_clahe(io.BytesIO(file_content), **params)

                if processed_io:
                    filename = f"guest_{uuid.uuid4().hex}.jpg"
                    with open(os.path.join(app.config['UPLOAD_FOLDER'], filename), 'wb') as f_out:
                        f_out.write(processed_io.getbuffer())
                    processed_url = filename
            except Exception as e:
                flash(f"Ошибка обработки: {e}", "error")

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
    app.run(debug=True)