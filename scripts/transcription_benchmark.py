#!/usr/bin/env python3
"""
Benchmark: Local Whisper (VomoMLX) vs AssemblyAI Universal-2

Compara transcricao e diarizacao entre os dois sistemas usando metricas
de concordancia (sem ground truth).

Uso:
    python scripts/transcription_benchmark.py ./audios_teste/ --mode AUDIENCIA
    python scripts/transcription_benchmark.py ./audios_teste/ --use-cache --skip-local
"""

import argparse
import csv
import difflib
import json
import os
import re
import sys
import time
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import numpy as np
from scipy.optimize import linear_sum_assignment

try:
    from tabulate import tabulate
except ImportError:
    tabulate = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm"}
ASSEMBLYAI_RATE_PER_HOUR_USD = 0.90
SLOT_DURATION = 0.5  # seconds for diarization discretization


# ============================================================
# Data structures
# ============================================================

@dataclass
class Segment:
    start: float
    end: float
    text: str
    speaker_label: str = ""


@dataclass
class TranscriptionResult:
    backend: str
    text: str
    segments: list[Segment]
    elapsed_seconds: float
    audio_duration: float = 0.0
    num_speakers: int = 0
    error: Optional[str] = None


@dataclass
class TextMetrics:
    global_similarity: float = 0.0
    bigram_overlap: float = 0.0
    trigram_overlap: float = 0.0
    window_mean: float = 0.0
    window_min: float = 0.0
    window_max: float = 0.0
    per_window: list = field(default_factory=list)


@dataclass
class DiarizationMetrics:
    speakers_local: int = 0
    speakers_aai: int = 0
    agreement_ratio: float = 0.0
    speaker_mapping: dict = field(default_factory=dict)
    turn_precision: float = 0.0  # % de trocas locais que AAI tambem detecta
    turn_recall: float = 0.0  # % de trocas AAI que local tambem detecta
    turn_timing_mean_diff: float = 0.0  # media de diferenca em segundos nas trocas
    turn_timing_median_diff: float = 0.0
    speech_coverage_local: float = 0.0  # % do tempo com fala detectada
    speech_coverage_aai: float = 0.0


@dataclass
class BenchmarkResult:
    filename: str
    audio_duration: float
    text_metrics: TextMetrics
    diarization_metrics: DiarizationMetrics
    rtf_local: float = 0.0
    rtf_aai: float = 0.0
    latency_local: float = 0.0
    latency_aai: float = 0.0
    cost_aai: float = 0.0
    cost_local: float = 0.0


# ============================================================
# Text normalization
# ============================================================

def normalize_text(text: str) -> str:
    """Lowercase, remove acentos, pontuacao, colapsa espacos."""
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def get_ngrams(text: str, n: int) -> set:
    words = text.split()
    if len(words) < n:
        return set()
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)}


def jaccard(set_a: set, set_b: set) -> float:
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    if not union:
        return 1.0
    return len(set_a & set_b) / len(union)


# ============================================================
# Text concordance metrics
# ============================================================

def text_concordance(text_a: str, text_b: str) -> dict:
    na = normalize_text(text_a)
    nb = normalize_text(text_b)
    return {
        "global_similarity": difflib.SequenceMatcher(None, na, nb).ratio(),
        "bigram_overlap": jaccard(get_ngrams(na, 2), get_ngrams(nb, 2)),
        "trigram_overlap": jaccard(get_ngrams(na, 3), get_ngrams(nb, 3)),
    }


def align_segments_by_time(
    segs_a: list[Segment], segs_b: list[Segment], window_sec: float = 30.0
) -> list[tuple[float, str, str]]:
    """Agrupa texto de ambos os sistemas em janelas temporais."""
    max_end = max(
        max((s.end for s in segs_a), default=0),
        max((s.end for s in segs_b), default=0),
    )
    windows = []
    t = 0.0
    while t < max_end:
        t_end = t + window_sec
        text_a = " ".join(
            s.text for s in segs_a if s.start < t_end and s.end > t
        )
        text_b = " ".join(
            s.text for s in segs_b if s.start < t_end and s.end > t
        )
        windows.append((t, normalize_text(text_a), normalize_text(text_b)))
        t = t_end
    return windows


