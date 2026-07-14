@echo off
:: BiliDanmaku Native Messaging Host Launcher
:: Chrome/Edge 通过此 bat 文件启动 Python Native Host
:: 如果 Python 不在 PATH 中，请修改下方路径为完整 Python 路径

cd /d "%~dp0"
python "%~dp0native_host.py"
