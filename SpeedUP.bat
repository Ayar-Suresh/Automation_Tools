@echo off
color 0B
title Full Temp, %TEMP%, and Prefetch Cleanup (with TakeOwnership)

echo.
echo ==============================
echo   Cleaning %TEMP% folder
echo ==============================
del /f /s /q "%TEMP%\*.*"
for /d %%x in ("%TEMP%\*") do rd /s /q "%%x"

echo.
echo ==============================
echo   Cleaning C:\Windows\Temp
echo ==============================
del /f /s /q "C:\Windows\Temp\*.*"
for /d %%x in ("C:\Windows\Temp\*") do rd /s /q "%%x"

echo.
echo ==============================
echo   Taking Ownership of PREFETCH
echo ==============================
takeown /f "C:\Windows\Prefetch" /r /d y
icacls "C:\Windows\Prefetch" /grant administrators:F /t

echo.
echo ==============================
echo   Stopping Explorer to free locked Prefetch files
echo ==============================
taskkill /f /im explorer.exe

echo.
echo ==============================
echo   Cleaning PREFETCH folder
echo ==============================
del /f /s /q "C:\Windows\Prefetch\*.*"
echo.
echo   Restarting Explorer...
start explorer.exe

echo.
echo ==============================
echo   CLEANUP COMPLETED!
echo ==============================
pause
