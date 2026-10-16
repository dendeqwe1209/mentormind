"""``knowhow vlm describe`` and ``knowhow vlm propose-reasons`` (spec 04 FR-05).

``describe`` takes the segments of spec 03 (``<video_id>`` reads
``data/work/video/<id>/segments.json``, or ``--segments FILE``) or a raw ``--video FILE`` cut by
spec 03's ``VideoCapturePipeline`` (``--method``, fixed 10 s windows by default, as ``sweep`` does). Drafts
go to the sink of ``KNOWHOW_PROFILE_SINK`` (spec 08's store when present, else
``data/work/vlm/<video_id>/profiles.json``); ``propose-reasons`` reads and updates them there and
appends one line per profile examined to ``data/work/vlm/<video_id>/reasons_audit.jsonl`` (spec 04 §5).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from mentormind.core.config import Settings, get_settings
from mentormind.core.schemas.common import DataClassification

if TYPE_CHECKING:
    from mentormind.core.providers.llm import LLMProvider
    from mentormind.core.schemas.video import Segment
    from mentormind.core.schemas.work_profile import WorkProfile

WORK = Path("data/work")


def describe_cmd(
    video_id: Annotated[str | None, typer.Argument(help="video_id đã cắt đoạn bằng spec 03 (segments.json).")] = None,
    video: Annotated[
        Path | None,
        typer.Option(exists=True, dir_okay=False, help="Video thô, cắt bằng spec 03 (--method)."),
    ] = None,
    segments: Annotated[
        Path | None, typer.Option(exists=True, dir_okay=False, help="segments.json của spec 03.")
    ] = None,
    classification: Annotated[
        DataClassification,
        typer.Option(help="Nhãn dữ liệu của --video; mặc định coi là dữ liệu nhà máy."),
    ] = DataClassification.FACTORY_CONFIDENTIAL,
    process_id: Annotated[str, typer.Option(help="Mã công đoạn.")] = "PACK01",
    fps: Annotated[
        float | None,
        typer.Option(help="fps khi đoạn chưa có motion_score (mặc định KNOWHOW_VLM_FPS)."),
    ] = None,
    window: Annotated[float, typer.Option(min=3, help="Độ dài đoạn (s) cho --video.")] = 10.0,
    method: Annotated[
        str, typer.Option(help="Cách cắt --video (spec 03): fixed_window | scene | hand_activity.")
    ] = "fixed_window",
    provider: Annotated[str | None, typer.Option(help="Ghi đè KNOWHOW_VLM_PROVIDER.")] = None,
    llm_provider: Annotated[str | None, typer.Option(help="LLM của lượt C; ghi đè KNOWHOW_LLM_PROVIDER.")] = None,
    consistency: Annotated[
        bool, typer.Option(help="Lượt B: chạy lượt A 2 lần, giữ bước có ở cả 2 (gấp đôi token).")
    ] = True,
    merge: Annotated[bool, typer.Option(help="Lượt C: LLM gộp bước trùng giữa các đoạn kề.")] = True,
) -> None:
    """Describe a video: passes A, B, C, then draft WorkProfiles."""
    from mentormind.core.guard import ConfidentialDataError, DataGuard
    from mentormind.core.providers.errors import ProviderError
    from mentormind.core.providers.llm.context import strictest
    from mentormind.core.providers.vlm import get_vlm_provider
    from mentormind.processing.vlm.passes.step_times import get_step_timer
    from mentormind.processing.vlm.pipeline import DescribePipeline
    from mentormind.processing.vlm.profiles import ProfileSinkError, get_profile_sink
    from mentormind.processing.vlm.transcript import load_transcript

    settings = get_settings()
    if provider:
        settings = settings.model_copy(update={"vlm_provider": provider})
    if llm_provider:
        settings = settings.model_copy(update={"llm_provider": llm_provider})
    try:
        sink = get_profile_sink(settings, work_dir=WORK)  # fail before any VLM call
        loaded = _segments(video_id, video, segments, classification, window, method, process_id)
        vid = loaded[0].video_id
        transcript = load_transcript(WORK, vid)  # spec 03 transcript.json; none -> no excerpts
        vlm = get_vlm_provider(settings)
        llm = _llm(settings) if merge else None
        label = strictest(s.data_classification for s in loaded)
        # Fail before any VLM token is spent when pass C could not run on this data.
        DataGuard.check(label, vlm)
        if llm is not None:
            DataGuard.check(label, llm)
        work_dir = WORK / "vlm" / vid / f"describe-{vlm.name}"
        pipeline = DescribePipeline(
            vlm,
            llm=llm,
            process_id=process_id,
            default_fps=fps or settings.vlm_fps,
            max_frames=settings.vlm_max_frames,
            consistency=consistency,
            transcript_lead_s=settings.transcript_lead_s,
            transcript_lag_s=settings.transcript_lag_s,
            step_timer=get_step_timer(settings.vlm_step_times),
            concurrency=settings.vlm_concurrency,
        )
        result = pipeline.run(loaded, work_dir, transcript)
    except ConfidentialDataError as exc:
        typer.secho(
            f"Lỗi: {exc}\nDữ liệu nhà máy chỉ chạy với provider tự host: KNOWHOW_VLM_PROVIDER="
            "local_openai và KNOWHOW_LLM_PROVIDER=local_openai (hoặc --no-merge).",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1) from exc
    except (
        ProviderError, PermissionError, ValueError, RuntimeError, FileNotFoundError,
        ProfileSinkError,
    ) as exc:  # fmt: skip
        typer.secho(f"Lỗi: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    stored = sink.save(vid, result.profiles)
    moved = sum(a.profile_id != b.profile_id for a, b in zip(result.profiles, stored, strict=True))
    kept = len(result.steps.steps)
    typer.echo(f"provider={vlm.name} model={vlm.model} | {len(loaded)} đoạn | chi tiết: {work_dir}")
    typer.echo(f"lượt A: {result.pass_a_steps} bước" + (f" → lượt B giữ {kept}" if consistency else ""))
    if result.merge is not None:
        m = result.merge
        typer.echo(
            f"lượt C ({llm.name if llm else '-'}): gộp {m.merged}, đổi tên {m.renamed}, "
            f"bỏ bước bịa {m.invented_dropped}, từ chối {m.rejected}" + (f" | {m.error}" if m.error else "")
        )
    if result.failed_segments:
        typer.secho(f"{len(result.failed_segments)} đoạn lỗi JSON: {work_dir}/failed_segments.json",
                    fg=typer.colors.YELLOW)  # fmt: skip
    if transcript:
        quoted = sum(p.evidence.transcript_excerpt is not None for p in result.profiles)
        typer.echo(f"transcript: {len(transcript)} câu → {quoted} profile có lời chuyên gia (vlm propose-reasons)")
    note = f" ({moved} đổi profile_id vì trùng profile của video khác)" if moved else ""
    typer.echo(f"{len(stored)} WorkProfile (draft) → {sink.where}{note}")


def propose_reasons_cmd(
    video_id: Annotated[str, typer.Argument(help="video_id đã chạy describe.")],
    llm_provider: Annotated[str | None, typer.Option(help="Ghi đè KNOWHOW_LLM_PROVIDER.")] = None,
) -> None:
    """Fill reasons from the expert's own words (transcript) into the video's profiles."""
    from mentormind.core.guard import ConfidentialDataError
    from mentormind.core.providers.errors import ProviderError
    from mentormind.processing.vlm.passes.reasons import examined, propose_reasons, reasons_audit_path
    from mentormind.processing.vlm.profiles import (
        FileProfileSink,
        ProfileSinkError,
        get_profile_sink,
    )

    settings = get_settings()
    if llm_provider:
        settings = settings.model_copy(update={"llm_provider": llm_provider})
    try:
        sink = get_profile_sink(settings, work_dir=WORK)
        profiles = sink.load(video_id)
    except ProfileSinkError as exc:
        typer.secho(f"Lỗi: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    if not profiles:
        typer.secho(
            f"Lỗi: {sink.where} chưa có profile nào của {video_id}; chạy `knowhow vlm describe` trước.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)
    candidates = len([p for p in profiles if examined(p)])
    if candidates == 0:
        typer.echo(
            f"{len(profiles)} profile, không bản nháp nào có transcript_excerpt mà chưa có lý do (cần transcript "
            "của spec 03; bước đã duyệt/từ chối/đang duyệt không bị xét lại) → không có gì để làm."
        )
        return
    audit = reasons_audit_path(WORK, video_id)
    current = {p.profile_id: p for p in profiles}
    changed: list[WorkProfile] = []

    def save(profile: WorkProfile) -> None:
        # Each accepted profile is stored before its audit line (spec 04 §5): a run stopped half-way
        # keeps what it found. The store gets only that profile (re-saving untouched ones would count
        # as id clashes); the file is the whole video.
        current[profile.profile_id] = profile
        sink.save(video_id, list(current.values()) if isinstance(sink, FileProfileSink) else [profile])
        changed.append(profile)

    try:
        propose_reasons(profiles, _llm(settings), audit=audit, save=save)
    except (ConfidentialDataError, ProviderError, ProfileSinkError) as exc:
        typer.secho(f"Lỗi: {exc} (đã lưu {len(changed)} lý do trước lỗi)", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"{candidates} profile có transcript → điền lý do cho {len(changed)} (in_review) → {sink.where}")
    typer.echo(f"tự kiểm từng quyết định: {audit}")


def _llm(settings: Settings) -> LLMProvider:
    from mentormind.core.providers.llm import get_llm_provider

    return get_llm_provider(settings)


def _segments(
    video_id: str | None,
    video: Path | None,
    segments: Path | None,
    classification: DataClassification,
    window: float,
    method: str = "fixed_window",
    process_id: str | None = None,
) -> list[Segment]:
    from mentormind.capture.video import VideoCapturePipeline
    from mentormind.capture.video.segmenters import METHODS
    from mentormind.capture.video.store import read_segments, segments_path

    if [video_id, video, segments].count(None) != 2:
        raise ValueError("Chọn đúng một nguồn: <video_id>, --video hoặc --segments.")
    if video is not None:
        if method not in METHODS:
            raise ValueError(f"--method phải là một trong {', '.join(METHODS)}.")
        capture = VideoCapturePipeline(get_settings(), window_s=window)
        return capture.run(
            video,
            work_dir=WORK,
            process_id=process_id,
            classification=classification,
            method=method,  # checked against METHODS above
            transcribe=False,
        ).segments
    return read_segments(segments or segments_path(WORK, str(video_id)))
