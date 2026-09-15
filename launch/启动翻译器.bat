@echo off
chcp 65001 >nul
rem ============================================
rem  PDF 翻译器 一键启动器 (Windows 原生, 无需 WSL)
rem  首次使用请先运行一次 install.bat
rem  建议右键本文件 -> 发送到 -> 桌面快捷方式
rem ============================================
cd /d "%~dp0.."

where uv >nul 2>nul
if errorlevel 1 (
    echo [未安装] 请先运行 launch 文件夹里的 install.bat
    pause
    exit /b 1
)

rem 3 秒后自动打开浏览器 (给服务器留启动时间)
start "" /min cmd /c "timeout /t 3 /nobreak >nul & start "" http://localhost:8000"

rem 窗口保持打开 = 服务运行中; 关闭窗口即停止服务
uv run web/server/main.py
if errorlevel 1 (
    echo.
    echo [启动失败] 黑窗口上方有报错信息; 可截图联系作者
    pause
)
