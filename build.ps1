# Builds MatrixRain.scr (a PyInstaller one-file exe renamed to .scr)
Set-Location $PSScriptRoot
python -m PyInstaller --noconfirm --onefile --noconsole --name MatrixRain matrix_saver.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller fallo ($LASTEXITCODE)" }
Copy-Item dist\MatrixRain.exe MatrixRain.scr -Force
Write-Host "Listo: $PSScriptRoot\MatrixRain.scr"
Write-Host "Instalar: clic derecho sobre MatrixRain.scr > Instalar"
