# Claudromos for Windows: syncs your Garmin data (Personal API) to %USERPROFILE%\Claudromos
# and rebuilds the dashboard (Claudromos\dashboards\claudromos.html) when new data arrives.
#
# Run from the cloned repo in PowerShell:
#   powershell -ExecutionPolicy Bypass -File install.ps1                 install or update; asks for the API key once
#   powershell -ExecutionPolicy Bypass -File install.ps1 update-key      replace an expired key
#   ... install.ps1 sync | rebuild | config | diagnose | uninstall
#   ... install.ps1 scope runs|all
#   ... install.ps1 history 1m|1y|3y|all
#
# The key is encrypted with Windows DPAPI for your user account (ConvertFrom-SecureString) in
# Claudromos\.claudromos\key.dpapi; only your Windows account on this PC can decrypt it.
param([string]$Mode = "install", [string]$Value = "")
$ErrorActionPreference = "Stop"

$Data = if ($env:CLAUDROMOS_DIR) { $env:CLAUDROMOS_DIR } else { Join-Path $env:USERPROFILE "Claudromos" }
$Eng = Join-Path $Data ".claudromos"
$Src = $PSScriptRoot
$Conf = Join-Path $Eng "config.json"
$KeyFile = Join-Path $Eng "key.dpapi"
$TaskName = "Claudromos sync"
$VenvPy = Join-Path $Eng "venv\Scripts\python.exe"
$VenvPyw = Join-Path $Eng "venv\Scripts\pythonw.exe"

function Find-Python {
    $probe = "import sys, ssl, venv; print(sys.executable)"
    $tries = @({ py -3 -c $probe }, { python -c $probe }, { python3 -c $probe })
    foreach ($t in $tries) {
        try {
            $exe = & $t 2>$null
            # the WindowsApps "python" is the Microsoft Store stub, not a real install
            if ($LASTEXITCODE -eq 0 -and $exe -and -not ("$exe" -like "*WindowsApps*")) { return "$exe".Trim() }
        } catch { }
    }
    return $null
}

function Read-Conf {
    if (Test-Path $Conf) { return Get-Content $Conf -Raw | ConvertFrom-Json }
    return [pscustomobject]@{ scope = "all"; history = "all" }
}

function Write-Conf([string]$Scope, [string]$History) {
    New-Item -ItemType Directory -Force -Path $Eng | Out-Null
    [pscustomobject]@{ scope = $Scope; history = $History; tools_python = $VenvPy } |
        ConvertTo-Json | Set-Content -Path $Conf -Encoding UTF8
    Write-Host "Settings: scope=$Scope, history=$History"
}

function Ask-Conf {
    Write-Host ""
    Write-Host "What should be synced?"
    Write-Host "  1) Runs and weight: every activity with its original FIT file, plus weigh-ins"
    Write-Host "  2) All Garmin data: the above plus full activity records, daily summaries, sleep, HRV,"
    Write-Host "     VO2 max, steps, stress, hydration, Body Battery, and profile settings"
    $s = Read-Host "Choose 1 or 2 [2]"
    $scope = if ($s -eq "1") { "runs" } else { "all" }
    Write-Host ""
    Write-Host "How much history should the first sync pull?"
    Write-Host "  1) 1 month   2) 1 year   3) 3 years   4) All (back to your first activity)"
    $h = Read-Host "Choose 1-4 [4]"
    $hist = switch ($h) { "1" { "1m" } "2" { "1y" } "3" { "3y" } default { "all" } }
    Write-Conf $scope $hist
}

function Store-Key {
    Write-Host ""
    $sec = Read-Host "Paste your Garmin Personal API key, then press Enter (hidden)" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try { $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    $plain = ($plain -replace "\s", "")
    if (-not $plain) { throw "No key entered." }
    $clean = ConvertTo-SecureString $plain -AsPlainText -Force
    New-Item -ItemType Directory -Force -Path $Eng | Out-Null
    ConvertFrom-SecureString $clean | Set-Content -Path $KeyFile -Encoding ASCII
    # verify the round trip
    $back = ConvertTo-SecureString (Get-Content $KeyFile -Raw).Trim()
    $b2 = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($back)
    try { $chk = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b2) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b2) }
    if ($chk -ne $plain) { throw "The stored key doesn't match what was pasted. Try update-key again." }
    Write-Host "Key saved, encrypted for your Windows account ($($plain.Length) characters, verified)."
    $plain = $null; $chk = $null
}

