"""spec 03 FR-07/07b/08 — sentences from word timestamps, recall audio, alignment (AC-05..AC-08, AC-10)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mentormind.capture.video import align_transcript, store
from mentormind.capture.video.transcribe import sentences, transcribe_recall, transcribe_video
from mentormind.core.providers.asr import ASRResult, ASRSegment, ASRWord
from mentormind.core.providers.asr.backends.fake import FakeASR
from mentormind.core.schemas.common import DataClassification
from mentormind.core.schemas.video import Segment, TranscriptSegment, VideoAsset

CONFIDENTIAL = DataClassification.FACTORY_CONFIDENTIAL


def words(*items: tuple[str, float, float]) -> tuple[ASRWord, ...]:
    return tuple(ASRWord(text=text, t_start=start, t_end=end) for text, start, end in items)


SPEECH = ASRSegment(
    text="Đặt cốc nghiêng. Rồi ấn nhẹ nắp xuống",
    t_start=1.0,
    t_end=9.0,
    words=words(
        (" Đặt", 1.0, 1.3), (" cốc", 1.3, 1.6), (" nghiêng.", 1.6, 2.1),  # sentence mark
        (" Rồi", 2.4, 2.6), (" ấn", 2.6, 2.8), (" nhẹ", 2.8, 3.0),
        (" nắp", 4.2, 4.5), (" xuống", 4.5, 9.0),  # 1.2 s pause before "nắp"
    ),
)  # fmt: skip


def asset(tmp_path: Path, *, has_audio: bool, label: DataClassification = CONFIDENTIAL) -> VideoAsset:
    video = tmp_path / "in.mp4"
    video.write_bytes(b"video")
    return VideoAsset(
        video_id="VID-0123456789ab", path=str(video), duration_s=30, fps=25, has_audio=has_audio,
        process_id="PACK01", data_classification=label,
    )  # fmt: skip


def fake_extract(video: Path, wav: Path) -> None:
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"RIFF....WAVE")


def test_ac_10_sentences_end_at_a_mark_or_a_pause() -> None:
    result = ASRResult(segments=(SPEECH,), language="vi", duration_s=30, latency_s=1, provider="fake", model="m")
    assert sentences(result) == [
        (1.0, 2.1, "Đặt cốc nghiêng."),
        (2.4, 3.0, "Rồi ấn nhẹ"),
        (4.2, 9.0, "nắp xuống"),
    ]
    no_words = ASRResult(
        segments=(ASRSegment(text=" Xong. ", t_start=0, t_end=1),), language="vi", duration_s=1, latency_s=0,
        provider="fake", model="m",
    )  # fmt: skip
    assert sentences(no_words) == [(0, 1, "Xong.")]


def test_ac_05_a_video_without_audio_gives_no_transcript(tmp_path: Path) -> None:
    asr = FakeASR([SPEECH])
    assert transcribe_video(asset(tmp_path, has_audio=False), asr, work_dir=tmp_path, extract=fake_extract) == []
    assert asr.calls == [] and not store.transcript_path(tmp_path, "VID-0123456789ab").exists()


def test_ac_07_every_line_carries_the_videos_label(tmp_path: Path) -> None:
    lines = transcribe_video(
        asset(tmp_path, has_audio=True), FakeASR([SPEECH]), work_dir=tmp_path, extract=fake_extract
    )
    assert [line.text for line in lines] == ["Đặt cốc nghiêng.", "Rồi ấn nhẹ", "nắp xuống"]
    assert {(line.data_classification, line.source, line.video_id) for line in lines} == {
        (CONFIDENTIAL, "inline", "VID-0123456789ab")
    }
    assert store.read_transcript(tmp_path, "VID-0123456789ab") == lines
    assert not (store.video_dir(tmp_path, "VID-0123456789ab") / "audio.wav").exists()  # the WAV is removed


def test_ac_08_recall_audio_is_shifted_by_the_offset_and_appended(tmp_path: Path) -> None:
    video = asset(tmp_path, has_audio=False)
    store.write_asset(tmp_path, video)
    recording = tmp_path / "recall.m4a"
    recording.write_bytes(b"audio")
    lines = transcribe_recall(recording, video_id=video.video_id, offset=12.5, asr=FakeASR([SPEECH]), work_dir=tmp_path)
    assert [line.t_start for line in lines] == [13.5, 14.9, 16.7]
    assert {(line.source, line.data_classification) for line in lines} == {("cued_recall", CONFIDENTIAL)}
    again = transcribe_video(  # a later inline pass keeps the recalled lines
        video.model_copy(update={"has_audio": True}), FakeASR([]), work_dir=tmp_path, extract=fake_extract
    )
    assert again == [] and store.read_transcript(tmp_path, video.video_id) == lines


def test_ac_08_an_unknown_video_id_is_an_error_and_nothing_is_written(tmp_path: Path) -> None:
    recording = tmp_path / "recall.m4a"
    recording.write_bytes(b"audio")
    asr = FakeASR([SPEECH])
    with pytest.raises(FileNotFoundError, match="VID-ffffffffffff"):
        transcribe_recall(recording, video_id="VID-ffffffffffff", offset=0, asr=asr, work_dir=tmp_path)
    assert asr.calls == [] and not (tmp_path / "video").exists()


def seg(index: int, start: float, end: float) -> Segment:
    return Segment(
        segment_id=f"VID-T-S{index:03d}", video_id="VID-T", index=index, t_start=start, t_end=end,
        method="fixed_window", motion_score=None, keyframes=[], clip_path="c.mp4",
        data_classification=DataClassification.SYNTHETIC,
    )  # fmt: skip


def said(start: float, end: float, text: str = "x") -> TranscriptSegment:
    return TranscriptSegment(
        video_id="VID-T", t_start=start, t_end=end, text=text, language="vi",
        data_classification=DataClassification.SYNTHETIC,
    )  # fmt: skip


def test_ac_06_a_line_across_a_boundary_goes_where_most_of_it_is() -> None:
    segments = [seg(1, 0, 10), seg(2, 10, 20), seg(3, 20, 30)]
    lines = [said(8, 13, "most in S002"), said(9, 11, "half each: earlier"), said(35, 36, "after the video")]
    aligned = align_transcript(segments, lines)
    assert [t.text for t in aligned["VID-T-S001"]] == ["half each: earlier"]
    assert [t.text for t in aligned["VID-T-S002"]] == ["most in S002"]
    assert [t.text for t in aligned["VID-T-S003"]] == ["after the video"]  # nearest segment
    assert align_transcript([], lines) == {}


def test_ac_10_languages_without_spaces_are_not_split_into_syllables() -> None:
    thai = ASRSegment(
        text="เราต้องการเพิ่มกำลังการผลิต",
        t_start=30.2,
        t_end=34.5,
        words=words(("เรา", 30.2, 30.5), ("ต้องการ", 30.5, 31.0), ("เพิ่ม", 31.0, 31.4), ("กำลังการผลิต", 31.4, 34.5)),
    )
    result = ASRResult(segments=(thai,), language="th", duration_s=40, latency_s=1, provider="fake", model="m")
    assert sentences(result) == [(30.2, 34.5, "เราต้องการเพิ่มกำลังการผลิต")]


def test_ac_10_a_long_sentence_is_never_cut_inside_a_word() -> None:
    syllables = tuple(ASRWord(text=t, t_start=i * 2.0, t_end=i * 2.0 + 2.0) for i, t in enumerate("กขคงจฉชซญดตถ"))
    thai = ASRSegment(text="".join("กขคงจฉชซญดตถ"), t_start=0, t_end=24, words=syllables)  # 24 s, no space
    spoken = ASRSegment(text="Đặt cốc", t_start=30, t_end=31, words=words((" Đặt", 30, 30.5), (" cốc", 30.5, 31)))
    result = ASRResult(segments=(thai, spoken), language="th", duration_s=40, latency_s=1, provider="fake", model="m")
    assert sentences(result) == [(0.0, 24.0, "กขคงจฉชซญดตถ"), (30, 31, "Đặt cốc")]


def test_ac_14_a_recording_replaces_its_own_stretch_and_keeps_the_rest(tmp_path: Path) -> None:
    video = asset(tmp_path, has_audio=True)
    store.write_asset(tmp_path, video)
    inline = transcribe_video(video, FakeASR([SPEECH]), work_dir=tmp_path, extract=fake_extract)  # 1–9 s
    recording = tmp_path / "recall.m4a"
    recording.write_bytes(b"audio")

    def recall(offset: float) -> None:
        transcribe_recall(recording, video_id=video.video_id, offset=offset, asr=FakeASR([SPEECH]), work_dir=tmp_path)

    def recalled() -> list[float]:
        lines = store.read_transcript(tmp_path, video.video_id)
        return sorted(line.t_start for line in lines if line.source == "cued_recall")

    recall(0.0)  # covers 0–9 s, the same stretch as the inline speech
    recall(0.0)  # the same recording again: no duplicates
    assert recalled() == [1.0, 2.4, 4.2]
    recall(12.5)  # another stretch (12.5–21.5 s): the earlier lines stay
    assert recalled() == [1.0, 2.4, 4.2, 13.5, 14.9, 16.7]
    kept = [line for line in store.read_transcript(tmp_path, video.video_id) if line.source == "inline"]
    assert kept == inline  # inline speech is never replaced by a recording
