import argparse
import os
import re
import subprocess
import tempfile
from pathlib import Path


def _ffprobe_duration_seconds(path: str) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    out = subprocess.check_output(cmd, text=True).strip()
    try:
        return float(out)
    except Exception:
        return 0.0


def _parse_ts_to_seconds(ts: str) -> int:
    parts = ts.split(":")
    if len(parts) == 2:
        m, s = parts
        return int(m) * 60 + int(s)
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + int(s)
    raise ValueError(f"invalid timestamp: {ts!r}")


def _format_seconds_as_ts(seconds: int) -> str:
    if seconds < 0:
        seconds = 0
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"


_TS_RE = re.compile(r"\[(\d{2}:\d{2}(?::\d{2})?)\]")


def _shift_timestamps(text: str, *, offset_seconds: int) -> str:
    def repl(m: re.Match) -> str:
        ts = m.group(1)
        total = _parse_ts_to_seconds(ts) + int(offset_seconds)
        return f"[{_format_seconds_as_ts(total)}]"

    return _TS_RE.sub(repl, text)


def _extract_chunk_wav(
    *,
    input_audio: str,
    start_seconds: int,
    duration_seconds: int,
    out_wav: str,
) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        str(int(start_seconds)),
        "-t",
        str(int(duration_seconds)),
        "-i",
        input_audio,
        "-ar",
        "16000",
        "-ac",
        "1",
        "-acodec",
        "pcm_s16le",
        out_wav,
    ]
    subprocess.check_call(cmd)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Transcreve áudio longo em chunks e consolida em um RAW único (timestamps ajustados)."
    )
    parser.add_argument("input_audio", help="Arquivo de áudio/vídeo (mp3/mp4/etc).")
    parser.add_argument(
        "--output",
        required=True,
        help="Caminho do RAW consolidado (.txt).",
    )
    parser.add_argument("--mode", default="FIDELIDADE", help="Modo (APOSTILA/FIDELIDADE/etc).")
    parser.add_argument("--language", default="pt", help="Idioma (pt/en/auto).")
    parser.add_argument(
        "--chunk-minutes",
        type=int,
        default=60,
        help="Tamanho de cada chunk em minutos (default: 60).",
    )
    parser.add_argument(
        "--provider",
        default="gemini",
        choices=["gemini", "openai"],
        help="Provider do VomoMLX (default: gemini).",
    )
    parser.add_argument(
        "--keep-chunks",
        action="store_true",
        help="Mantém arquivos temporários de chunks (.wav e raw) ao lado do output.",
    )

    args = parser.parse_args()

    input_audio = str(Path(args.input_audio).expanduser())
    out_path = Path(args.output).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    total_seconds = int(_ffprobe_duration_seconds(input_audio))
    if total_seconds <= 0:
        raise SystemExit("Falha ao detectar duração do áudio via ffprobe.")

    chunk_seconds = max(60, int(args.chunk_minutes) * 60)

    # Importa VomoMLX só depois de validar ffprobe (evita inicialização pesada desnecessária).
    from mlx_vomo import VomoMLX  # noqa: WPS433

    vomo = VomoMLX(provider=args.provider)

    merged_parts: list[str] = []
    temp_root = out_path.parent / (out_path.stem + "_chunks")
    if args.keep_chunks:
        temp_root.mkdir(parents=True, exist_ok=True)

    chunk_index = 0
    start = 0
    while start < total_seconds:
        dur = min(chunk_seconds, total_seconds - start)
        chunk_index += 1
        chunk_tag = f"chunk_{chunk_index:02d}_{_format_seconds_as_ts(start).replace(':', '-')}"

        if args.keep_chunks:
            chunk_wav = temp_root / f"{chunk_tag}.wav"
        else:
            # Use temp files to avoid clutter.
            fd, tmp_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            chunk_wav = Path(tmp_path)

        _extract_chunk_wav(
            input_audio=input_audio,
            start_seconds=start,
            duration_seconds=dur,
            out_wav=str(chunk_wav),
        )

        chunk_raw = vomo.transcribe_file(
            str(chunk_wav),
            mode=args.mode,
            diarization=False,
            language=args.language,
        )

        chunk_raw_shifted = _shift_timestamps(chunk_raw, offset_seconds=start)
        merged_parts.append(f"\n\n===== {chunk_tag} =====\n\n{chunk_raw_shifted}\n")

        if args.keep_chunks:
            (temp_root / f"{chunk_tag}_RAW.txt").write_text(chunk_raw_shifted, encoding="utf-8")
        else:
            try:
                chunk_wav.unlink(missing_ok=True)
            except Exception:
                pass

        start += chunk_seconds

    out_path.write_text("".join(merged_parts).lstrip(), encoding="utf-8")
    print(f"OK: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

