@echo off
title Setup e Inicializador - Placar Aldo Luiz Live
chcp 65001 >nul
color 0B

echo ========================================================
echo       ALDO LUIZ LIVE - SETUP AUTOMATIZADO DO PLACAR
echo ========================================================
echo.

:: 0. Verificacao e Download de Atualizacoes (GitHub)
echo [0/4] A verificar atualizacoes no GitHub...
set "REPO_URL=https://github.com/pedrodomingosdev/lives-placar.git"

:: Baixa as versoes mais recentes dos arquivos principais silenciosamente
curl -s -f "%REPO_URL%/scraper.py" -o "scraper.py.tmp" && (
    move /y "scraper.py.tmp" "scraper.py" >nul
    echo       -> 'scraper.py' atualizado!
) || (
    del /f "scraper.py.tmp" >nul 2>&1
)

curl -s -f "%REPO_URL%/placar.html" -o "placar.html.tmp" && (
    move /y "placar.html.tmp" "placar.html" >nul
    echo       -> 'placar.html' atualizado!
) || (
    del /f "placar.html.tmp" >nul 2>&1
)
echo.

:: 1. Identificacao do comando Python
set PYTHON_CMD=
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=python
) else (
    py --version >nul 2>&1
    if %errorlevel% equ 0 (
        set PYTHON_CMD=py
    )
)

if "%PYTHON_CMD%"=="" (
    echo [AVISO] O Python ainda nao foi detetado neste computador!
    pause
    exit /b
)

echo [1/4] Python detetado com sucesso via '%PYTHON_CMD%'!
echo.

:: 2. Verificacao de bibliotecas
echo [2/4] A verificar bibliotecas necessarias...
%PYTHON_CMD% -m pip install selenium webdriver-manager >nul 2>&1
echo.

:: 3. Localizacao do executavel do Chrome
set "CHROME_EXE="
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    set "CHROME_EXE=C:\Program Files\Google\Chrome\Application\chrome.exe"
) else if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    set "CHROME_EXE=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
) else if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_EXE=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
) else (
    set "CHROME_EXE=chrome.exe"
)

:: 4. Arranque do Chrome em perfil isolado na porta 9333
echo [3/4] A iniciar o Chrome dedicado na porta 9333...

powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name = 'chrome.exe'\" | Where-Object { $_.CommandLine -like '*ChromeSofa*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

set "CHROME_DIR=%LOCALAPPDATA%\ChromeSofa"
if not exist "%CHROME_DIR%" mkdir "%CHROME_DIR%"

start "" "%CHROME_EXE%" --remote-debugging-port=9333 --remote-allow-origins=* --user-data-dir="%CHROME_DIR%" --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding --disable-features=CalculateNativeWinOcclusion

timeout /t 5 /nobreak >nul
echo.

:: 5. Execucao do Scraper
echo ========================================================
echo [4/4] A ligar ao Chrome e a iniciar a leitura em direto...
echo ========================================================
echo.
%PYTHON_CMD% scraper.py

pause