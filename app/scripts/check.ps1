param([Parameter(Mandatory=$true)][string]$Task, [switch]$RealModels)
$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$tests = @{ M01 = 'MigrationIT'; M02 = 'AuthAccessIT'; M03 = 'DocumentCodecTest,FileAccessIT,DraftIT'; M04 = 'PYTHON'; M05 = 'OCR'; M06 = 'LibraryGenerationIT'; M07 = 'QueueIT,LateResultIT,FaultPipelineIT,RealPipelineIT'; M08 = 'SubmissionIT,DecisionIT'; ALL = '*IT,*Test' }
if (-not $tests.ContainsKey($Task)) { Write-Error "Task $Task has no implemented verification entry"; exit 2 }
$configPath = Join-Path $root 'app/config/local.json'
if (-not (Test-Path $configPath)) { $configPath = Join-Path $root 'app/config/local.example.json' }
$config = Get-Content -Raw -LiteralPath $configPath | ConvertFrom-Json
$env:CAMPUS_ROOT = $root.Replace('\','/')
$env:JAVA_HOME = Split-Path (Split-Path $config.java -Parent) -Parent
$runtime = Join-Path $root $config.runtimeRoot
if ($Task -eq 'M04') {
    $env:PYTHONPATH = Join-Path $root 'app/python'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:HF_HUB_OFFLINE = '1'
    $env:TRANSFORMERS_OFFLINE = '1'
    $env:CAMPUS_REAL_MODELS = if ($RealModels) { '1' } else { '0' }
    & (Join-Path $root $config.python) -B (Join-Path $root 'app/python/run_checks.py') main
    exit $LASTEXITCODE
}
if ($Task -eq 'M05') {
    $env:PYTHONPATH = Join-Path $root 'app/python'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:PYTHONUTF8 = '1'
    $env:CAMPUS_REAL_MODELS = if ($RealModels) { '1' } else { '0' }
    & (Join-Path $root $config.ocrPython) -B (Join-Path $root 'app/python/run_checks.py') ocr
    exit $LASTEXITCODE
}
$env:CAMPUS_MIGRATIONS = Join-Path $root 'app/backend/src/main/resources/db/migrations'
$env:CAMPUS_ACCOUNTS_FILE = Join-Path $runtime 'private-config/accounts.json'
$credentialPath = Join-Path $runtime 'private-config/database.json'
if (Test-Path $credentialPath) {
    $credential = Get-Content -Raw -LiteralPath $credentialPath | ConvertFrom-Json
    $env:CAMPUS_TEST_DB_USER = 'campus_test'
    $env:CAMPUS_TEST_DB_PASSWORD = $credential.test
}
$env:CAMPUS_TEST_DB_URL = "jdbc:mysql://127.0.0.1:$($config.ports.mysql)/$($config.testDatabase)?connectionTimeZone=UTC&forceConnectionTimeZoneToSession=true"
$env:CAMPUS_RUNTIME_NAMESPACE = 'test'
$env:CAMPUS_REAL_MODELS = if ($RealModels) { '1' } else { '0' }
Push-Location (Join-Path $root 'app/backend')
try {
    & $config.maven -B -ntp -s settings.xml "-Dmaven.repo.local=$runtime/m2-repository" "-Dtest=$($tests[$Task])" test
    $result = $LASTEXITCODE
} finally { Pop-Location; Remove-Item Env:CAMPUS_TEST_DB_PASSWORD -ErrorAction SilentlyContinue }
if ($result -ne 0) { exit $result }
if ($Task -in @('M02','M03','ALL')) {
    Push-Location (Join-Path $root 'app/frontend')
    try {
        & (Join-Path (Split-Path $config.node -Parent) 'npm.cmd') test
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & (Join-Path (Split-Path $config.node -Parent) 'npm.cmd') run build
        $result = $LASTEXITCODE
    } finally { Pop-Location }
}
if ($Task -in @('M01','M03','ALL')) {
    & (Join-Path $root $config.python) -B -m unittest discover -s (Join-Path $PSScriptRoot 'tests')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if ($Task -eq 'ALL') {
    $env:PYTHONPATH = Join-Path $root 'app/python'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:HF_HUB_OFFLINE = '1'
    $env:TRANSFORMERS_OFFLINE = '1'
    $env:CAMPUS_REAL_MODELS = if ($RealModels) { '1' } else { '0' }
    & (Join-Path $root $config.python) -B (Join-Path $root 'app/python/run_checks.py') main
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & (Join-Path $root $config.ocrPython) -B (Join-Path $root 'app/python/run_checks.py') ocr
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
exit $result
