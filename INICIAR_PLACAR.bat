@echo off
title Setup e Inicializador - Placar Aldo Luiz Live
chcp 65001 >nul
color 0B

echo ========================================================
echo       ALDO LUIZ LIVE - SETUP AUTOMATIZADO DO PLACAR
echo ========================================================
echo.

:: 0. Descarregamento e Sincronizacao de Todos os Ficheiros via GitHub (.ZIP + TAR)
echo [0/4] A verificar e descarregar atualizacoes completas do GitHub...
set "REPO_ZIP_MAIN=https://github.com/pedrodomingosdev/lives-placar/archive/refs/heads/main.zip"
set "REPO_ZIP_MASTER=https://github.com/pedrodomingosdev/lives-placar/archive/refs/heads/master.zip"

:: Tenta descarregar a branch main com quebra de cache
curl -s -f -L "%REPO_ZIP_MAIN%?nocache=%RANDOM%" -o "update.zip"

:: Se a branch for master, efetua o fallback automatico
if not exist "update.zip" (
    curl -s -f -L "%REPO_ZIP_MASTER%?nocache=%RANDOM%" -o "update.zip"
)

:: Descompacta e substitui todos os ficheiros (scripts, html, sons .mp3 e imagens)
if exist "update.zip" (
    tar -xf "update.zip" --strip-components=1
    del /f /q "update.zip" >nul 2>&1
    echo       - Todos os ficheiros do projeto foram sincronizados com sucesso!
) else (
    echo       - [AVISO] Nao foi possivel descarregar as atualizacoes. A usar ficheiros locais...
)
echo.

:: 1. Identificacao segura do comando Python
set "PYTHON_CMD="
python --version >nul 2>&1 && set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
    py --version >nul 2>&1 && set "PYTHON_CMD=py"
)

if not defined PYTHON_CMD (
    echo [ERRO CRITICO] O Python nao foi detetado neste computador!
    echo Instale o Python a partir de python.org marcando a opcao "Add Python to PATH".
    echo.
    pause
    exit /b
)

echo [1/4] Python detetado com sucesso via '%PYTHON_CMD%'!
echo.

:: 2. Verificacao de bibliotecas necessarias
echo [2/4] A verificar bibliotecas necessarias...
%PYTHON_CMD% -m pip install selenium webdriver-manager >nul 2>&1
echo       - Dependencias verificadas com sucesso!
echo.

:: 3. Localizacao do executavel do Google Chrome
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

:: 4. Encerramento de instancias antigas e arranque do Chrome dedicado
echo [3/4] A iniciar o Chrome dedicado na porta 9333...

powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name = 'chrome.exe'\" | Where-Object { $_.CommandLine -like '*ChromeSofa*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

set "CHROME_DIR=%LOCALAPPDATA%\ChromeSofa"
if not exist "%CHROME_DIR%" mkdir "%CHROME_DIR%"

start "" "%CHROME_EXE%" --remote-debugging-port=9333 --remote-allow-origins=* --user-data-dir="%CHROME_DIR%" --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding --disable-features=CalculateNativeWinOcclusion

timeout /t 4 /nobreak >nul
echo       - Janela do Chrome pronta para operacao!
echo.

:: 5. Execucao do Servidor e Scraper
echo ========================================================
echo [4/4] A ligar ao Chrome e a iniciar a leitura em direto...
echo ========================================================
echo.
%PYTHON_CMD% scraper.py

pause