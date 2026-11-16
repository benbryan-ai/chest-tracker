# Builds "Chest-Tracker.exe" in this folder. Only needed if you change the code.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .venv-app\Scripts\python.exe)) { python -m venv .venv-app }
.venv-app\Scripts\python.exe -m pip install -q --disable-pip-version-check -r requirements-dev.txt

# The replay scanner (chest-scan.exe) is built with .NET and bundled into the app. Without it the app still
# works and just uses the screen count, so a missing .NET SDK only warns, unless REQUIRE_SCANNER is set.
$scannerExe = "$PSScriptRoot\scanner-out\chest-scan.exe"
if (Get-Command dotnet -ErrorAction SilentlyContinue) {
    dotnet publish scanner\src\chest-scan\chest-scan.csproj -c Release -r win-x64 --self-contained `
        -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -o scanner-out
    if ($LASTEXITCODE -ne 0) { throw "Building the replay scanner failed" }
}
$scannerArgs = @()
if (Test-Path $scannerExe) {
    $scannerArgs = @("--add-binary", "$scannerExe;.")
} elseif ($env:REQUIRE_SCANNER) {
    throw "chest-scan.exe was not built"
} else {
    Write-Warning "No .NET SDK found: building without the replay scanner (the app will use the screen count)."
}

.venv-app\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name "Chest-Tracker" `
    --icon "$PSScriptRoot\assets\icon.ico" `
    --add-data "$PSScriptRoot\assets\icon.png;assets" `
    --add-data "$PSScriptRoot\assets\box_model.npz;assets" `
    --add-data "$PSScriptRoot\assets\prompt_word.png;assets" `
    --add-data "$PSScriptRoot\assets\recap_play_again.png;assets" `
    --add-data "$PSScriptRoot\assets\recap_return.png;assets" `
    @scannerArgs `
    --exclude-module tkinter `
    --distpath . --workpath build --specpath build `
    app.py
