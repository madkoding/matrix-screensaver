# Builds MatrixRain.scr (a PyInstaller one-file exe renamed to .scr).
# Needs: pip install -r requirements.txt pyinstaller
Set-Location $PSScriptRoot
python -m PyInstaller --noconfirm --onefile --noconsole --name MatrixRain `
    --icon icon.ico --version-file version_info.txt `
    --hidden-import glcontext --collect-submodules moderngl `
    matrix_saver.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)" }
Copy-Item dist\MatrixRain.exe MatrixRain.scr -Force
Write-Host "Done: $PSScriptRoot\MatrixRain.scr"
Write-Host "Install: right-click MatrixRain.scr > Install"
