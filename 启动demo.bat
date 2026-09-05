@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 商品企划生成 Agent

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.9+
    pause
    exit /b 1
)

echo 正在检查依赖 (flask / python-pptx / pillow)...
python -c "import flask, pptx, PIL" >nul 2>&1
if errorlevel 1 (
    echo 首次运行，正在安装依赖，请稍候...
    python -m pip install flask python-pptx pillow -q
)

echo.
echo 正在启动「商品企划生成 Agent」...
echo 浏览器将自动打开；若未打开请手动访问 http://localhost:8000
echo 按 Ctrl+C 可停止服务。
echo.
start "" http://localhost:8000
python server.py
pause
