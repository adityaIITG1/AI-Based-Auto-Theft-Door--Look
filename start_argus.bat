@echo off
echo ==============================================
echo     STARTING ARGUS BACKEND ^& TUNNEL
echo ==============================================
echo.

cd backend
start "ARGUS Backend" cmd /k ""C:\Users\ASUS\anaconda3\Anaconda 2025\python.exe" main.py"
cd ..

echo Starting Permanent Tunnel at:
echo https://argus-backend-aditya-007.loca.lt
echo.
npx -y localtunnel --port 8000 --subdomain argus-backend-aditya-007

pause
