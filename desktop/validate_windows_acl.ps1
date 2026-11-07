param(
    [Parameter(Mandatory=$true)][string]$NewOutput,
    [string]$PythonPath = 'python',
    [string]$Sidecar = ''
)
$ErrorActionPreference = 'Stop'
if (-not $IsWindows) { throw 'Windows ACL validation only' }
$workspacePath = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
$cacheRoot = [IO.Path]::GetFullPath((Join-Path $workspacePath '.cache'))
$probeRoot = [IO.Path]::GetFullPath($NewOutput)
if (-not $probeRoot.StartsWith($cacheRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Test output must be within this checkout .cache' }
if (Test-Path -LiteralPath $probeRoot) { throw 'Existing output directory refused' }
# Refuse an existing directory junction/symlink that resolves outside our cache.
$ancestor = Split-Path $probeRoot -Parent
while ($ancestor) {
    if (Test-Path -LiteralPath $ancestor) {
        $item = Get-Item -LiteralPath $ancestor -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse-point test output refused' }
    }
    if ($ancestor -eq $workspacePath) { break }
    $ancestor = Split-Path $ancestor -Parent
}
New-Item -ItemType Directory -Path $probeRoot | Out-Null
[IO.File]::WriteAllText((Join-Path $probeRoot '.front-generated-acl-test'), 'generated ACL test only')
$deniedPath = Join-Path $probeRoot '中文 space & denied'
New-Item -ItemType Directory -Path $deniedPath | Out-Null
$samplePath = Join-Path $deniedPath 'generated-sentinel.txt'
[IO.File]::WriteAllText($samplePath, 'generated ACL regression sentinel')
$beforeHash = (Get-FileHash -LiteralPath $samplePath -Algorithm SHA256).Hash
$originalAcl = Get-Acl -LiteralPath $deniedPath
[IO.File]::WriteAllText((Join-Path $probeRoot 'original-acl.sddl'), $originalAcl.Sddl)
$restrictedAcl = Get-Acl -LiteralPath $deniedPath
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
$rule = [Security.AccessControl.FileSystemAccessRule]::new($identity,
    [Security.AccessControl.FileSystemRights]::Write,
    [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit',
    [Security.AccessControl.PropagationFlags]::None, [Security.AccessControl.AccessControlType]::Deny)
$restrictedAcl.AddAccessRule($rule)
$previousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = Join-Path $workspacePath 'backend'
$denied = $false
try {
    Set-Acl -LiteralPath $deniedPath -AclObject $restrictedAcl
    try { [IO.File]::WriteAllText((Join-Path $deniedPath 'must-not-write.txt'), 'must refuse') }
    catch { if ($_.Exception -is [UnauthorizedAccessException] -or $_.Exception.InnerException -is [UnauthorizedAccessException]) { $denied = $true } else { throw } }
    if (-not $denied) { throw 'Native ACL denial did not occur' }
    $probeArguments = @((Join-Path $PSScriptRoot 'acl_probe.py'), $deniedPath)
    if ($Sidecar) { $probeArguments += @('--sidecar', [IO.Path]::GetFullPath($Sidecar)) }
    $result = & $PythonPath @probeArguments
    if ($LASTEXITCODE -ne 0) { throw 'Front denied-directory regression failed' }
    $result | Write-Output
} finally {
    Set-Acl -LiteralPath $deniedPath -AclObject $originalAcl
    $env:PYTHONPATH = $previousPythonPath
}
[IO.File]::WriteAllText((Join-Path $deniedPath 'restored-write.txt'), 'ACL restored')
$beforeRaw = [Security.AccessControl.RawSecurityDescriptor]::new($originalAcl.Sddl)
$afterRaw = [Security.AccessControl.RawSecurityDescriptor]::new((Get-Acl -LiteralPath $deniedPath).Sddl)
$beforeRules = [byte[]]::new($beforeRaw.DiscretionaryAcl.BinaryLength)
$afterRules = [byte[]]::new($afterRaw.DiscretionaryAcl.BinaryLength)
$beforeRaw.DiscretionaryAcl.GetBinaryForm($beforeRules, 0)
$afterRaw.DiscretionaryAcl.GetBinaryForm($afterRules, 0)
# Windows may recompute the AI metadata flag after Set-Acl. Preserve every ACE,
# owner/group and all other control flags (including inheritance protection).
$metadataMask = -bnot [int][Security.AccessControl.ControlFlags]::DiscretionaryAclAutoInherited
if ($beforeRaw.Owner -ne $afterRaw.Owner -or $beforeRaw.Group -ne $afterRaw.Group -or
    (([int]$beforeRaw.ControlFlags -band $metadataMask) -ne ([int]$afterRaw.ControlFlags -band $metadataMask)) -or
    [Convert]::ToBase64String($beforeRules) -ne [Convert]::ToBase64String($afterRules)) { throw 'ACL restoration descriptor mismatch' }
if ((Get-FileHash -LiteralPath $samplePath -Algorithm SHA256).Hash -ne $beforeHash) { throw 'Generated sentinel changed' }
$report = @{ generated_only=$true; clean_vm=$false; actual_deny_ace=$true; acl_restored=$true; sentinel_sha256_unchanged=$true; private_originals_modified=$false; frozen=[bool]$Sidecar }
$report | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $probeRoot 'report.json') -Encoding utf8
$report | ConvertTo-Json -Compress
