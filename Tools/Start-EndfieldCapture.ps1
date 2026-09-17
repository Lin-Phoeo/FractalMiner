[CmdletBinding()]
param([switch]$UseLauncher)

# Retired after the user's normal capture attempt was rejected by the game.
# Keep this entry point so old shortcuts cannot silently retry injection.
# This script does not register layers, start processes, or change the system.
Write-Output 'Endfield RenderDoc capture is stopped for this client.'
Write-Output 'The game rejected the normal capture launch with protection error 1-18000.'
Write-Output 'RenderDoc reported a launch identifier, not a completed frame capture.'
Write-Output 'The previous script incorrectly treated that identifier as a failure exit code.'
Write-Output 'Do not repeat capture through this entry point or its launcher option.'
Write-Output 'Use the official launcher normally. Reconstruction continues from local screenshots and extracted shader data.'
Write-Output 'Details: docs/research/renderdoc-capture-status.md'
exit 2
