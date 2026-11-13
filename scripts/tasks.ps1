# Windows equivalent of the Makefile. Usage: .\scripts\tasks.ps1 test
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('install', 'db', 'dev', 'test', 'lint', 'format', 'migrate')]
    [string]$Task
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$uv = if (Get-Command uv -ErrorAction SilentlyContinue) { @('uv') } else { @('py', '-3.12', '-m', 'uv') }

function Exec([string]$dir, [string[]]$cmd) {
    Push-Location $dir
    try {
        $exe, $rest = $cmd
        & $exe @rest
        if ($LASTEXITCODE -ne 0) { throw "'$($cmd -join ' ')' failed in $dir (exit $LASTEXITCODE)" }
    } finally { Pop-Location }
}

function ExecUv([string]$dir, [string[]]$cmd) { Exec $dir ($uv + $cmd) }

switch ($Task) {
    'install' {
        ExecUv $backend @('sync')
        Exec $frontend @('npm', 'ci')
    }
    'db' { Exec $root @('docker', 'compose', 'up', '-d', 'db') }
    'dev' {
        $api = ($uv + @('run', 'uvicorn', 'app.main:create_app', '--factory', '--reload', '--port', '8000')) -join ' '
        Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location '$backend'; $api"
        Exec $frontend @('npm', 'run', 'dev')
    }
    'test' {
        ExecUv $backend @('run', 'pytest')
        Exec $frontend @('npx', 'vitest', 'run', '--coverage')
    }
    'lint' {
        ExecUv $backend @('run', 'ruff', 'check', '.')
        ExecUv $backend @('run', 'ruff', 'format', '--check', '.')
        ExecUv $backend @('run', 'mypy')
        Exec $frontend @('npm', 'run', 'lint')
        Exec $frontend @('npm', 'run', 'typecheck')
    }
    'format' {
        ExecUv $backend @('run', 'ruff', 'check', '--fix', '.')
        ExecUv $backend @('run', 'ruff', 'format', '.')
    }
    'migrate' { ExecUv $backend @('run', 'python', '-m', 'app.db.migrate') }
}
