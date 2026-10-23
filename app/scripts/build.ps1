$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$configPath = Join-Path $root 'app/config/local.json'
if (-not (Test-Path $configPath)) { $configPath = Join-Path $root 'app/config/local.example.json' }
$config = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
$env:CAMPUS_ROOT = $root.Replace('\','/')
$env:JAVA_HOME = Split-Path (Split-Path $config.java -Parent) -Parent
Push-Location (Join-Path $root 'app/frontend')
try {
    & (Join-Path (Split-Path $config.node -Parent) 'npm.cmd') run build
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally { Pop-Location }
$staticPath = [IO.Path]::GetFullPath((Join-Path $root 'app/backend/src/main/resources/static'))
$allowedPath = [IO.Path]::GetFullPath((Join-Path $root 'app/backend/src/main/resources'))
if (-not $staticPath.StartsWith($allowedPath + [IO.Path]::DirectorySeparatorChar)) { throw 'Invalid generated static directory' }
if (Test-Path $staticPath) { Remove-Item -LiteralPath $staticPath -Recurse -Force }
New-Item -ItemType Directory -Force -Path $staticPath | Out-Null
Copy-Item -Path (Join-Path $root 'app/frontend/dist/*') -Destination $staticPath -Recurse
Push-Location (Join-Path $root 'app/backend')
try {
    & $config.maven -B -ntp -s settings.xml "-Dmaven.repo.local=$root/$($config.runtimeRoot)/m2-repository" -DskipTests package
    $result = $LASTEXITCODE
} finally { Pop-Location }
exit $result
