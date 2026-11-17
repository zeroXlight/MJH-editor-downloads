param([string]$Runtime, [string]$Reader, [string]$Skeleton, [string]$Atlas, [string]$Output)
$ErrorActionPreference='Stop'
[void][System.Reflection.Assembly]::LoadFrom($Runtime)
Add-Type -Path $Reader -ReferencedAssemblies @($Runtime)
$data=[TemplateRuntimeReader]::Read($Skeleton,$Atlas)
$data | ConvertTo-Json -Depth 60 -Compress | Set-Content -LiteralPath $Output -Encoding utf8
