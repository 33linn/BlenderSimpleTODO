param(
    [string]$BlenderExe = $env:BLENDER_EXE
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$testScripts = @(
    (Join-Path $projectRoot 'tests\test_simple_todo.py'),
    (Join-Path $projectRoot 'tests\test_history_selection.py')
)

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

foreach ($testScript in $testScripts) {
    & $BlenderExe --background --factory-startup --python $testScript
    if ($LASTEXITCODE -ne 0) {
        throw "ToDo List test failed: $testScript (exit code $LASTEXITCODE)."
    }
}
