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
from datetime import date
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

def can_guest_process(ip):
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    today = date.today()
    
    try:
        # Проверяем, есть ли запись для этого IP
        cursor.execute("SELECT count, last_update FROM guest_usage WHERE ip_address = %s", (ip,))
        row = cursor.fetchone()
        
        if row:
            # Если наступил новый день, сбрасываем счетчик
            if row['last_update'] < today:
                cursor.execute("UPDATE guest_usage SET count = 1, last_update = %s WHERE ip_address = %s", (today, ip))
                db.commit()
                return True
            # Если сегодня уже было 5 или более обработок
            if row['count'] >= 5:
                return False
            # Иначе инкрементируем
            cursor.execute("UPDATE guest_usage SET count = count + 1 WHERE ip_address = %s", (ip,))
        else:
            # Первая запись для этого IP
            cursor.execute("INSERT INTO guest_usage (ip_address, count, last_update) VALUES (%s, 1, %s)", (ip, today))
        
        db.commit()
        return True
    finally:
        cursor.close()
        db.close()

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
    if 'user_id' not in session: 
        return redirect(url_for('login'))
    
    db = get_db_connection()
    cursor = db.cursor(dictionary=True)
    
    try:
        # 1. Проверка лимита хранения
        cursor.execute("SELECT COUNT(*) as count FROM images WHERE user_id = %s", (session['user_id'],))
        if cursor.fetchone()['count'] >= 100:
            flash("Лимит хранения (100) исчерпан.", "error")
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            file = request.files.get('file')
            if file and allowed_file(file.filename):
                # Измеряем размер файла
                file.seek(0, os.SEEK_END)
                file_size = file.tell()
                file.seek(0)

                ext = file.filename.rsplit('.', 1)[1].lower()
                is_video_ext = ext in {'mp4', 'mov', 'avi'}

                # 2. Проверка размера (видео 50МБ, фото 10МБ)
                if (is_video_ext and file_size > 50 * 1024 * 1024) or (
                        not is_video_ext and file_size > 10 * 1024 * 1024):
                    flash("Файл слишком большой!", "error")
                    return redirect(url_for('dashboard'))

                # 3. ФИКСИРОВАННЫЕ ПАРАМЕТРЫ (Пользователь больше их не выбирает)
                params = {
                    'denoise_h': 15.0,
                    'saturation_factor': 1.3,
                    'sharpness_factor': 1.0,
                    'contrast_alpha': 1.15,
                    'brightness_beta': 15
                }

                # Проверяем только наличие галочки AI
                use_ai = 'use_ai' in request.form
                u_id = uuid.uuid4().hex

                # --- ОБРАБОТКА ВИДЕО ---
                if is_video_ext:
                    filename_orig = f"raw_{u_id}.{ext}"
                    filename_proc = f"proc_{u_id}.mp4"
                    p_in = os.path.join(app.config['UPLOAD_FOLDER'], filename_orig)
                    p_out = os.path.join(app.config['UPLOAD_FOLDER'], filename_proc)
                    file.save(p_in)

                    p_compressed = os.path.join(app.config['UPLOAD_FOLDER'], f"res_{u_id}.mp4")
                    
                    # Сжатие до 720p (если оригинал больше)
                    was_compressed = image_processor.resize_video_if_needed(p_in, p_compressed)
                    input_for_processing = p_compressed if was_compressed else p_in

                    # Основной фильтр улучшения (передаем флаг use_ai и фиксированные параметры)
                    if image_processor.process_video(input_for_processing, p_out, params, use_ai=use_ai):
                        if was_compressed and os.path.exists(p_compressed):
                            os.remove(p_compressed)

                        cursor.execute(
                            "INSERT INTO images (user_id, filename_original, filename_processed, brightness_beta, contrast_alpha) VALUES (%s,%s,%s,%s,%s)",
                            (session['user_id'], filename_orig, filename_proc, params['brightness_beta'], params['contrast_alpha']))
                        db.commit()
                        
                        msg = "Видео сжато и обработано!" if was_compressed else "Видео успешно обработано!"
                        flash(msg, "success")
                    else:
                        flash("Ошибка при обработке видео", "error")
                    
                    return redirect(url_for('dashboard'))

                # --- ОБРАБОТКА ФОТО ---
                else:
                    file_data = file.read()
                    filename_orig = f"{u_id}.{ext}"
                    p_orig = os.path.join(app.config['UPLOAD_FOLDER'], filename_orig)
                    
                    with open(p_orig, 'wb') as f:
                        f.write(file_data)

                    if use_ai:
                        # Каскад нейросетей
                        m_path = os.path.join('models', 'zero_dce_pp.pth')
                        dn_path = os.path.join('models', 'nafnet_denoiser.pth')
                        proc_io = image_processor.enhance_image_ai(
                            io.BytesIO(file_data), 
                            model_path=m_path, 
                            denoise_path=dn_path
                        )
                    else:
                        # Классический метод с фиксированными параметрами
                        proc_io = image_processor.enhance_low_light_clahe(io.BytesIO(file_data), **params)

                    if proc_io:
                        filename_proc = f"proc_{u_id}.jpg"
                        p_proc = os.path.join(app.config['UPLOAD_FOLDER'], filename_proc)
                        with open(p_proc, 'wb') as f_out: 
                            f_out.write(proc_io.getbuffer())
                            
                        cursor.execute(
                            "INSERT INTO images (user_id, filename_original, filename_processed, brightness_beta, contrast_alpha) VALUES (%s,%s,%s,%s,%s)",
                            (session['user_id'], filename_orig, filename_proc, params['brightness_beta'], params['contrast_alpha']))
                        db.commit()
                        
                        mode_label = "AI" if use_ai else "Алгоритм"
                        flash(f"Фото обработано ({mode_label})", "success")
                    else:
                        flash("Ошибка при обработке фото", "error")
                        
                    return redirect(url_for('dashboard'))

        # GET-запрос: загружаем список файлов
        cursor.execute("SELECT * FROM images WHERE user_id = %s ORDER BY upload_date DESC", (session['user_id'],))
        images = cursor.fetchall()
        return render_template('dashboard.html', images=images)

    except Exception as e:
        print(f"Ошибка в роуте dashboard: {e}")
        flash("Произошла ошибка при обработке файла.", "error")
        return redirect(url_for('dashboard'))

    finally:
        cursor.close()
        db.close()