def windowed_concordance(windows: list[tuple[float, str, str]]) -> dict:
    sims = []
    for _, ta, tb in windows:
        if not ta and not tb:
            sims.append(1.0)
        elif not ta or not tb:
            sims.append(0.0)
        else:
            sims.append(difflib.SequenceMatcher(None, ta, tb).ratio())
    return {
        "mean": float(np.mean(sims)) if sims else 0.0,
        "min": float(np.min(sims)) if sims else 0.0,
        "max": float(np.max(sims)) if sims else 0.0,
        "per_window": [
            {"start": w[0], "similarity": s} for w, s in zip(windows, sims)
        ],
    }


def compute_text_metrics(
    result_a: TranscriptionResult,
    result_b: TranscriptionResult,
    window_sec: float,
) -> TextMetrics:
    tc = text_concordance(result_a.text, result_b.text)
    windows = align_segments_by_time(result_a.segments, result_b.segments, window_sec)
    wc = windowed_concordance(windows)
    return TextMetrics(
        global_similarity=tc["global_similarity"],
        bigram_overlap=tc["bigram_overlap"],
        trigram_overlap=tc["trigram_overlap"],
        window_mean=wc["mean"],
        window_min=wc["min"],
        window_max=wc["max"],
        per_window=wc["per_window"],
    )


# ============================================================
# Diarization metrics
# ============================================================

def _get_speakers(segments: list[Segment]) -> list[str]:
    return sorted(set(s.speaker_label for s in segments if s.speaker_label))


def _discretize_speakers(
    segments: list[Segment], max_time: float, slot_dur: float
) -> list[Optional[str]]:
    """Assign a speaker to each time slot."""
    n_slots = int(max_time / slot_dur) + 1
    slots = [None] * n_slots
    for s in segments:
        i_start = int(s.start / slot_dur)
        i_end = min(int(s.end / slot_dur) + 1, n_slots)
        for i in range(i_start, i_end):
            slots[i] = s.speaker_label
    return slots


def build_speaker_overlap_matrix(
    segs_a: list[Segment], segs_b: list[Segment], slot_dur: float = SLOT_DURATION
) -> tuple[np.ndarray, list[str], list[str]]:
    speakers_a = _get_speakers(segs_a)
    speakers_b = _get_speakers(segs_b)
    if not speakers_a or not speakers_b:
        return np.zeros((0, 0)), speakers_a, speakers_b

    max_t = max(
        max((s.end for s in segs_a), default=0),
        max((s.end for s in segs_b), default=0),
    )
    slots_a = _discretize_speakers(segs_a, max_t, slot_dur)
    slots_b = _discretize_speakers(segs_b, max_t, slot_dur)

    matrix = np.zeros((len(speakers_a), len(speakers_b)))
    for i, sa in enumerate(speakers_a):
        for j, sb in enumerate(speakers_b):
            matrix[i][j] = sum(
                1
                for k in range(len(slots_a))
                if k < len(slots_b) and slots_a[k] == sa and slots_b[k] == sb
            )
    return matrix, speakers_a, speakers_b


def optimal_speaker_mapping(
    matrix: np.ndarray, labels_a: list[str], labels_b: list[str]
) -> dict[str, str]:
    if matrix.size == 0:
        return {}
    cost = -matrix  # maximize overlap = minimize negative
    row_ind, col_ind = linear_sum_assignment(cost)
    mapping = {}
    for r, c in zip(row_ind, col_ind):
        if r < len(labels_a) and c < len(labels_b):
            mapping[labels_a[r]] = labels_b[c]
    return mapping


