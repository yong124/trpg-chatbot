@echo off
CHCP 65001
ECHO Starting Backend and Frontend servers...

REM Set the path to the Python executable in the virtual environment
SET PYTHON_EXE=%~dp0backend\venv\Scripts\python.exe

REM Check if the Python executable exists
IF NOT EXIST "%PYTHON_EXE%" (
    ECHO ERROR: Python executable not found at %PYTHON_EXE%
    ECHO Please make sure the virtual environment is correctly set up in the 'backend' folder.
    PAUSE
    EXIT /B
)

ECHO Using Python from the virtual environment to run both servers.

REM Start the Backend Server in a new window
ECHO Starting Backend Server...
START "TRPG Chatbot Backend" cmd /k "cd backend && %PYTHON_EXE% -u app.py"

REM Start the Frontend Server in a new window
ECHO Starting Frontend Server on http://localhost:8000 ...
START "TRPG Chatbot Frontend" cmd /k "cd frontend && "%PYTHON_EXE%" -m http.server 8000"

ECHO ---
ECHO Servers are starting up.
ECHO Please open http://localhost:8000 in your browser to start the application.
