"""Prepare color-space-safe references for the M5 pose renderer.

Frame 6411 has two different capture stages. Resource 19394 is linear HDR input
to the captured post pass. Resource 19599 is the post pass output: RGBA8_UNORM
whose values have already been shader-encoded to sRGB. A post-processed Unity
PNG must only be compared with the latter; this module makes that contract
explicit instead of silently comparing different transfer functions.
"""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

from PIL import Image

DXGI_R8G8B8A8_UNORM = 28
_DDS_DX10_OFFSET = 128
_DDS_PAYLOAD_OFFSET = 148


def _u32(blob: bytes, offset: int) -> int:
    return struct.unpack_from("<I", blob, offset)[0]


def read_rgba8_header(path: Path) -> tuple[int, int, bytes]:
    blob = path.read_bytes()
    if len(blob) < 128 or blob[:4] != b"DDS " or _u32(blob, 4) != 124:
        raise ValueError("Expected DDS with a complete 124-byte header")
    width, height = _u32(blob, 16), _u32(blob, 12)
    if width < 1 or height < 1:
        raise ValueError("DDS dimensions must be positive")
    fourcc = _u32(blob, 84)
    if fourcc == 0x30315844:
        if len(blob) < _DDS_PAYLOAD_OFFSET:
            raise ValueError("Expected a complete DDS DX10 header")
        dxgi = _u32(blob, _DDS_DX10_OFFSET)
        if dxgi != DXGI_R8G8B8A8_UNORM:
            raise ValueError("Expected post-output DXGI R8G8B8A8_UNORM, got DXGI {}".format(dxgi))
        return width, height, blob[_DDS_PAYLOAD_OFFSET:]
    # RenderDoc is permitted to write the same RGBA8_UNORM resource using the
    # legacy DDS_PIXELFORMAT masks. The frame-6411 post-output does exactly this.
    if (fourcc != 0 or _u32(blob, 80) != 0x41 or _u32(blob, 88) != 32
            or tuple(_u32(blob, offset) for offset in (92, 96, 100, 104))
            != (0xff, 0xff00, 0xff0000, 0xff000000)):
        raise ValueError("Expected post-output legacy RGBA8 masks or DXGI R8G8B8A8_UNORM")
    return width, height, blob[128:]


def write_post_output_png(source: Path, target: Path) -> None:
    """Convert captured event1205 output to a display PNG without re-encoding RGB.

    RenderDoc's DDS payload rows are vertically opposite to the Unity readback
    convention used by pose-applied-lit-post.png, hence the one explicit flip.
    The bytes are already shader-encoded sRGB and must never receive Reinhard or
    gamma conversion in this path.
    """
    width, height, payload = read_rgba8_header(source)
    expected = width * height * 4
    if len(payload) != expected:
        raise ValueError("Expected {} RGBA8 payload bytes, got {}".format(expected, len(payload)))
    image = Image.frombytes("RGBA", (width, height), payload)
    image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)


def reference_contract(stage: str) -> dict:
    if stage == "prepost":
        return {
            "capture_resource": 19394,
            "source_format": "R16G16B16A16_FLOAT",
            "encoding": "linear-HDR",
            "vertical_flip": True,
        }
    if stage == "post":
        return {
            "capture_resource": 19599,
            "source_format": "R8G8B8A8_UNORM",
            "encoding": "shader-encoded-sRGB",
            "vertical_flip": True,
        }
    raise ValueError("Unknown capture stage: {}".format(stage))


def require_compatible_stages(reference_stage: str, current_stage: str) -> None:
    if reference_stage != current_stage:
        raise ValueError(
            "Cannot compare {} reference with {} current output: compare post-output "
            "only to post-processed output, or compare prepost HDR in a shared linear domain."
            .format(reference_stage, current_stage))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path,
        default=Path("Validation/Captures/tifuluosi-front-20260917/pipeline-textures-01/post-output.dds"))
    parser.add_argument("--output", type=Path,
        default=Path("Validation/Captures/tifuluosi-front-20260917/pipeline-textures-01/post-output-flipped.png"))
    args = parser.parse_args()
    write_post_output_png(args.source, args.output)
    print("wrote {} from event1205 post-output (no RGB transfer conversion)".format(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
