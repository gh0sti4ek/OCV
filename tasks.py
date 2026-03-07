import os
import io
import mysql.connector
from celery_app import celery
import image_processor
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME')
    )

@celery.task(bind=True)
def process_video_task(self, filename_in, filename_out, params, use_ai):
    """Фоновая задача для обработки видео"""
    p_in = os.path.join('static', 'uploads', filename_in)
    p_out = os.path.join('static', 'uploads', filename_out)
    
    try:
        # В image_processor.process_video params передается как словарь (3-й аргумент)
        success = image_processor.process_video(p_in, p_out, params, use_ai=use_ai)
        status = 'ready' if success else 'error'
    except Exception as e:
        print(f"Celery Video Error: {e}")
        status = 'error'
    
    _update_db_status(self.request.id, status)

@celery.task(bind=True)
def process_photo_task(self, filename_orig, filename_proc, use_ai, params, model_paths):
    """Фоновая задача для обработки фото"""
    p_orig = os.path.join('static', 'uploads', filename_orig)
    p_proc = os.path.join('static', 'uploads', filename_proc)
    
    try:
        if not os.path.exists(p_orig):
            raise FileNotFoundError(f"Original file not found: {p_orig}")

        with open(p_orig, 'rb') as f:
            file_data = f.read()
        
        if use_ai:
            proc_io = image_processor.enhance_image_ai(
                io.BytesIO(file_data), 
                model_path=model_paths['model'], 
                denoise_path=model_paths['denoise']
            )
        else:
            # Для фото-функции enhance_low_light_clahe передаем параметры явно из словаря
            # Это безопаснее, чем **params, так как мы контролируем порядок
            proc_io = image_processor.enhance_low_light_clahe(
                io.BytesIO(file_data),
                denoise_h=float(params.get('denoise_h', 15.0)),
                saturation_factor=float(params.get('saturation_factor', 1.3)),
                sharpness_factor=float(params.get('sharpness_factor', 1.0)),
                contrast_alpha=float(params.get('contrast_alpha', 1.15)),
                brightness_beta=int(params.get('brightness_beta', 15))
            )

        if proc_io:
            with open(p_proc, 'wb') as f_out:
                f_out.write(proc_io.getbuffer())
            status = 'ready'
        else:
            status = 'error'
    except Exception as e:
        print(f"Celery Photo Error: {e}")
        status = 'error'

    _update_db_status(self.request.id, status)

def _update_db_status(task_id, status):
    """Вспомогательная функция для обновления статуса в БД"""
    try:
        db = get_db_connection()
        cursor = db.cursor()
        cursor.execute("UPDATE images SET status = %s WHERE task_id = %s", (status, task_id))
        db.commit()
        cursor.close()
        db.close()
    except Exception as e:
        print(f"Database Update Error: {e}")