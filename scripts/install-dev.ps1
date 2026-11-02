param(
    [string]$Root = (Join-Path $env:LOCALAPPDATA 'MAJIMeeting-DEV'),
    [string]$Bundle = '',
    [string]$Manifest = '',
    [switch]$NoShortcuts
)
$ErrorActionPreference = 'Stop'
if (-not (Get-Command py.exe -ErrorAction SilentlyContinue)) {
    throw 'Installez Python 3.11 x64 avec le lanceur py, puis relancez Installer-DEV.cmd.'
}
$installed = Test-Path (Join-Path $Root 'state.json')
$manager = Join-Path $PSScriptRoot 'dev_channel.py'
$arguments = @('-X', 'utf8', $manager, '--root', $Root, 'bootstrap', '--refresh')
$engine = (Get-Command py.exe).Source
if ($installed) {
    $state = Get-Content (Join-Path $Root 'state.json') -Raw | ConvertFrom-Json
    $fingerprint = [string]$state.current.runtime
    if ($fingerprint -notmatch '^[0-9a-f]{64}$') { throw 'Empreinte du runtime DEV invalide.' }
    $engine = Join-Path $Root ('runtimes/' + $fingerprint.Substring(0,16) + '/Scripts/python.exe')
    if (-not (Test-Path $engine)) { throw 'Le runtime DEV existant est introuvable.' }
    # The catalogue lock needs Qt; a base Python installation need not contain PySide6.
    $arguments = @('-I') + $arguments
    Write-Host 'Actualisation avec le runtime DEV existant, sans reinstaller les dependances.'
} else {
    $arguments = @('-3.11') + $arguments
}
if ($Bundle) { $arguments += @('--bundle', $Bundle, '--manifest', $Manifest) }
& $engine @arguments
if ($LASTEXITCODE -ne 0) { throw "Installation DEV interrompue. Consultez $Root/dev-errors.log" }
if (-not $NoShortcuts) {
    $shell = New-Object -ComObject WScript.Shell
    $desktop = [Environment]::GetFolderPath('Desktop')
    $menu = Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs/MAJIMeeting DEV'
    New-Item -ItemType Directory -Force $menu | Out-Null
    $console = (Get-Command py.exe).Source
    $hidden = (Get-Command pyw.exe -ErrorAction SilentlyContinue).Source
    if (-not $hidden) { $hidden = $console }
    $items = @(
        @('MAJIMeeting DEV', 'run', $hidden),
        @('Mettre a jour et lancer MAJIMeeting DEV', 'update', $console),
        @('Revenir a la version DEV precedente', 'rollback', $console),
        @('Copier mes reunions vers DEV', 'copy-data', $console)
    )
    foreach ($item in $items) {
        foreach ($directory in @($desktop, $menu)) {
            $link = $shell.CreateShortcut((Join-Path $directory ($item[0] + '.lnk')))
            $link.TargetPath = $item[2]
            $link.Arguments = '-3.11 -X utf8 "' + (Join-Path $Root 'launcher.py') + '" ' + $item[1]
            $link.WorkingDirectory = $Root
            $link.Save()
        }
    }
}
Write-Host "Installation terminee : $Root"
if ($installed) {
    Write-Host 'Donnees DEV conservees. Ne recopiez pas vos reunions : lancez MAJIMeeting DEV.'
} else {
    Write-Host 'Fermez les deux applications avant Copier mes reunions vers DEV.'
}
