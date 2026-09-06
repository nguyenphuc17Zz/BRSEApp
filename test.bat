@echo off
title Run Comtor Copilot Automated Tests
cd /d "%~dp0\services\backend"
echo Running all Unit and Scenario Tests...
.\.venv\Scripts\pytest.exe -v
pause
