"""``knowhow vlm providers`` and ``knowhow vlm ping``: is the configured VLM reachable and sane?

``ping`` sends a synthetic clip whose answer depends on frame ORDER (a red square sliding into a
box), or frames of a real video.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer

from mentormind.core.config import Settings, get_settings
from mentormind.core.schemas.common import DataClassification

if TYPE_CHECKING:
    from mentormind.core.providers.vlm import VLMProvider
PING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "moving_object_color": {"type": "string"},
        "direction": {"enum": ["left_to_right", "right_to_left", "static", "other"]},
        "ends_inside_box": {"type": "boolean"},
    },
    "required": ["moving_object_color", "direction", "ends_inside_box"],
}
PING_PROMPT = (
    "Các ảnh sau là {n} khung hình liên tiếp của một video ngắn, theo đúng thứ tự thời gian. "
    "Vật nào đang di chuyển, theo hướng nào, và cuối cùng có nằm trong hộp không? "
    'Trả về DUY NHẤT JSON: {{"moving_object_color": str, '
    '"direction": "left_to_right|right_to_left|static|other", "ends_inside_box": bool}}'
)
VIDEO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "steps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "steps"],
}
VIDEO_PROMPT = (
    "Các ảnh sau là {n} khung hình liên tiếp của một video dài {duration:.1f}s, lấy mẫu {fps} "
    "khung/giây, theo đúng thứ tự thời gian. Chỉ mô tả điều nhìn thấy, không suy đoán lý do. "
    'Trả về DUY NHẤT JSON: {{"summary": str, "steps": [str]}} — mỗi bước bắt đầu bằng động từ.'
)


def providers_cmd() -> None:
    """List registered VLM providers, the selected one and whether each has its key."""
    from mentormind.core.config import lookup_secret
    from mentormind.core.providers.openai_compat import OPENAI_COMPAT_ENDPOINTS
    from mentormind.core.providers.vlm import VLM_REGISTRY
    from mentormind.core.providers.vlm.catalog import default_vlm_model

    settings = get_settings()
    typer.echo(f"{'':2}{'provider':<20}{'nơi chạy':<10}{'model mặc định':<32}api key")
    for name in VLM_REGISTRY.names():
        endpoint = OPENAI_COMPAT_ENDPOINTS.get(name)
        where = "cloud" if endpoint and endpoint.is_cloud else "local"
        key_env = VLM_REGISTRY[name].api_key_env(name)
        if key_env is None:
            key = "không cần"
        elif lookup_secret(key_env, secrets_file=settings.secrets_file):
            key = f"{key_env} ✓"
        else:
            key = f"{key_env} (chưa đặt)"
        marker = "*" if name == settings.vlm_provider else " "
        model = default_vlm_model(name) or "(KNOWHOW_VLM_MODEL)"
        typer.echo(f"{marker} {name:<20}{where:<10}{model:<32}{key}")
    typer.echo("\n* = KNOWHOW_VLM_PROVIDER. Key đặt trong .env; cách lấy key: .secrets/README.md")


def ping_cmd(
    provider: Annotated[str | None, typer.Option(help="Ghi đè KNOWHOW_VLM_PROVIDER cho lần chạy này.")] = None,
    video: Annotated[Path | None, typer.Option(exists=True, dir_okay=False, help="Mô tả video thật này.")] = None,
    classification: Annotated[
        DataClassification,
        typer.Option(help="Nhãn dữ liệu của --video; mặc định coi là dữ liệu nhà máy."),
    ] = DataClassification.FACTORY_CONFIDENTIAL,
    frames: Annotated[int, typer.Option(min=2, max=64, help="Số khung của clip tổng hợp.")] = 8,
) -> None:
    """Call the configured VLM with several frames; print answer, latency and tokens."""
    from mentormind.core.providers.errors import ProviderError
    from mentormind.core.providers.vlm import get_vlm_provider

    settings = get_settings()
    if provider:
        settings = settings.model_copy(update={"vlm_provider": provider})
    try:
        vlm = get_vlm_provider(settings)
        with tempfile.TemporaryDirectory(prefix="knowhow-ping-") as tmp:
            if video is None:
                paths = _synthetic_clip(Path(tmp), frames)
                prompt, schema = PING_PROMPT.format(n=len(paths)), PING_SCHEMA
                label: DataClassification = DataClassification.SYNTHETIC
                temperature = 0.0  # deterministic PASS/FAIL
            else:
                paths, prompt = _video_frames(video, classification, vlm, Path(tmp), settings)
                schema, label = VIDEO_SCHEMA, classification
                temperature = 0.2  # greedy decoding makes Qwen3-VL loop long step lists
            response = vlm.generate(paths, prompt, classification=label, json_schema=schema, temperature=temperature)
    except (ProviderError, PermissionError, ValueError) as exc:
        typer.secho(f"Lỗi: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc

    usage = response.usage
    tokens = f"{usage.prompt_tokens} vào / {usage.completion_tokens} ra" if usage else "n/a"
    typer.echo(f"provider={response.provider} model={response.model} cloud={vlm.is_cloud}")
    typer.echo(f"{len(paths)} khung | {response.latency_s:.2f}s | token: {tokens}")
    typer.echo(response.text)
    if video is None:
        from mentormind.core.providers.parsing import parse_json_object

        answer = parse_json_object(response.text)
        ok = answer.get("direction") == "left_to_right" and answer.get("ends_inside_box") is True
        typer.secho("PASS" if ok else "FAIL", fg=typer.colors.GREEN if ok else typer.colors.RED)
        raise typer.Exit(0 if ok else 1)


def _synthetic_clip(out_dir: Path, count: int) -> list[Path]:
    """JPEG frames of a red square sliding left -> right into a blue open box."""
    from PIL import Image, ImageDraw

    width, height = 448, 252
    box_left = width - 130
    paths = []
    for i in range(count):
        image = Image.new("RGB", (width, height), (200, 200, 200))
        draw = ImageDraw.Draw(image)
        draw.rectangle((box_left, 90, width - 20, 230), outline=(30, 60, 220), width=6)
        x = 20 + round((box_left + 25 - 20) * i / (count - 1))
        draw.rectangle((x, 150, x + 50, 200), fill=(220, 30, 30))
        path = out_dir / f"ping_{i:03d}.jpg"
        image.save(path, format="JPEG", quality=90)
        paths.append(path)
    return paths


def _video_frames(
    video: Path,
    classification: DataClassification,
    vlm: VLMProvider,
    out_dir: Path,
    settings: Settings,
) -> tuple[list[Path], str]:
    """Sample the whole video as one segment (motion unknown -> KNOWHOW_VLM_FPS)."""
    import cv2

    from mentormind.core.schemas.video import Segment
    from mentormind.processing.vlm.frames.sampler import sample_frames

    capture = cv2.VideoCapture(str(video))
    duration = capture.get(cv2.CAP_PROP_FRAME_COUNT) / (capture.get(cv2.CAP_PROP_FPS) or 30.0)
    capture.release()
    segment = Segment(
        segment_id="PING-S000",
        video_id="PING",
        index=0,
        t_start=0.0,
        t_end=duration,
        method="fixed_window",
        motion_score=None,
        keyframes=[],
        clip_path=str(video),
        data_classification=classification,
    )
    sampled = sample_frames(
        segment,
        vlm,
        out_dir=out_dir,
        default_fps=settings.vlm_fps,
        max_frames=settings.vlm_max_frames,
    )
    prompt = VIDEO_PROMPT.format(n=len(sampled.paths), duration=duration, fps=sampled.fps)
    return sampled.paths, prompt
