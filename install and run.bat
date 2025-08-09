@echo off
echo Installing dependencies...
pip install --upgrade pip
pip install -r requirements.txt

echo Running RSBP.py...
python RSBP.py

pause
