param()
$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$configPath = Join-Path $root 'app/config/local.json'
if (-not (Test-Path $configPath)) { $configPath = Join-Path $root 'app/config/local.example.json' }
$config = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
$python = Join-Path $root $config.python
& $python -B (Join-Path $PSScriptRoot 'runtime_manager.py') mysql-start
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python -B (Join-Path $PSScriptRoot 'runtime_manager.py') inventory
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python -B (Join-Path $PSScriptRoot 'runtime_manager.py') accounts
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$runtime = Join-Path $root $config.runtimeRoot
$env:CAMPUS_ROOT = $root.Replace('\','/')
$env:JAVA_HOME = Split-Path (Split-Path $config.java -Parent) -Parent
Push-Location (Join-Path $root 'app/backend')
try {
    & $config.maven -B -ntp -s settings.xml "-Dmaven.repo.local=$runtime/m2-repository" compile
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $connector = Get-ChildItem -LiteralPath (Join-Path $runtime 'm2-repository/com/mysql/mysql-connector-j') -Recurse -Filter '*.jar' | Select-Object -First 1
    if (-not $connector) { throw 'MySQL JDBC dependency missing' }
    $credential = Get-Content -Raw -LiteralPath (Join-Path $runtime 'private-config/database.json') | ConvertFrom-Json
    $env:CAMPUS_DB_USER = 'campus_app'
    $env:CAMPUS_DB_PASSWORD = $credential.app
    $env:CAMPUS_DB_URL = "jdbc:mysql://127.0.0.1:3308/$($config.database)?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true"
    & $config.java -cp "target/classes;$($connector.FullName)" local.campus.review.bootstrap.MigrationRunner src/main/resources/db/migrations
    $result = $LASTEXITCODE
} finally { Pop-Location; Remove-Item Env:CAMPUS_DB_PASSWORD -ErrorAction SilentlyContinue }
exit $result
