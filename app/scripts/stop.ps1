param([ValidateSet('all','java','detector','ocr')][string]$Component='all',[switch]$Interrupt,[switch]$StopMysql)
$ErrorActionPreference='Stop'
$root=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$configPath=Join-Path $root 'app/config/local.json'
if(-not(Test-Path $configPath)){$configPath=Join-Path $root 'app/config/local.example.json'}
$config=Get-Content -Raw -LiteralPath $configPath|ConvertFrom-Json
$arguments=@('stop','--component',$Component)
if($Interrupt){$arguments+='--interrupt'}
if($StopMysql){$arguments+='--stop-mysql'}
& (Join-Path $root $config.python) -B (Join-Path $PSScriptRoot 'process_supervisor.py') @arguments
exit $LASTEXITCODE
