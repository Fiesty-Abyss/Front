param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
$fixtureRoot=[IO.Path]::GetFullPath($Root)
$allowedRoot=[IO.Path]::GetFullPath((Join-Path $projectRoot '.cache'))
if (-not $fixtureRoot.StartsWith($allowedRoot + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Fixture must be in checkout cache' }
if ([IO.File]::ReadAllText((Join-Path $fixtureRoot '.front-generated-updater-test')) -ne 'generated updater fixture v1') { throw 'Unmarked test fixture refused' }
$directory=Get-Item -LiteralPath $fixtureRoot -Force
if ($directory.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Fixture reparse point refused' }
$owner=[Security.Principal.WindowsIdentity]::GetCurrent().User
$system=[Security.Principal.SecurityIdentifier]::new('S-1-5-18')
$acl=[Security.AccessControl.DirectorySecurity]::new()
$acl.SetOwner($owner)
$acl.SetAccessRuleProtection($true,$false)
foreach ($principal in @($owner,$system)) {
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($principal,
        [Security.AccessControl.FileSystemRights]::FullControl,
        [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit',
        [Security.AccessControl.PropagationFlags]::None,[Security.AccessControl.AccessControlType]::Allow))
}
Set-Acl -LiteralPath $fixtureRoot -AclObject $acl
$confirmed=Get-Acl -LiteralPath $fixtureRoot
if (-not $confirmed.AreAccessRulesProtected) { throw 'Fixture inheritance protection failed' }
$rules=$confirmed.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])
if ($rules.Count -ne 2 -or ($rules | Where-Object { $_.IdentityReference -ne $owner -and $_.IdentityReference -ne $system })) { throw 'Unexpected generated fixture access' }
