@echo off
cd /d "%~dp0"
echo Starting LOTTO QUANT V3 dashboard...
echo Close this window to stop the dashboard.
python -m streamlit run lotto_quant_v3\dashboard\app.py
echo.
echo Dashboard stopped.
pause
