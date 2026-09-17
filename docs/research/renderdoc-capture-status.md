# RenderDoc preparation — 2026-09-17

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

## Prepared handoff

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