def diarization_agreement(
    segs_a: list[Segment],
    segs_b: list[Segment],
    mapping: dict[str, str],
    slot_dur: float = SLOT_DURATION,
) -> float:
    """% of time slots where both systems agree on speaker (after mapping)."""
    max_t = max(
        max((s.end for s in segs_a), default=0),
        max((s.end for s in segs_b), default=0),
    )
    slots_a = _discretize_speakers(segs_a, max_t, slot_dur)
    slots_b = _discretize_speakers(segs_b, max_t, slot_dur)
    n = min(len(slots_a), len(slots_b))
    if n == 0:
        return 0.0

    agree = 0
    total = 0
    for k in range(n):
        sa = slots_a[k]
        sb = slots_b[k]
        if sa is None and sb is None:
            continue
        total += 1
        mapped = mapping.get(sa)
        if mapped == sb:
            agree += 1
    return agree / total if total > 0 else 0.0


def _detect_speaker_turns(segments: list[Segment], tolerance: float = 1.0) -> list[tuple[float, str]]:
    """Detect moments where speaker changes. Returns [(time, new_speaker), ...]."""
    turns = []
    prev_speaker = None
    for s in sorted(segments, key=lambda x: x.start):
        if s.speaker_label and s.speaker_label != prev_speaker:
            turns.append((s.start, s.speaker_label))
            prev_speaker = s.speaker_label
    return turns


def _match_turns(
    turns_a: list[tuple[float, str]],
    turns_b: list[tuple[float, str]],
    tolerance: float = 2.0,
) -> tuple[int, int, list[float]]:
    """
    Match speaker turns between two systems within tolerance window.
    Returns: (matched_count, total_a_turns, timing_diffs)
    """
    used_b = set()
    matched = 0
    timing_diffs = []

    for t_a, _ in turns_a:
        best_diff = None
        best_idx = None
        for idx, (t_b, _) in enumerate(turns_b):
            if idx in used_b:
                continue
            diff = abs(t_a - t_b)
            if diff <= tolerance and (best_diff is None or diff < best_diff):
                best_diff = diff
                best_idx = idx
        if best_idx is not None:
            matched += 1
            used_b.add(best_idx)
            timing_diffs.append(best_diff)

    return matched, len(turns_a), timing_diffs


def speech_coverage(segments: list[Segment], total_duration: float) -> float:
    """% of total duration covered by speech segments."""
    if total_duration <= 0:
        return 0.0
    covered = sum(s.end - s.start for s in segments)
    return min(covered / total_duration, 1.0)


def compute_diarization_metrics(
    result_local: TranscriptionResult,
    result_aai: TranscriptionResult,
) -> DiarizationMetrics:
    segs_l = result_local.segments
    segs_a = result_aai.segments
    speakers_l = _get_speakers(segs_l)
    speakers_a = _get_speakers(segs_a)

    matrix, labels_l, labels_a = build_speaker_overlap_matrix(segs_l, segs_a)
    mapping = optimal_speaker_mapping(matrix, labels_l, labels_a)
    agreement = diarization_agreement(segs_l, segs_a, mapping)

    # Speaker turn analysis
    turns_l = _detect_speaker_turns(segs_l)
    turns_a = _detect_speaker_turns(segs_a)

    matched_la, total_l, diffs_la = _match_turns(turns_l, turns_a, tolerance=2.0)
    matched_al, total_a, diffs_al = _match_turns(turns_a, turns_l, tolerance=2.0)

    all_diffs = diffs_la + diffs_al
    duration = max(
        max((s.end for s in segs_l), default=0),
        max((s.end for s in segs_a), default=0),
    )

    return DiarizationMetrics(
        speakers_local=len(speakers_l),
        speakers_aai=len(speakers_a),
        agreement_ratio=agreement,
        speaker_mapping=mapping,
        turn_precision=matched_la / total_l if total_l > 0 else 0.0,
        turn_recall=matched_al / total_a if total_a > 0 else 0.0,
        turn_timing_mean_diff=float(np.mean(all_diffs)) if all_diffs else 0.0,
        turn_timing_median_diff=float(np.median(all_diffs)) if all_diffs else 0.0,
        speech_coverage_local=speech_coverage(segs_l, duration),
        speech_coverage_aai=speech_coverage(segs_a, duration),
    )


# ============================================================
# Backends
# ============================================================

