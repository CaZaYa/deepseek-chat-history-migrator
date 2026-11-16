@echo off
setlocal
cd /d "%~dp0"

echo [1/3] 安装打包依赖…
python -m pip install --quiet --upgrade pyinstaller || goto :error

echo [2/3] 构建图形界面…
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name DeepSeek2Cherry --paths src --icon assets\icon.ico --add-data "assets\icon.ico;assets" ^
    --distpath dist --workpath build run_gui.py || goto :error

echo [3/3] 构建命令行版本…
python -m PyInstaller --noconfirm --clean --onefile --console ^
    --name DeepSeek2Cherry-CLI --paths src --icon assets\icon.ico ^
    --distpath dist --workpath build run_cli.py || goto :error

echo.
echo 完成，产物在 dist\ 目录。
exit /b 0

:error
echo 构建失败。
exit /b 1
