# Typhoeus URP geometry/rendering repair — 2026-09-17

## Confirmed causes

The apparent exploding model was reproducible with `Endfield/CharacterLit` but
not with URP Lit on the same static or baked skinned mesh.

- Imported clothing materials set `_OutlineMaxWidth = 3`. The previous outline
  vertex shader interpreted this as world-space meters. At width 0.5 it extruded
  a roughly 1.6 m character by about 1.6 m. Widths are now bounded screen pixels;
  this is a URP adaptation, not a claim about HGRP's exact original formula.
- `_ZTest = 3` (Equal) relied on the source pipeline's depth prepass. The standalone
  forward pass now uses LessEqual and opaque materials write depth.
- Reconstructed meshes lacked tangents. They now recalculate tangents, and shader
  code handles absent tangent/UV7 channels without normalizing a zero vector.
- The capture framed/scaled only the first VFX mesh. It now frames baked vertices
  across all enabled character renderers without scaling the character.
- Rebuilt meshes are now persistent `.asset` files with stable GUIDs on rebuild.
- Ramp highlights are modulated by material reflectance and incident light to
  avoid washing dark clothing out to white.

## Validation

Actual running editor: Unity 2022.3.30f1, resolved URP 14.0.11. The existing manifest
requests URP 14.0.12; that discrepancy predates this repair. Shader sampling uses
a private inline sampler to avoid depending on minor-version global declarations.

1. Raw extracted triangles have reasonable edge lengths; shared bind matrices agree.
2. Original static and baked skinned geometry both render as a complete character.
3. Reopened saved scene contains all 17 persistent meshes, tangents and materials.
4. Maximum rest-pose vertex displacement: about 0.0000216 m (weight quantization).
5. Rotating the head 15 degrees moves 22,141 vertices. Unity BakeMesh agrees with
   independent four-weight skinning within 0.000000479 m. The pose is restored.
6. Character shader reports no compilation errors. Front, side and rear screenshots
   are in `Validation/verified-*.png`; numerical output is `geometry-report.txt`.

Run `Endfield / Capture Showcase Screenshot`, then `Endfield / Validate Saved Showcase`.
Open `Assets/Scenes/Typhoeus_Showcase.unity`. These commands rebuild/open the showcase,
so save unrelated scene edits first. The original active scene has a local recovery
copy at `Assets/Scenes/Recovery/BeforeGeometryFix_20260917.unity`.

## Remaining rendering work

This resolves the observed explosion and missing opaque body. It is not a complete
match to the game. Dedicated HGRP hair/eye shadow shells and VFX shells remain in
the hierarchy with their renderers disabled until their stencil/effect passes are
ported. Hair highlights, translucent cloth and face shading need further work.
Existing unrelated Ruri Caustics sample shader errors are outside this change.

The supplied NGA and Zhihu pages returned HTTP 403, and tajourney.games/5607 returned
502 during this session. No technical claim above relies on unread page content.
The repair used local extracted mesh/material data and controlled rendering probes.

## GitHub checkpoints

User requested a GitHub commit after each completed change. Destination is the
user-owned `LinXingjian365/FractalMiner`, not the read-only upstream. Record scoped
code/assets plus validation evidence on a dedicated branch, preserve unrelated
working-tree changes, and report the pushed commit. Do not use `git add .` here.
This checkpoint is based on the user's remote main at `6cd186f`.
