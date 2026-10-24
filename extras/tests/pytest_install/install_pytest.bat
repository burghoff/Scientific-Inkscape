@echo off

python.exe get-pip.py
pip uninstall pytest
pip install -U --no-cache-dir pytest

echo Done!
pause