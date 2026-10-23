param([ValidateSet('all','java','detector','ocr')][string]$Component='all')
$ErrorActionPreference='Stop'
$root=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$configPath=Join-Path $root 'app/config/local.json'
if(-not(Test-Path $configPath)){$configPath=Join-Path $root 'app/config/local.example.json'}
$config=Get-Content -Raw -LiteralPath $configPath|ConvertFrom-Json
& (Join-Path $root $config.python) -B (Join-Path $PSScriptRoot 'process_supervisor.py') start --component $Component
exit $LASTEXITCODE