def run_local_whisper(audio_path: str, mode: str) -> TranscriptionResult:
    """Run transcription via VomoMLX (local Whisper + Pyannote)."""
    sys.path.insert(0, str(PROJECT_ROOT))
    from mlx_vomo import VomoMLX

    vomo = VomoMLX(model_size="large-v3-turbo", provider="gemini")
    vomo._diarization_enabled = True
    vomo._diarization_required = True

    start = time.time()
    try:
        raw = vomo.transcribe_with_segments(audio_path)
    except Exception as e:
        return TranscriptionResult(
            backend="local_whisper",
            text="",
            segments=[],
            elapsed_seconds=time.time() - start,
            error=str(e),
        )
    elapsed = time.time() - start

    segments = []
    for s in raw.get("segments", []):
        segments.append(
            Segment(
                start=s.get("start", 0),
                end=s.get("end", 0),
                text=s.get("text", ""),
                speaker_label=s.get("speaker_label", ""),
            )
        )

    speakers = set(s.speaker_label for s in segments if s.speaker_label)
    duration = max((s.end for s in segments), default=0)

    return TranscriptionResult(
        backend="local_whisper",
        text=raw.get("text", ""),
        segments=segments,
        elapsed_seconds=elapsed,
        audio_duration=duration,
        num_speakers=len(speakers),
    )


def run_assemblyai(audio_path: str) -> TranscriptionResult:
    """Run transcription via AssemblyAI Universal-2."""
    try:
        import assemblyai as aai
    except ImportError:
        return TranscriptionResult(
            backend="assemblyai",
            text="",
            segments=[],
            elapsed_seconds=0,
            error="assemblyai not installed. Run: pip install assemblyai",
        )

    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        return TranscriptionResult(
            backend="assemblyai",
            text="",
            segments=[],
            elapsed_seconds=0,
            error="ASSEMBLYAI_API_KEY not set",
        )

    aai.settings.api_key = api_key

    config = aai.TranscriptionConfig(
        speaker_labels=True,
        language_code="pt",
    )

    start = time.time()
    try:
        transcriber = aai.Transcriber()
        transcript = transcriber.transcribe(audio_path, config=config)

        if transcript.status == aai.TranscriptStatus.error:
            return TranscriptionResult(
                backend="assemblyai",
                text="",
                segments=[],
                elapsed_seconds=time.time() - start,
                error=transcript.error,
            )
    except Exception as e:
        return TranscriptionResult(
            backend="assemblyai",
            text="",
            segments=[],
            elapsed_seconds=time.time() - start,
            error=str(e),
        )

    elapsed = time.time() - start

    segments = []
    if transcript.utterances:
        for utt in transcript.utterances:
            segments.append(
                Segment(
                    start=utt.start / 1000.0,
                    end=utt.end / 1000.0,
                    text=utt.text,
                    speaker_label=f"SPEAKER_{utt.speaker}",
                )
            )

    speakers = set(s.speaker_label for s in segments if s.speaker_label)
    duration = transcript.audio_duration or max((s.end for s in segments), default=0)

    return TranscriptionResult(
        backend="assemblyai",
        text=transcript.text or "",
        segments=segments,
        elapsed_seconds=elapsed,
        audio_duration=duration,
        num_speakers=len(speakers),
    )


# ============================================================
# Cache
# ============================================================

def _cache_path(output_dir: Path, filename: str, backend: str) -> Path:
    return output_dir / "raw" / f"{filename}.{backend}.json"


def _save_cache(path: Path, result: TranscriptionResult):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "backend": result.backend,
        "text": result.text,
        "segments": [
            {
                "start": s.start,
                "end": s.end,
                "text": s.text,
                "speaker_label": s.speaker_label,
            }
            for s in result.segments
        ],
        "elapsed_seconds": result.elapsed_seconds,
        "audio_duration": result.audio_duration,
        "num_speakers": result.num_speakers,
        "error": result.error,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def _load_cache(path: Path) -> Optional[TranscriptionResult]:
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    segments = [
        Segment(
            start=s["start"],
            end=s["end"],
            text=s["text"],
            speaker_label=s.get("speaker_label", ""),
        )
        for s in data.get("segments", [])
    ]
    return TranscriptionResult(
        backend=data["backend"],
        text=data["text"],
        segments=segments,
        elapsed_seconds=data["elapsed_seconds"],
        audio_duration=data.get("audio_duration", 0),
        num_speakers=data.get("num_speakers", 0),
        error=data.get("error"),
    )


