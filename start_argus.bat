@echo off
echo ==============================================
echo     STARTING ARGUS BACKEND ^& TUNNEL
echo ==============================================
echo.

cd backend
start "ARGUS Backend" cmd /k "python main.py"
cd ..

echo Starting Permanent Tunnel at:
echo https://argus-door-lock-backend.loca.lt
echo.
npx -y localtunnel --port 8000 --subdomain argus-door-lock-backend

pause
