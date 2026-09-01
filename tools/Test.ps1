param(
    [string]$BlenderExe = $env:BLENDER_EXE
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$testScript = Join-Path $projectRoot 'tests\test_simple_todo.py'

if ([string]::IsNullOrWhiteSpace($BlenderExe)) {
    $blenderCommand = Get-Command blender -ErrorAction SilentlyContinue
    if ($null -ne $blenderCommand) {
        $BlenderExe = $blenderCommand.Source
    }
}

if (
    [string]::IsNullOrWhiteSpace($BlenderExe) -or
    -not (Test-Path -LiteralPath $BlenderExe -PathType Leaf)
) {
    throw 'Blender was not found. Pass -BlenderExe or set BLENDER_EXE.'
}

& $BlenderExe --background --factory-startup --python $testScript
if ($LASTEXITCODE -ne 0) {
    throw "ToDo List tests failed with exit code $LASTEXITCODE."
}
