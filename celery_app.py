from celery import Celery
import os

def make_celery(app_name):
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    return Celery(
        app_name,
        backend=redis_url,
        broker=redis_url,
        include=['tasks']
    )

celery = make_celery('image_enhancer')