# ============================================================
# Report generation
# ============================================================

def _fmt_time(seconds: float) -> str:
    if seconds >= 3600:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h}h{m:02d}m"
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}m{s:02d}s"


def _fmt_pct(val: float) -> str:
    return f"{val * 100:.1f}%"


def print_report(results: list[BenchmarkResult]):
    if not results:
        print("Nenhum resultado para reportar.")
        return

    if tabulate:
        _print_report_tabulate(results)
    else:
        _print_report_plain(results)


def _print_report_tabulate(results: list[BenchmarkResult]):
    print("\n" + "=" * 70)
    print("  BENCHMARK: Local Whisper vs AssemblyAI Universal-2")
    print("=" * 70)

    headers = ["Metrica"] + [r.filename for r in results]

    rows = [
        ["Duracao"] + [_fmt_time(r.audio_duration) for r in results],
        ["", ""],
        ["--- TEXTO ---"] + ["" for _ in results],
        ["Similaridade global"]
        + [_fmt_pct(r.text_metrics.global_similarity) for r in results],
        ["Bigram overlap"]
        + [_fmt_pct(r.text_metrics.bigram_overlap) for r in results],
        ["Trigram overlap"]
        + [_fmt_pct(r.text_metrics.trigram_overlap) for r in results],
        ["Janela (media)"]
        + [_fmt_pct(r.text_metrics.window_mean) for r in results],
        ["Janela (min)"]
        + [_fmt_pct(r.text_metrics.window_min) for r in results],
        ["", ""],
        ["--- DIARIZACAO ---"] + ["" for _ in results],
        ["Speakers (local)"]
        + [str(r.diarization_metrics.speakers_local) for r in results],
        ["Speakers (AAI)"]
        + [str(r.diarization_metrics.speakers_aai) for r in results],
        ["Agreement"]
        + [_fmt_pct(r.diarization_metrics.agreement_ratio) for r in results],
        ["Turn precision"]
        + [_fmt_pct(r.diarization_metrics.turn_precision) for r in results],
        ["Turn recall"]
        + [_fmt_pct(r.diarization_metrics.turn_recall) for r in results],
        ["Turn timing (media)"]
        + [f"{r.diarization_metrics.turn_timing_mean_diff:.2f}s" for r in results],
        ["Turn timing (mediana)"]
        + [f"{r.diarization_metrics.turn_timing_median_diff:.2f}s" for r in results],
        ["Cobertura fala (local)"]
        + [_fmt_pct(r.diarization_metrics.speech_coverage_local) for r in results],
        ["Cobertura fala (AAI)"]
        + [_fmt_pct(r.diarization_metrics.speech_coverage_aai) for r in results],
        ["", ""],
        ["--- PERFORMANCE ---"] + ["" for _ in results],
        ["RTF local"] + [f"{r.rtf_local:.3f}x" for r in results],
        ["RTF AssemblyAI"] + [f"{r.rtf_aai:.3f}x" for r in results],
        ["Latencia local"] + [_fmt_time(r.latency_local) for r in results],
        ["Latencia AAI"] + [_fmt_time(r.latency_aai) for r in results],
        ["", ""],
        ["--- CUSTO ---"] + ["" for _ in results],
        ["AssemblyAI"] + [f"${r.cost_aai:.2f}" for r in results],
        ["Local"] + [f"${r.cost_local:.2f}" for r in results],
    ]

    # Pad rows to match headers length
    for row in rows:
        while len(row) < len(headers):
            row.append("")

    print(tabulate(rows, headers=headers, tablefmt="simple"))
    print("=" * 70 + "\n")


