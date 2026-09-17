# RenderDoc preparation — 2026-09-17

## Current status: capture rejected; live-client entry point retired

The user ran the prepared script as administrator. RenderDoc printed
`Launched as ID 38920`; the game then rejected startup with the message
`检测到黑客工具。请关闭不必要的程序，重启机器后再试。(1-18000)`.
The original screenshot is user-supplied evidence; identifiers in the dialog are
not copied into this repository.

Read-only follow-up confirms the Vulkan layer is now correctly registered, no
RDC exists in `Validation/Captures`, and no Endfield/renderdoccmd/qrenderdoc
process remained at inspection time. The restriction is no longer a missing
administrator setup step. No further injection or capture attempts were made.

There was also a separate bug in our wrapper: RenderDoc 1.46's non-waiting
`capture` command returns the positive target-control identifier on successful
launch and prints it to stderr. It does not follow the usual zero-only-success
convention. `38920` is not an OS process ID and not by itself a failure code.
The old `$LASTEXITCODE -ne 0` check was incorrect. A valid initial launch report
does not establish game compatibility or successful frame capture.

Official source:
https://github.com/baldurk/renderdoc/blob/v1.46/renderdoccmd/renderdoccmd.cpp#L238-L257
https://github.com/baldurk/renderdoc/blob/v1.46/renderdoc/api/replay/control_types.h#L1642-L1659

`Tools/Start-EndfieldCapture.ps1` now reports this known block and exits with code
2 without requiring administrator rights or performing any launch/registration.
The old `.cmd` shortcut and `-UseLauncher` argument also reach that same read-only
status. Do not follow the superseded startup instructions below. No game files,
protection components or registry entries were changed during this follow-up.
Continue reconstruction using the existing official screenshot and static dump;
RenderDoc can still be used with a compatible development application such as
the user's own Unity reconstruction if needed.

## Earlier preparation record (superseded)

User requested an attempt at normal RenderDoc capture of the running game, and
provided an official Typhoeus details screenshot. It is stored only in the ignored
`Validation/LocalReference` directory because account identifiers are visible.

Verified locally:

- Game log reports Unity 2021.3.34f5 and Vulkan device creation. This is separate
  from the reconstruction project's Unity 2022.3.30f1 / URP environment.
- No existing RDC was found in the scoped workspace, Downloads or Desktop search.
- Downloaded the official portable RenderDoc 1.46 x64 archive from
  https://renderdoc.org/stable/1.46/RenderDoc_1.46_64.zip
- Archive SHA256: `9CA4D09ECABA2CC791168660D6FC2A7E3D70FE67146E87EC05C5F8DEA70772F7`.
- `renderdoccmd.exe` Authenticode signature status: Valid.
- `renderdoccmd vulkanlayer --explain` reports this build's layer unregistered,
  and requires `vulkanlayer --register --system` with administrator privileges.
- The agent's Windows process token is not administrator. No system layer was
  registered, no RenderDoc injection was attempted, and no RDC was produced.
- The user's running game was not closed or terminated.

## Earlier handoff (do not retry on this client)

1. Close the game normally when ready.
2. Right-click `Tools/Start-EndfieldCapture.cmd`, choose Run as administrator.
3. The script verifies the official executable signature, registers RenderDoc's
   capture layer using its documented command, then starts the game under capture.
4. Open Typhoeus details and confirm RenderDoc's capture overlay/connection before
   capturing. Use the capture hotkey configured by RenderDoc (default F12/PrintScreen).
5. RDC output prefix is printed by the script and points into `Validation/Captures`.

If the game requires the official launcher, the PowerShell script accepts
`-UseLauncher`, using RenderDoc's documented child-process capture option.
If normal launch or capture fails, retain its exact error for diagnosis. This
workflow does not remove, patch, disable or bypass any game protection.

The script was syntax-checked only; its elevated launch/capture path has not been
executed. A valid screenshot is useful for visual matching but does not contain
the GPU resources and state that an RDC supplies.

Official references:
https://renderdoc.org/docs/window/index.html
https://github.com/baldurk/renderdoc/releases/tag/v1.46
