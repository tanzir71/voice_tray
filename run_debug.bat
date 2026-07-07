@echo off
cd /d "%~dp0"
set VOICETRAY_LOG_LEVEL=DEBUG
set VOICETRAY_LOG_CONSOLE=1
echo Starting VoiceTray in debug mode...
echo Logs: %LOCALAPPDATA%\VoiceTray\logs\voicetray.log
echo.
python -m voicetray
echo.
echo VoiceTray exited with code %ERRORLEVEL%.
pause
