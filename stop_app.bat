@echo off
echo Stopping project services...

:: ��������� ���� �� ������, ������� �� ���� � ������� start
taskkill /fi "windowtitle eq Flask App*" /t /f
taskkill /fi "windowtitle eq MinIO*" /t /f
taskkill /fi "windowtitle eq Celery Worker*" /t /f
taskkill /fi "windowtitle eq Redis Server*" /t /f

echo Done.
pause