@echo off
setlocal EnableExtensions

if /I "%~1"=="/?" goto help
if /I "%~1"=="-h" goto help
if /I "%~1"=="--help" goto help
if /I "%~1"=="--launch" goto launch

where powershell.exe >nul 2>nul
if errorlevel 1 (
    echo PowerShell powershell.exe was not found.
    exit /b 1
)

if /I "%~1"=="/remove" goto run_payload
if /I "%~1"=="-remove" goto run_payload
if /I "%~1"=="uninstall" goto run_payload
if /I "%~1"=="--dry-run" goto run_payload

where wt.exe >nul 2>nul
if errorlevel 1 (
    if not exist "%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe" (
        echo Warning: Windows Terminal wt.exe was not found.
        echo The menu will use a normal PowerShell window as a fallback.
    )
)

where codex >nul 2>nul
if errorlevel 1 (
    if not exist "%APPDATA%\npm\codex.cmd" (
        echo Warning: codex was not found in PATH.
        echo The menu will be created, but Codex may not launch until PATH is fixed.
    )
)

:run_payload
set "CODEX_CONTEXT_ACTION=%~1"
set "CODEX_CONTEXT_SCRIPT=%~f0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'Stop'; $marker = '(?m)^# POWERSHELL_PAYLOAD\r?$'; $content = Get-Content -Raw -LiteralPath $env:CODEX_CONTEXT_SCRIPT; $parts = $content -split $marker, 2; if ($parts.Count -lt 2) { throw 'PowerShell payload not found.' }; & ([scriptblock]::Create($parts[1]))"
exit /b %ERRORLEVEL%

:help
echo Usage:
echo   %~nx0          Add the context menu item.
echo   %~nx0 /remove  Remove the context menu item.
echo.
echo The menu opens Windows Terminal with PowerShell in the chosen directory,
echo then starts Codex CLI. If Windows Terminal is unavailable, it falls back
echo to a normal PowerShell window.
exit /b 0

:launch
set "CODEX_CONTEXT_DIR=%~2"
set "CODEX_CONTEXT_CODEX=%~3"
set "CODEX_CONTEXT_WT=%~4"

if not defined CODEX_CONTEXT_DIR set "CODEX_CONTEXT_DIR=%CD%"
if not exist "%CODEX_CONTEXT_DIR%\." (
    echo The selected path is not a directory:
    echo %CODEX_CONTEXT_DIR%
    pause
    exit /b 1
)

if not defined CODEX_CONTEXT_CODEX (
    for /f "delims=" %%I in ('where codex 2^>nul') do if not defined CODEX_CONTEXT_CODEX set "CODEX_CONTEXT_CODEX=%%I"
)
if not defined CODEX_CONTEXT_CODEX if exist "%APPDATA%\npm\codex.cmd" set "CODEX_CONTEXT_CODEX=%APPDATA%\npm\codex.cmd"

if not defined CODEX_CONTEXT_WT (
    for /f "delims=" %%I in ('where wt.exe 2^>nul') do if not defined CODEX_CONTEXT_WT set "CODEX_CONTEXT_WT=%%I"
)
if not defined CODEX_CONTEXT_WT if exist "%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe" set "CODEX_CONTEXT_WT=%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe"

if defined CODEX_CONTEXT_WT (
    if defined CODEX_CONTEXT_CODEX (
        start "" "%CODEX_CONTEXT_WT%" -d "%CODEX_CONTEXT_DIR%" powershell.exe -NoLogo -NoExit -ExecutionPolicy Bypass -Command "& $env:CODEX_CONTEXT_CODEX"
    ) else (
        start "" "%CODEX_CONTEXT_WT%" -d "%CODEX_CONTEXT_DIR%" powershell.exe -NoLogo -NoExit -ExecutionPolicy Bypass -Command "Write-Host 'codex was not found in PATH.' -ForegroundColor Red"
    )
) else (
    if defined CODEX_CONTEXT_CODEX (
        start "Codex CLI" /D "%CODEX_CONTEXT_DIR%" powershell.exe -NoLogo -NoExit -ExecutionPolicy Bypass -Command "& $env:CODEX_CONTEXT_CODEX"
    ) else (
        start "Codex CLI" /D "%CODEX_CONTEXT_DIR%" powershell.exe -NoLogo -NoExit -ExecutionPolicy Bypass -Command "Write-Host 'codex was not found in PATH.' -ForegroundColor Red"
    )
)
exit /b %ERRORLEVEL%

