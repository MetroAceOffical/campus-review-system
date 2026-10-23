param([Parameter(Mandatory=$true)][string]$Backup,[Parameter(Mandatory=$true)][string]$Target,[int]$Port=3318)
$ErrorActionPreference='Stop'
$root=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$configPath=Join-Path $root 'app/config/local.json'
if(-not(Test-Path $configPath)){$configPath=Join-Path $root 'app/config/local.example.json'}
$config=Get-Content -Raw -LiteralPath $configPath|ConvertFrom-Json
& (Join-Path $root $config.python) -B (Join-Path $PSScriptRoot 'backup_restore.py') restore --backup $Backup --target $Target --port $Port
exit $LASTEXITCODE
