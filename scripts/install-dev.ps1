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
$manager = Join-Path $PSScriptRoot 'dev_channel.py'
$arguments = @('-3.11', '-X', 'utf8', $manager, '--root', $Root, 'bootstrap')
if ($Bundle) { $arguments += @('--bundle', $Bundle, '--manifest', $Manifest) }
& py.exe @arguments
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
Write-Host 'Fermez les deux applications avant Copier mes reunions vers DEV.'
