"""``knowhow vlm sweep``: pass A at several fps, scored against a hand-labelled truth (§6)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from mentormind.core.config import get_settings
from mentormind.core.schemas.common import DataClassification


def sweep_cmd(
    video: Annotated[Path, typer.Option(exists=True, dir_okay=False, help="Video cần mô tả.")],
    truth: Annotated[Path, typer.Option(exists=True, dir_okay=False, help="Bước gán tay (spec 04 §6).")],
    fps: Annotated[str, typer.Option(help="Các fps cần quét, phân tách bằng dấu phẩy.")] = "1,2,4,8",
    out: Annotated[Path, typer.Option(help="File CSV kết quả.")] = Path("data/work/sweep.csv"),
    provider: Annotated[str | None, typer.Option(help="Ghi đè KNOWHOW_VLM_PROVIDER cho lần chạy này.")] = None,
    segments: Annotated[
        Path | None,
        typer.Option(exists=True, dir_okay=False, help="segments.json của spec 03 (nếu đã có)."),
    ] = None,
    window: Annotated[float, typer.Option(min=3, help="Độ dài đoạn (s) khi chưa có segments.json.")] = 10.0,
    classification: Annotated[
        DataClassification,
        typer.Option(help="Nhãn dữ liệu của video; mặc định coi là dữ liệu nhà máy."),
    ] = DataClassification.FACTORY_CONFIDENTIAL,
    process_id: Annotated[str, typer.Option(help="Mã công đoạn.")] = "PACK01",
) -> None:
    """Run pass A at several fps on one video and score it against the truth."""
    import json

    from mentormind.capture.video import VideoCapturePipeline, video_id_for
    from mentormind.capture.video.segmenters import FixedWindowSegmenter
    from mentormind.core.providers.errors import ProviderError
    from mentormind.core.providers.vlm import get_vlm_provider
    from mentormind.core.schemas.video import Segment
    from mentormind.processing.vlm.passes.step_times import get_step_timer
    from mentormind.processing.vlm.sweep import load_truth, markdown_table, run_sweep, write_csv

    settings = get_settings()
    if provider:
        settings = settings.model_copy(update={"vlm_provider": provider})
    fps_values = [float(v) for v in fps.split(",") if v.strip()]
    try:
        vlm = get_vlm_provider(settings)
        video_id = video_id_for(video)
        # One folder per step-times mode: a sweep per KNOWHOW_VLM_STEP_TIMES value keeps its own details.
        work_dir = Path("data/work/vlm") / video_id / f"sweep-{vlm.name}-{settings.vlm_step_times}"
        if segments is not None:
            loaded = [Segment.model_validate(s) for s in json.loads(segments.read_text())]
        else:
            # Spec 03's fixed windows; no motion pass: the sweep forces its own fps on every segment.
            capture = VideoCapturePipeline(settings, build=lambda _: FixedWindowSegmenter(window, motion=False))
            loaded = capture.run(
                video,
                work_dir=settings.work_dir,
                process_id=process_id,
                classification=classification,
                method="fixed_window",
                transcribe=False,
                video_id=video_id,
            ).segments
        rows = run_sweep(
            loaded,
            load_truth(truth),
            fps_values,
            vlm,
            process_id=process_id,
            work_dir=work_dir,
            max_frames=settings.vlm_max_frames,
            step_timer=get_step_timer(settings.vlm_step_times),
        )
    except (ProviderError, PermissionError, ValueError, RuntimeError) as exc:
        typer.secho(f"Lỗi: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    write_csv(rows, out)
    table = markdown_table(rows)
    out.with_suffix(".md").write_text(table + "\n", encoding="utf-8")
    typer.echo(
        f"provider={vlm.name} model={vlm.model} step_times={settings.vlm_step_times} | {len(loaded)} đoạn"
        f" | chi tiết: {work_dir}"
    )
    typer.echo(table)
    typer.echo(f"CSV: {out}")