def _print_report_plain(results: list[BenchmarkResult]):
    print("\n" + "=" * 60)
    print("  BENCHMARK: Local Whisper vs AssemblyAI Universal-2")
    print("=" * 60)
    for r in results:
        print(f"\n--- {r.filename} ({_fmt_time(r.audio_duration)}) ---")
        print(f"  Texto:")
        print(f"    Similaridade:    {_fmt_pct(r.text_metrics.global_similarity)}")
        print(f"    Bigram overlap:  {_fmt_pct(r.text_metrics.bigram_overlap)}")
        print(f"    Trigram overlap: {_fmt_pct(r.text_metrics.trigram_overlap)}")
        print(f"    Janela (media):  {_fmt_pct(r.text_metrics.window_mean)}")
        print(f"    Janela (min):    {_fmt_pct(r.text_metrics.window_min)}")
        print(f"  Diarizacao:")
        print(f"    Speakers:        local={r.diarization_metrics.speakers_local} AAI={r.diarization_metrics.speakers_aai}")
        print(f"    Agreement:       {_fmt_pct(r.diarization_metrics.agreement_ratio)}")
        print(f"    Turn precision:  {_fmt_pct(r.diarization_metrics.turn_precision)}")
        print(f"    Turn recall:     {_fmt_pct(r.diarization_metrics.turn_recall)}")
        print(f"    Turn timing:     media={r.diarization_metrics.turn_timing_mean_diff:.2f}s mediana={r.diarization_metrics.turn_timing_median_diff:.2f}s")
        print(f"    Cobertura fala:  local={_fmt_pct(r.diarization_metrics.speech_coverage_local)} AAI={_fmt_pct(r.diarization_metrics.speech_coverage_aai)}")
        print(f"  Performance:")
        print(f"    RTF:             local={r.rtf_local:.3f}x AAI={r.rtf_aai:.3f}x")
        print(f"    Latencia:        local={_fmt_time(r.latency_local)} AAI={_fmt_time(r.latency_aai)}")
        print(f"  Custo:")
        print(f"    AssemblyAI:      ${r.cost_aai:.2f}")
        print(f"    Local:           ${r.cost_local:.2f}")
    print("=" * 60 + "\n")


def save_json_report(results: list[BenchmarkResult], output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "report.json"

    data = []
    for r in results:
        entry = {
            "filename": r.filename,
            "audio_duration": r.audio_duration,
            "text_metrics": {
                "global_similarity": r.text_metrics.global_similarity,
                "bigram_overlap": r.text_metrics.bigram_overlap,
                "trigram_overlap": r.text_metrics.trigram_overlap,
                "window_mean": r.text_metrics.window_mean,
                "window_min": r.text_metrics.window_min,
                "window_max": r.text_metrics.window_max,
                "per_window": r.text_metrics.per_window,
            },
            "diarization_metrics": {
                "speakers_local": r.diarization_metrics.speakers_local,
                "speakers_aai": r.diarization_metrics.speakers_aai,
                "agreement_ratio": r.diarization_metrics.agreement_ratio,
                "speaker_mapping": r.diarization_metrics.speaker_mapping,
                "turn_precision": r.diarization_metrics.turn_precision,
                "turn_recall": r.diarization_metrics.turn_recall,
                "turn_timing_mean_diff": r.diarization_metrics.turn_timing_mean_diff,
                "turn_timing_median_diff": r.diarization_metrics.turn_timing_median_diff,
                "speech_coverage_local": r.diarization_metrics.speech_coverage_local,
                "speech_coverage_aai": r.diarization_metrics.speech_coverage_aai,
            },
            "performance": {
                "rtf_local": r.rtf_local,
                "rtf_aai": r.rtf_aai,
                "latency_local": r.latency_local,
                "latency_aai": r.latency_aai,
            },
            "cost": {
                "assemblyai_usd": r.cost_aai,
                "local_usd": r.cost_local,
            },
        }
        data.append(entry)

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"JSON report: {path}")