function Invoke-Sync([string[]]$Extra = @()) {
    & $VenvPy -X utf8 (Join-Path $Eng "sync.py") --root $Data @Extra
}

function Run-Sync {
    $c = Read-Conf
    Write-Host ""
    Write-Host "Syncing $($c.scope) data, history $($c.history). A first sync can take a while (about 1 s per activity, more with 'all')."
    Write-Host "Progress: $Data\logs\sync.log"
    try { Invoke-Sync } catch { }
    Write-Host ""; Write-Host "Result:"; Get-Content (Join-Path $Data "status.json") -ErrorAction SilentlyContinue
}

switch ($Mode) {
    "update-key" { Store-Key; Run-Sync; exit 0 }
    "sync"       { Run-Sync; exit 0 }
    "rebuild"    { Invoke-Sync @("rebuild"); Write-Host "Dashboard: $Data\dashboards\claudromos.html"; exit 0 }
    "config"     { Ask-Conf; Run-Sync; exit 0 }
    "scope"      { if ($Value -notin @("runs", "all")) { throw "Usage: install.ps1 scope runs|all" }; Write-Conf $Value (Read-Conf).history; Run-Sync; exit 0 }
    "history"    { if ($Value -notin @("1m", "1y", "3y", "all")) { throw "Usage: install.ps1 history 1m|1y|3y|all" }; Write-Conf (Read-Conf).scope $Value; Run-Sync; exit 0 }
    "diagnose"   { Invoke-Sync @("diagnose"); exit 0 }
    "uninstall"  {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
        Remove-Item $KeyFile -ErrorAction SilentlyContinue
        Write-Host "Stopped the sync and removed the key. Your data in $Data was left in place."; exit 0 }
    "install"    { }
    default      { throw "Unknown option: $Mode" }
}

if (-not (Test-Path (Join-Path $Src "engine\sync.py"))) { throw "Run the install from the cloned claudromos repo (it needs engine\)." }
if (("$Src\").ToLower().StartsWith(("$Data\").ToLower())) { throw "The repo is inside the data folder $Data. Clone it somewhere else, e.g. $env:USERPROFILE\src\claudromos" }
$py = Find-Python
if (-not $py) { throw "Python 3 isn't installed. Install it with:  winget install Python.Python.3.12   then run this installer again." }
Write-Host "Using Python: $py"

foreach ($d in @("$Eng\tools", "$Eng\dashboards", "$Data\config", "$Data\logs", "$Data\dashboards")) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
Copy-Item "$Src\engine\sync.py" $Eng -Force
Copy-Item "$Src\engine\tools\*.py" "$Eng\tools" -Force
Copy-Item "$Src\engine\dashboards\claudromos.template.html" "$Eng\dashboards" -Force
Copy-Item "$Src\install.ps1" $Eng -Force
Write-Host "Engine installed in $Eng"

if (-not (Test-Path $VenvPy)) { Write-Host "Setting up the Python environment (one-off)..."; & $py -m venv (Join-Path $Eng "venv") }
& $VenvPy -m pip install -q --disable-pip-version-check --upgrade fitdecode
if ($LASTEXITCODE -ne 0) { Write-Warning "Could not install fitdecode; dashboards won't build until it is installed." }

if (-not (Test-Path $Conf)) { Ask-Conf } else { $c = Read-Conf; Write-Conf $c.scope $c.history }
if (-not (Test-Path $KeyFile)) { Store-Key } else { Write-Host "A key is already saved (use update-key to replace it)." }

# Task Scheduler can't watch a file, so the task runs every 15 minutes and the sync itself decides
# (--if-due): it syncs when 3 hours have passed or when .claudromos\trigger was touched.
New-Item -ItemType File -Force -Path (Join-Path $Eng "trigger") | Out-Null
$action = New-ScheduledTaskAction -Execute $VenvPyw -Argument "-X utf8 `"$Eng\sync.py`" --root `"$Data`" --if-due" -WorkingDirectory $Eng
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 15)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 3)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Claudromos: Garmin sync and dashboard rebuild" -Force | Out-Null
Write-Host "Scheduled: checks every 15 minutes, syncs every 3 hours or when $Eng\trigger is touched."

Run-Sync
Write-Host "Done. Data: $Data   Dashboard: $Data\dashboards\claudromos.html"
Write-Host "Next: in Claude, add the claudromos-coach skill and say `"set me up`"."
