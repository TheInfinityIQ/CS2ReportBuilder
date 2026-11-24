@echo off
setlocal
cd /d "%~dp0"
set "VIEWER_VCVARS=C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
if not exist "%VIEWER_VCVARS%" (
  echo Visual Studio C++ tools were not found. No tools were installed.
  exit /b 1
)
call "%VIEWER_VCVARS%" >nul
if errorlevel 1 exit /b 1
if not exist build mkdir build
set "NATIVE_BUILD_NAME=v_%RANDOM%_%RANDOM%"
mkdir "build\%NATIVE_BUILD_NAME%"
cl /nologo /std:c++20 /EHsc /O2 /MT /LD /guard:cf capture.cpp /Fo:"build\%NATIVE_BUILD_NAME%\capture.obj" /Fe:"build\%NATIVE_BUILD_NAME%\capture.dll" /link windowsapp.lib d3d11.lib dxgi.lib dcomp.lib user32.lib ole32.lib mfplat.lib mfreadwrite.lib mfuuid.lib /IMPLIB:"build\%NATIVE_BUILD_NAME%\capture.lib" /INCREMENTAL:NO
if errorlevel 1 exit /b 1
>build\current.json.tmp echo {"dll":"%NATIVE_BUILD_NAME%/capture.dll","abi":2}
move /Y build\current.json.tmp build\current.json >nul
if errorlevel 1 exit /b 1
echo Native capture build published. Existing views keep their loaded version.
exit /b 0
