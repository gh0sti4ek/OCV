@echo off
echo Stopping project services...

:: «акрываем окна по именам, которые мы дали в команде start
taskkill /fi "windowtitle eq Flask App*" /t /f
taskkill /fi "windowtitle eq Celery Worker*" /t /f
taskkill /fi "windowtitle eq Redis Server*" /t /f

echo Done.
pause