$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Py = "python"
if (Get-Command py -ErrorAction SilentlyContinue) {
  $Py = "py"
}

& $Py "$ScriptDir/nsx.py" @args
