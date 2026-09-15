@echo off
chcp 65001 >nul
rem =====================================================
rem  PDF 翻译器 安装器 (Windows 原生, 不需要 WSL)
rem  首次使用运行一次即可; 之后双击 "启动翻译器.bat"
rem =====================================================
cd /d "%~dp0.."

rem 优先使用发布包内附带的 uv (免联网安装 uv 本体)
set "PATH=%~dp0;%PATH%"

where uv >nul 2>nul
if errorlevel 1 (
    echo [1/2] 未检测到 uv, 正在安装 (约 10 秒)...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
) else (
    echo [1/2] uv 已安装, 跳过
)

echo [2/2] 正在安装翻译依赖 (首次约 3-10 分钟, 视网速)...
uv sync
if errorlevel 1 (
    echo.
    echo [安装失败] 请检查网络后重新运行本文件; 或联系作者
    pause
    exit /b 1
)

echo.
echo ============================
echo   安装完成! 请双击 "启动翻译器.bat"
echo ============================
pause