# POWERSHELL_PAYLOAD
$ErrorActionPreference = 'Stop'

$action = $env:CODEX_CONTEXT_ACTION
if ([string]::IsNullOrWhiteSpace($action)) {
    $normalizedAction = ''
} else {
    $normalizedAction = $action.ToLowerInvariant()
}

$menuKey = 'OpenCodexCLIHere'
$menuText = [string]::Concat([char[]](0x5728, 0x8FD9, 0x91CC, 0x6253, 0x5F00)) + 'codex CLI'
$valueKind = [Microsoft.Win32.RegistryValueKind]::String
$scriptPath = $env:CODEX_CONTEXT_SCRIPT

function Resolve-CommandPath([string]$name) {
    $command = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $command) {
        return ''
    }
    if (-not [string]::IsNullOrWhiteSpace($command.Source)) {
        return $command.Source
    }
    if (-not [string]::IsNullOrWhiteSpace($command.Path)) {
        return $command.Path
    }
    return ''
}

function Quote-Argument([string]$value) {
    if ($null -eq $value) {
        return '""'
    }
    return '"' + ($value -replace '"', '\"') + '"'
}

$codexPath = Resolve-CommandPath 'codex'
if ([string]::IsNullOrWhiteSpace($codexPath)) {
    $npmCodex = Join-Path $env:APPDATA 'npm\codex.cmd'
    if (Test-Path -LiteralPath $npmCodex) {
        $codexPath = $npmCodex
    }
}

$wtPath = Resolve-CommandPath 'wt.exe'
if ([string]::IsNullOrWhiteSpace($wtPath)) {
    $windowsAppsWt = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\wt.exe'
    if (Test-Path -LiteralPath $windowsAppsWt) {
        $wtPath = $windowsAppsWt
    }
}

$entries = @(
    @{ Key = "Software\Classes\Directory\Background\shell\$menuKey"; Token = '%V' },
    @{ Key = "Software\Classes\Directory\shell\$menuKey"; Token = '%1' },
    @{ Key = "Software\Classes\Drive\shell\$menuKey"; Token = '%1' }
)

if ($normalizedAction -in @('/remove', '-remove', 'uninstall')) {
    foreach ($entry in $entries) {
        try {
            [Microsoft.Win32.Registry]::CurrentUser.DeleteSubKeyTree($entry.Key, $false)
        } catch {
            if ($_.Exception.GetType().FullName -ne 'System.ArgumentException') {
                throw
            }
        }
    }

    Write-Host "Removed context menu: $menuText"
    exit 0
}

$dryRun = $normalizedAction -eq '--dry-run'

foreach ($entry in $entries) {
    $command = (Quote-Argument $scriptPath) + ' --launch "' + $entry.Token + '" ' + (Quote-Argument $codexPath) + ' ' + (Quote-Argument $wtPath)

    if ($dryRun) {
        Write-Host ($entry.Key + ' -> ' + $command)
        continue
    }

    $key = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($entry.Key)
    try {
        $key.SetValue('', $menuText, $valueKind)
        $key.SetValue('MUIVerb', $menuText, $valueKind)
        $key.SetValue('Icon', 'wt.exe', $valueKind)
        $key.SetValue('Position', 'Top', $valueKind)

        $commandKey = $key.CreateSubKey('command')
        try {
            $commandKey.SetValue('', $command, $valueKind)
        } finally {
            $commandKey.Close()
        }
    } finally {
        $key.Close()
    }
}

if ($dryRun) {
    Write-Host 'Dry run completed. No registry keys were changed.'
} else {
    Write-Host "Added context menu: $menuText"
    Write-Host 'Use this item from a folder background, selected folder, or drive root.'
    Write-Host 'Run this batch with /remove to uninstall the menu item.'
}
