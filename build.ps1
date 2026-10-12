# Builds MatrixRain.scr (a PyInstaller one-file exe renamed to .scr)
Set-Location $PSScriptRoot
python -m PyInstaller --noconfirm --onefile --noconsole --name MatrixRain matrix_saver.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)" }
Copy-Item dist\MatrixRain.exe MatrixRain.scr -Force
Write-Host "Done: $PSScriptRoot\MatrixRain.scr"
Write-Host "Install: right-click MatrixRain.scr > Install"
