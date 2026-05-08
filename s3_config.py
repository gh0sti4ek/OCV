import os
import boto3
from botocore.config import Config
from dotenv import load_dotenv

load_dotenv()

# Инициализация клиента S3 в одном месте
s3_client = boto3.client(
    's3',
    endpoint_url=os.getenv('S3_ENDPOINT', 'https://s3.twcstorage.ru'),
    aws_access_key_id=os.getenv('S3_ACCESS_KEY'),
    aws_secret_access_key=os.getenv('S3_SECRET_KEY'),
    config=Config(signature_version='s3v4', proxies={}),
    region_name=os.getenv('S3_REGION', 'ru-1')
)

bucket_name = os.getenv('S3_BUCKET', 'diploma-ocv')