def save_csv_summary(results: list[BenchmarkResult], output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "summary.csv"

    fieldnames = [
        "filename",
        "duration_sec",
        "text_similarity",
        "bigram_overlap",
        "trigram_overlap",
        "window_mean",
        "window_min",
        "speakers_local",
        "speakers_aai",
        "diarization_agreement",
        "turn_precision",
        "turn_recall",
        "turn_timing_mean",
        "turn_timing_median",
        "coverage_local",
        "coverage_aai",
        "rtf_local",
        "rtf_aai",
        "latency_local_sec",
        "latency_aai_sec",
        "cost_aai_usd",
    ]

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(
                {
                    "filename": r.filename,
                    "duration_sec": round(r.audio_duration, 1),
                    "text_similarity": round(r.text_metrics.global_similarity, 4),
                    "bigram_overlap": round(r.text_metrics.bigram_overlap, 4),
                    "trigram_overlap": round(r.text_metrics.trigram_overlap, 4),
                    "window_mean": round(r.text_metrics.window_mean, 4),
                    "window_min": round(r.text_metrics.window_min, 4),
                    "speakers_local": r.diarization_metrics.speakers_local,
                    "speakers_aai": r.diarization_metrics.speakers_aai,
                    "diarization_agreement": round(
                        r.diarization_metrics.agreement_ratio, 4
                    ),
                    "turn_precision": round(r.diarization_metrics.turn_precision, 4),
                    "turn_recall": round(r.diarization_metrics.turn_recall, 4),
                    "turn_timing_mean": round(
                        r.diarization_metrics.turn_timing_mean_diff, 3
                    ),
                    "turn_timing_median": round(
                        r.diarization_metrics.turn_timing_median_diff, 3
                    ),
                    "coverage_local": round(
                        r.diarization_metrics.speech_coverage_local, 4
                    ),
                    "coverage_aai": round(
                        r.diarization_metrics.speech_coverage_aai, 4
                    ),
                    "rtf_local": round(r.rtf_local, 4),
                    "rtf_aai": round(r.rtf_aai, 4),
                    "latency_local_sec": round(r.latency_local, 1),
                    "latency_aai_sec": round(r.latency_aai, 1),
                    "cost_aai_usd": round(r.cost_aai, 2),
                }
            )
    print(f"CSV summary: {path}")


# ============================================================
# Main orchestration
# ============================================================

def find_audio_files(audio_dir: Path) -> list[Path]:
    files = []
    for f in sorted(audio_dir.iterdir()):
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS:
            files.append(f)
    return files


def process_file(
    audio_path: Path,
    mode: str,
    output_dir: Path,
    skip_local: bool,
    skip_aai: bool,
    use_cache: bool,
    window_sec: float,
) -> Optional[BenchmarkResult]:
    filename = audio_path.name
    print(f"\n{'='*60}")
    print(f"  {filename}")
    print(f"{'='*60}")

    # --- Local Whisper ---
    result_local = None
    cache_local = _cache_path(output_dir, filename, "local_whisper")

    if skip_local:
        if use_cache:
            result_local = _load_cache(cache_local)
            if result_local:
                print(f"  [local] Cache carregado")
        if not result_local:
            print(f"  [local] Pulado")
    else:
        if use_cache:
            result_local = _load_cache(cache_local)
        if result_local:
            print(f"  [local] Cache carregado")
        else:
            print(f"  [local] Transcrevendo...")
            result_local = run_local_whisper(str(audio_path), mode)
            if result_local.error:
                print(f"  [local] ERRO: {result_local.error}")
            else:
                print(
                    f"  [local] OK - {len(result_local.segments)} segmentos, "
                    f"{result_local.num_speakers} speakers, "
                    f"{result_local.elapsed_seconds:.1f}s"
                )
                _save_cache(cache_local, result_local)

    # --- AssemblyAI ---
    result_aai = None
    cache_aai = _cache_path(output_dir, filename, "assemblyai")

    if skip_aai:
        if use_cache:
            result_aai = _load_cache(cache_aai)
            if result_aai:
                print(f"  [AAI]   Cache carregado")
        if not result_aai:
            print(f"  [AAI]   Pulado")
    else:
        if use_cache:
            result_aai = _load_cache(cache_aai)
        if result_aai:
            print(f"  [AAI]   Cache carregado")
        else:
            print(f"  [AAI]   Transcrevendo...")
            result_aai = run_assemblyai(str(audio_path))
            if result_aai.error:
                print(f"  [AAI]   ERRO: {result_aai.error}")
            else:
                print(
                    f"  [AAI]   OK - {len(result_aai.segments)} segmentos, "
                    f"{result_aai.num_speakers} speakers, "
                    f"{result_aai.elapsed_seconds:.1f}s"
                )
                _save_cache(cache_aai, result_aai)

    # --- Metrics ---
    if (
        not result_local
        or not result_aai
        or result_local.error
        or result_aai.error
    ):
        print(f"  [SKIP] Nao e possivel comparar - um ou ambos backends falharam")
        return None

    duration = max(result_local.audio_duration, result_aai.audio_duration)
    if duration <= 0:
        duration = max(
            max((s.end for s in result_local.segments), default=0),
            max((s.end for s in result_aai.segments), default=0),
        )

    print(f"  Calculando metricas...")
    text_m = compute_text_metrics(result_local, result_aai, window_sec)
    diar_m = compute_diarization_metrics(result_local, result_aai)

    return BenchmarkResult(
        filename=filename,
        audio_duration=duration,
        text_metrics=text_m,
        diarization_metrics=diar_m,
        rtf_local=(
            result_local.elapsed_seconds / duration if duration > 0 else 0
        ),
        rtf_aai=result_aai.elapsed_seconds / duration if duration > 0 else 0,
        latency_local=result_local.elapsed_seconds,
        latency_aai=result_aai.elapsed_seconds,
        cost_aai=(duration / 3600) * ASSEMBLYAI_RATE_PER_HOUR_USD,
        cost_local=0.0,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark: Local Whisper vs AssemblyAI Universal-2"
    )
    parser.add_argument("audio_dir", type=Path, help="Diretorio com arquivos de audio")
    parser.add_argument(
        "--mode",
        default="AUDIENCIA",
        choices=["APOSTILA", "FIDELIDADE", "AUDIENCIA", "REUNIAO", "DEPOIMENTO"],
        help="Modo de transcricao para VomoMLX (default: AUDIENCIA)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("scripts/benchmark_results"),
        help="Diretorio de saida (default: scripts/benchmark_results)",
    )
    parser.add_argument(
        "--skip-local", action="store_true", help="Pular backend local"
    )
    parser.add_argument(
        "--skip-assemblyai", action="store_true", help="Pular AssemblyAI"
    )
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help="Reusar transcricoes anteriores do cache",
    )
    parser.add_argument(
        "--window-sec",
        type=float,
        default=30.0,
        help="Tamanho da janela temporal em segundos (default: 30)",
    )

    args = parser.parse_args()

    if not args.audio_dir.exists():
        print(f"Erro: diretorio nao encontrado: {args.audio_dir}")
        sys.exit(1)

    files = find_audio_files(args.audio_dir)
    if not files:
        print(f"Nenhum arquivo de audio encontrado em {args.audio_dir}")
        print(f"Extensoes suportadas: {', '.join(sorted(AUDIO_EXTENSIONS))}")
        sys.exit(1)

    print(f"\nBenchmark: {len(files)} arquivo(s) de audio")
    print(f"  Modo:   {args.mode}")
    print(f"  Output: {args.output}")
    print(f"  Cache:  {'sim' if args.use_cache else 'nao'}")

    results = []
    for audio_path in files:
        result = process_file(
            audio_path=audio_path,
            mode=args.mode,
            output_dir=args.output,
            skip_local=args.skip_local,
            skip_aai=args.skip_assemblyai,
            use_cache=args.use_cache,
            window_sec=args.window_sec,
        )
        if result:
            results.append(result)

    if results:
        print_report(results)
        save_json_report(results, args.output)
        save_csv_summary(results, args.output)
    else:
        print("\nNenhum resultado valido para gerar relatorio.")


if __name__ == "__main__":
    main()