@app.route('/guest', methods=['GET', 'POST'])
def guest_mode():
    cleanup_old_files() # Очистка старых временных файлов
    processed_url = None
    
    if request.method == 'POST':
        # 1. Получаем IP пользователя
        user_ip = get_remote_address() 
        
        # 2. Проверяем лимит в базе данных (5 фото в день)
        if not can_guest_process(user_ip):
            flash("Лимит для гостей исчерпан! Пожалуйста, зарегистрируйтесь.", "error")
            return redirect(url_for('guest_mode'))

        file = request.files.get('file')
        if file and allowed_file(file.filename):
            try:
                ext = file.filename.rsplit('.', 1)[1].lower()
                
                # Запрет видео для гостей (оставляем проверку для безопасности)
                if ext in {'mp4', 'mov', 'avi'}:
                    flash("Видео доступно только зарегистрированным пользователям!", "error")
                    return redirect(url_for('guest_mode'))

                file_stream = file.read()
                
                # Проверка разрешения изображения
                with Image.open(io.BytesIO(file_stream)) as img:
                    if img.width * img.height > MAX_IMAGE_PIXELS:
                        flash("Изображение слишком большое!", "error")
                        return redirect(url_for('guest_mode'))

                # 3. ФИКСИРОВАННЫЕ ПАРАМЕТРЫ ДЛЯ ГОСТЯ
                # Мы полностью убрали чтение из request.form
                params = {
                    'denoise_h': 15.0,
                    'saturation_factor': 1.3,
                    'sharpness_factor': 1.0,
                    'contrast_alpha': 1.15,
                    'brightness_beta': 15
                }

                # 4. Вызов процессора (только CLAHE, без проверки use_ai)
                # Передаем BytesIO, так как мы прочитали файл для проверки Image.open
                proc_io = image_processor.enhance_low_light_clahe(io.BytesIO(file_stream), **params)
                
                if proc_io:
                    # Создаем уникальное имя файла для гостя
                    filename = f"guest_{uuid.uuid4().hex}.jpg"
                    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    
                    with open(save_path, 'wb') as f:
                        f.write(proc_io.getbuffer())
                    
                    processed_url = filename
                    flash("Изображение успешно обработано стандартным алгоритмом!", "success")
                
            except Exception as e:
                print(f"Ошибка в guest_mode: {e}")
                flash("Произошла ошибка при обработке.", "error")
        else:
            flash("Пожалуйста, выберите корректный файл изображения!", "error")
            
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