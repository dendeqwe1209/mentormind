"""``knowhow video probe|segment|transcribe|providers`` (spec 03 FR-01, FR-02, FR-07, FR-07b, FR-07c)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from mentormind.core.config import Settings, get_settings
from mentormind.core.schemas.common import DataClassification

app = typer.Typer(help="Cắt video, keyframe, clip, transcript (spec 03).", no_args_is_help=True)

Classification = Annotated[
    DataClassification,
    typer.Option(help="Nhãn dữ liệu của video; mặc định coi là dữ liệu nhà máy."),
]
ProcessId = Annotated[str | None, typer.Option("--process-id", help="Mã công đoạn.")]


@app.command("probe", help="Thông tin video: video_id, thời lượng, fps, có audio không (ffprobe).")
def probe_cmd(
    video: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="Tệp video.")],
    process_id: ProcessId = None,
    classification: Classification = DataClassification.FACTORY_CONFIDENTIAL,
) -> None:
    from mentormind.capture.video.probe import probe_video

    try:
        asset = probe_video(video, process_id=process_id, classification=classification)
    except (ValueError, FileNotFoundError) as exc:
        typer.secho(f"Lỗi: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    typer.echo(asset.model_dump_json(indent=2))


@app.command("segment", help="Cắt đoạn + keyframe + clip, ghi data/work/video/<video_id>/segments.json.")
def segment_cmd(
    video: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="Tệp video.")],
    process_id: ProcessId = None,
    classification: Classification = DataClassification.FACTORY_CONFIDENTIAL,
    method: Annotated[
        str | None,
        typer.Option(
            help="hand_activity (nhịp tay) | scene (cảnh) | fixed_window (10 s); mặc định KNOWHOW_VIDEO_METHOD."
        ),
    ] = None,
) -> None:
    from mentormind.capture.video.pipeline import VideoCapturePipeline
    from mentormind.capture.video.segmenters import METHODS

    settings = get_settings()
    method = method or settings.video_method
    if method not in METHODS:
        typer.secho(f"Lỗi: --method phải là một trong {', '.join(METHODS)}.", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    try:
        result = VideoCapturePipeline(settings).run(
            video,
            work_dir=settings.work_dir,
            process_id=process_id,
            classification=classification,
            method=method,  # checked against METHODS above
            transcribe=False,
        )
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        typer.secho(f"Lỗi: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    lengths = [s.t_end - s.t_start for s in result.segments]
    fell_back = f" (rơi về {result.method_used})" if result.method_used != result.method else ""
    typer.echo(
        f"{result.asset.video_id} | {result.asset.duration_s:.1f}s | cách cắt {result.method}{fell_back} | "
        f"{len(result.segments)} đoạn, {min(lengths):.1f}–{max(lengths):.1f}s"
    )
    typer.echo("thời gian: " + ", ".join(f"{k} {v:.1f}s" for k, v in result.seconds.items()))


@app.command("transcribe", help="Lời nói → câu có mốc thời gian (transcript.json); --recall-audio cho video câm.")
def transcribe_cmd(
    video: Annotated[
        Path | None, typer.Argument(dir_okay=False, help="Tệp video (bỏ trống khi dùng --recall-audio).")
    ] = None,
    process_id: ProcessId = None,
    classification: Classification = DataClassification.FACTORY_CONFIDENTIAL,
    recall_audio: Annotated[
        Path | None, typer.Option("--recall-audio", dir_okay=False, help="Ghi âm video-cued recall (FR-07b).")
    ] = None,
    video_id: Annotated[str | None, typer.Option("--video-id", help="Video của bản ghi âm recall.")] = None,
    offset: Annotated[float, typer.Option(help="Giây cộng vào mốc thời gian của bản ghi âm.")] = 0.0,
) -> None:
    from mentormind.capture.video.probe import probe_video
    from mentormind.capture.video.store import write_asset
    from mentormind.capture.video.transcribe import transcribe_recall, transcribe_video
    from mentormind.core.guard import ConfidentialDataError
    from mentormind.core.providers.asr import get_asr_provider
    from mentormind.core.providers.errors import ProviderError

    settings = get_settings()
    try:
        asr = get_asr_provider(settings)
        if recall_audio is not None:
            if not video_id:
                raise ValueError("--recall-audio cần --video-id.")
            lines = transcribe_recall(
                recall_audio, video_id=video_id, offset=offset, asr=asr, work_dir=settings.work_dir,
                language=settings.asr_language,
            )  # fmt: skip
        elif video is not None:
            asset = probe_video(video, process_id=process_id, classification=classification)
            write_asset(settings.work_dir, asset)
            if not asset.has_audio:
                typer.echo(f"{asset.video_id}: video không có audio → transcript rỗng.")
                return
            lines = transcribe_video(asset, asr, work_dir=settings.work_dir, language=settings.asr_language)
        else:
            raise ValueError("Cần tệp video, hoặc --recall-audio kèm --video-id.")
    except (ValueError, FileNotFoundError, RuntimeError, ProviderError, ConfidentialDataError) as exc:
        typer.secho(f"Lỗi: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"{len(lines)} câu")
    for line in lines[:10]:
        typer.echo(f"  {line.t_start:7.1f}–{line.t_end:7.1f}s  {line.text}")


@app.command("providers", help="Liệt kê provider ASR đã đăng ký, provider đang chọn và model mặc định.")
def providers_cmd() -> None:
    from mentormind.core.providers.asr import ASR_REGISTRY
    from mentormind.core.providers.asr.catalog import default_asr_model

    settings = get_settings()
    typer.echo(f"{'':2}{'provider':<18}{'nơi chạy':<10}{'model mặc định':<16}")
    for name in ASR_REGISTRY.names():
        mark = "* " if name == settings.asr_provider else "  "
        typer.echo(f"{mark}{name:<18}{ASR_REGISTRY[name].where:<10}{default_asr_model(name) or '-':<16}")
    model = settings.asr_model or default_asr_model(settings.asr_provider) or "mặc định của máy chủ"
    provider_cls = ASR_REGISTRY.get(settings.asr_provider)
    if provider_cls is not None and provider_cls.where == "server":
        runs_on = _inference_server(settings)
    else:
        runs_on = f"{settings.asr_device}/{settings.asr_compute_type}"
    typer.echo(
        f"đang dùng: {settings.asr_provider} · model {model} · {runs_on}"
        f" · ngôn ngữ {settings.asr_language or 'tự nhận'}"
    )


def _inference_server(settings: Settings) -> str:
    """The inference server as the CLI shows it: URL without credentials, local or cloud."""
    from mentormind.core.providers.errors import ProviderConfigError
    from mentormind.core.providers.inference import INFERENCE_URL_ENV, InferenceClient

    try:
        client = InferenceClient.from_settings(settings)
    except ProviderConfigError:
        return f"máy chủ chưa cấu hình ({INFERENCE_URL_ENV} trống)"
    return f"máy chủ {client.shown_url} ({'cloud' if client.is_cloud else 'local'})"
