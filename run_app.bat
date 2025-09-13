@echo off
echo Starting Audio Notetaker - Speech-to-Text Application...
echo.
echo Make sure you have installed the required dependencies:
echo pip install -r requirements.txt
echo.
echo The application will run in the background and minimize to the system tray.
echo Auto-starts listening on launch.
echo Default hotkey: F9
echo.
echo Starting in background mode...
start /min pythonw speech_to_text_app.py
echo.
echo Application started! Check your system tray for the microphone icon.
echo You can safely close this window.
echo.
pause