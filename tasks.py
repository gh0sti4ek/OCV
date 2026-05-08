import os
import io
import mysql.connector
import boto3  # Добавили для работы с MinIO
import json   # Добавили для настройки прав доступа
from botocore.config import Config
from celery_app import celery
import image_processor
from dotenv import load_dotenv
from s3_config import s3_client, bucket_name

load_dotenv()

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME')
    )

def upload_to_s3_and_cleanup(local_path, filename):
    """Загружает файл в MinIO и удаляет локальную копию"""
    bucket_name = os.getenv('S3_BUCKET', 'uploads')
    try:
        s3_client.upload_file(local_path, bucket_name, filename)
        if os.path.exists(local_path):
            os.remove(local_path)
        print(f"--- [S3] Файл {filename} успешно загружен и удален локально ---")
    except Exception as e:
        print(f"--- [S3 ERROR] Ошибка загрузки {filename}: {e} ---")

@celery.task(bind=True)
def process_video_task(self, filename_in, filename_out, params, use_ai):
    """Фоновая задача для обработки видео"""
    p_in = os.path.join('static', 'uploads', filename_in)
    p_out = os.path.join('static', 'uploads', filename_out)
    
    try:
        success = image_processor.process_video(p_in, p_out, params, use_ai=use_ai)
        if success:
            upload_to_s3_and_cleanup(p_in, filename_in)
            upload_to_s3_and_cleanup(p_out, filename_out)
            status = 'ready'
        else:
            status = 'error'
    except Exception as e:
        print(f"Celery Video Error: {e}")
        status = 'error'
    
    _update_db_status(self.request.id, status)

@celery.task(bind=True)
def process_photo_task(self, filename_orig, filename_proc, use_ai, params, model_paths):
    """Фоновая задача для обработки фото с поддержкой GFPGAN"""
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
                model_path=model_paths.get('model'), 
                denoise_path=model_paths.get('denoise'),
                enhance_faces=params.get('enhance_faces', False)
            )
        else:
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
            
            upload_to_s3_and_cleanup(p_orig, filename_orig)
            upload_to_s3_and_cleanup(p_proc, filename_proc)
            
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