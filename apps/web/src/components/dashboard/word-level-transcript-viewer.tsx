'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Play, Pause, Volume2, VolumeX, SkipBack, SkipForward } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { cn } from '@/lib/utils';

interface Word {
    word: string;
    start: number;
    end: number;
    speaker?: string;
}

interface Segment {
    start?: number;
    end?: number;
    text?: string;
    speaker?: string;
    speaker_label?: string;
}

interface WordLevelTranscriptViewerProps {
    /** Raw transcript text with [MM:SS] timestamps */
    rawContent: string;
    /** Word-level timestamps array */
    words: Word[];
    /** Optional segment-level timestamps for fallback word synthesis */
    segments?: Segment[];
    /** Audio/video URL */
    mediaUrl?: string | null;
    /** Interval for visual timestamps (seconds) - default 60 */
    timestampInterval?: number;
    className?: string;
}

const MAX_FALLBACK_WORDS = 80000;
const OVERSCAN_PX = 800;

/**
 * Formats seconds to [MM:SS] or [HH:MM:SS]
 */
function formatTimestamp(seconds: number): string {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) {
        return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    }
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

function parseTimestampToSeconds(timestamp: string): number {
    const parts = timestamp.split(':').map((p) => Number(p));
    if (parts.some((p) => Number.isNaN(p))) return 0;
    if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
    if (parts.length === 2) return parts[0] * 60 + parts[1];
    return 0;
}

function looksLikeMilliseconds(maxStart: number, mediaDuration?: number): boolean {
    if (!Number.isFinite(maxStart) || maxStart <= 0) return false;
    if (maxStart > 10000) return true;
    if (mediaDuration && mediaDuration > 0 && maxStart > mediaDuration * 8) return true;
    return false;
}

function normalizeWords(words: Word[], mediaDuration?: number): { words: Word[]; convertedFromMs: boolean } {
    if (!Array.isArray(words) || words.length === 0) {
        return { words: [], convertedFromMs: false };
    }

    const maxStart = words.reduce((acc, w) => Math.max(acc, Number(w?.start) || 0), 0);
    const convertMs = looksLikeMilliseconds(maxStart, mediaDuration);
    const factor = convertMs ? 1000 : 1;

    const normalized = words
        .map((w) => {
            const start = (Number(w?.start) || 0) / factor;
            const endRaw = (Number(w?.end) || start) / factor;
            const end = endRaw >= start ? endRaw : start + 0.2;
            const token = String(w?.word || '').trim();
            return {
                word: token,
                start: Math.max(0, start),
                end: Math.max(0, end),
                speaker: w?.speaker ? String(w.speaker) : undefined,
            };
        })
        .filter((w) => Boolean(w.word))
        .sort((a, b) => a.start - b.start || a.end - b.end);

    return { words: normalized, convertedFromMs: convertMs };
}

function normalizeSegments(segments: Segment[] | undefined, mediaDuration?: number): { segments: Segment[]; convertedFromMs: boolean } {
    if (!Array.isArray(segments) || segments.length === 0) {
        return { segments: [], convertedFromMs: false };
    }

    const maxStart = segments.reduce((acc, s) => Math.max(acc, Number(s?.start) || 0), 0);
    const convertMs = looksLikeMilliseconds(maxStart, mediaDuration);
    const factor = convertMs ? 1000 : 1;

    const normalized = segments
        .map((s) => {
            const start = s.start !== undefined ? (Number(s.start) || 0) / factor : undefined;
            const end = s.end !== undefined ? (Number(s.end) || 0) / factor : undefined;
            return {
                ...s,
                start: start !== undefined ? Math.max(0, start) : undefined,
                end: end !== undefined ? Math.max(0, end) : undefined,
            };
        })
        .filter((s) => String(s?.text || '').trim().length > 0);

    return { segments: normalized, convertedFromMs: convertMs };
}

function tokenize(text: string): string[] {
    return (text.match(/\S+/g) || []).map((t) => t.trim()).filter(Boolean);
}

function buildWordsFromSegments(segments: Segment[]): Word[] {
    const out: Word[] = [];
    if (!Array.isArray(segments) || segments.length === 0) return out;

    for (const seg of segments) {
        if (out.length >= MAX_FALLBACK_WORDS) break;
        const text = String(seg?.text || '').trim();
        if (!text) continue;
        const tokens = tokenize(text);
        if (tokens.length === 0) continue;

        const start = Number(seg?.start) || 0;
        const segmentSpeaker = seg?.speaker ? String(seg.speaker) : (seg?.speaker_label ? String(seg.speaker_label) : undefined);
        const endCandidate = Number(seg?.end);
        const end = Number.isFinite(endCandidate) && endCandidate > start
            ? endCandidate
            : start + Math.max(0.6, tokens.length * 0.32);
        const step = Math.max(0.08, (end - start) / Math.max(tokens.length, 1));

        for (let i = 0; i < tokens.length; i += 1) {
            if (out.length >= MAX_FALLBACK_WORDS) break;
            const wStart = start + i * step;
            const wEnd = Math.max(wStart + 0.05, start + (i + 1) * step);
            out.push({
                word: tokens[i],
                start: wStart,
                end: wEnd,
                speaker: segmentSpeaker,
            });
        }
    }
    return out;
}

function buildWordsFromRaw(rawContent: string): Word[] {
    const out: Word[] = [];
    const lines = (rawContent || '').split('\n');
    const tsRegex = /\[(\d{1,2}:\d{2}(?::\d{2})?)\]/g;
    const speakerRegex = /^\*{0,2}\s*SPEAKER\s+\d+\s*\*{0,2}$/i;
    let cursor = 0;

    for (const lineRaw of lines) {
        if (out.length >= MAX_FALLBACK_WORDS) break;
        const line = lineRaw.trim();
        if (!line) continue;
        if (speakerRegex.test(line)) continue;

        let working = line;
        const matches = [...line.matchAll(tsRegex)];
        if (matches.length > 0) {
            const last = matches[matches.length - 1];
            cursor = parseTimestampToSeconds(last[1]);
            working = line.replace(tsRegex, ' ').trim();
        }

        const tokens = tokenize(working);
        if (tokens.length === 0) continue;

        const step = 0.28;
        for (let i = 0; i < tokens.length; i += 1) {
            if (out.length >= MAX_FALLBACK_WORDS) break;
            const start = cursor + i * step;
            out.push({
                word: tokens[i],
                start,
                end: start + step,
            });
        }
        cursor += Math.max(tokens.length * step, 0.45);
    }
    return out;
}

interface WordBlock {
    startTime: number;
    words: Word[];
    showTimestamp: boolean;
    speaker?: string;
}

/**
 * Groups words into blocks by speaker changes and/or time intervals.
 * When diarization is active (words have speaker field), groups by speaker.
 * Otherwise, groups by time interval.
 */
function groupWordsIntoBlocks(words: Word[], intervalSeconds: number = 60): WordBlock[] {
    if (!words || words.length === 0) return [];

    const blocks: WordBlock[] = [];
    let currentBlock: WordBlock | null = null;
    let lastShownTimestamp = intervalSeconds > 0 ? -intervalSeconds : Number.NEGATIVE_INFINITY;

    for (const word of words) {
        const speaker = word.speaker;
        const speakerChanged = currentBlock && speaker !== currentBlock.speaker;
        const shouldShowTimestamp = intervalSeconds === 0 || (word.start - lastShownTimestamp >= intervalSeconds);
        const shouldStartNewBlock = !currentBlock || Boolean(speakerChanged) || shouldShowTimestamp;

        if (shouldStartNewBlock) {
            if (currentBlock) blocks.push(currentBlock);
            currentBlock = {
                startTime: word.start,
                words: [],
                showTimestamp: shouldShowTimestamp,
                speaker,
            };
            if (shouldShowTimestamp) lastShownTimestamp = word.start;
        }
        if (!currentBlock) continue;
        currentBlock.words.push(word);
    }

    if (currentBlock) blocks.push(currentBlock);
    return blocks;
}

function estimateBlockHeight(block: WordBlock): number {
    const textLength = block.words.reduce((acc, w) => acc + w.word.length + 1, 0);
    const approxLines = Math.max(1, Math.ceil(textLength / 72));
    const labelExtra = block.speaker ? 20 : 0;
    const timestampExtra = block.showTimestamp ? 14 : 0;
    return 20 + labelExtra + timestampExtra + approxLines * 24;
}

function findIndexForOffset(prefixHeights: number[], target: number): number {
    if (prefixHeights.length === 0) return 0;
    let low = 0;
    let high = prefixHeights.length - 1;
    let ans = high;
    while (low <= high) {
        const mid = Math.floor((low + high) / 2);
        if (prefixHeights[mid] > target) {
            ans = mid;
            high = mid - 1;
        } else {
            low = mid + 1;
        }
    }
    return ans;
}

export function WordLevelTranscriptViewer({
    rawContent,
    words,
    segments = [],
    mediaUrl,
    timestampInterval = 60,
    className,
}: WordLevelTranscriptViewerProps) {
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const containerRef = useRef<HTMLDivElement | null>(null);
    const activeWordRef = useRef<HTMLSpanElement | null>(null);
    const rafRef = useRef<number | null>(null);

    const [isPlaying, setIsPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [isMuted, setIsMuted] = useState(false);
    const [playbackRate, setPlaybackRate] = useState(1);
    const [scrollTop, setScrollTop] = useState(0);
    const [viewportHeight, setViewportHeight] = useState(600);

    const hasAudio = Boolean(mediaUrl);
    const normalizedData = useMemo(() => {
        const normalizedProvider = normalizeWords(words, duration || undefined);
        if (normalizedProvider.words.length > 0) {
            return {
                words: normalizedProvider.words,
                source: 'provider' as const,
                convertedFromMs: normalizedProvider.convertedFromMs,
            };
        }

        const normalizedSegs = normalizeSegments(segments, duration || undefined);
        const fromSegments = buildWordsFromSegments(normalizedSegs.segments);
        if (fromSegments.length > 0) {
            const normalizedFallback = normalizeWords(fromSegments, duration || undefined);
            return {
                words: normalizedFallback.words,
                source: 'segments' as const,
                convertedFromMs: normalizedSegs.convertedFromMs || normalizedFallback.convertedFromMs,
            };
        }

        const fromRaw = buildWordsFromRaw(rawContent);
        const normalizedRaw = normalizeWords(fromRaw, duration || undefined);
        return {
            words: normalizedRaw.words,
            source: normalizedRaw.words.length > 0 ? ('raw' as const) : ('none' as const),
            convertedFromMs: normalizedRaw.convertedFromMs,
        };
    }, [words, segments, rawContent, duration]);
    const normalizedWords = normalizedData.words;
    const hasWords = normalizedWords.length > 0;
    const fallbackApproximate = normalizedData.source !== 'provider' && normalizedData.source !== 'none';

    // Debug checks for transcript timing data (development only)
    useEffect(() => {
        if (!hasWords || process.env.NODE_ENV !== 'development') return;

        let unordered = 0;
        let endBeforeStart = 0;
        let negative = 0;
        let maxStart = -Infinity;
        let firstUnorderedIndex: number | null = null;
        let firstEndBeforeStartIndex: number | null = null;

        let lastStart = -Infinity;
        for (let i = 0; i < normalizedWords.length; i += 1) {
            const w = normalizedWords[i];
            if (w.start < lastStart) {
                unordered += 1;
                if (firstUnorderedIndex === null) firstUnorderedIndex = i;
            }
            if (w.end < w.start) {
                endBeforeStart += 1;
                if (firstEndBeforeStartIndex === null) firstEndBeforeStartIndex = i;
            }
            if (w.start < 0 || w.end < 0) {
                negative += 1;
            }
            if (w.start > maxStart) maxStart = w.start;
            lastStart = w.start;
        }

        const msLikely = maxStart > 10000; // > ~2.7h suggests ms, not seconds

        console.warn('[WordTimingCheck]', {
            count: normalizedWords.length,
            unordered,
            endBeforeStart,
            negative,
            msLikely,
            maxStart,
            firstUnorderedIndex,
            firstEndBeforeStartIndex,
            source: normalizedData.source,
            convertedFromMs: normalizedData.convertedFromMs,
        });
    }, [normalizedWords, hasWords, normalizedData]);

    // Group words into blocks with timestamps
    const blocks = useMemo(
        () => (hasWords ? groupWordsIntoBlocks(normalizedWords, timestampInterval) : []),
        [normalizedWords, timestampInterval, hasWords]
    );

    // Binary search to find active word index based on current time
    const activeWordIndex = useMemo(() => {
        if (!hasWords || normalizedWords.length === 0) return -1;

        // First, check for exact match (word.start <= time <= word.end)
        let left = 0;
        let right = normalizedWords.length - 1;
        let lastBefore = -1;

        while (left <= right) {
            const mid = Math.floor((left + right) / 2);
            const word = normalizedWords[mid];

            if (word.start <= currentTime && word.end >= currentTime) {
                return mid; // Exact match found
            }

            if (word.end < currentTime) {
                lastBefore = mid; // This word ended before current time
                left = mid + 1;
            } else {
                right = mid - 1;
            }
        }

        // If no exact match, return the last word that ended before current time
        return lastBefore;
    }, [currentTime, normalizedWords, hasWords]);

    const wordIndexMaps = useMemo(() => {
        const indices = new Map<string, number>();
        const blockByWord: number[] = [];
        let globalIdx = 0;
        blocks.forEach((block, blockIndex) => {
            block.words.forEach((_, wordIndex) => {
                indices.set(`${blockIndex}-${wordIndex}`, globalIdx);
                blockByWord[globalIdx] = blockIndex;
                globalIdx += 1;
            });
        });
        return { indices, blockByWord };
    }, [blocks]);

    const activeBlockIndex = useMemo(() => {
        if (activeWordIndex < 0) return -1;
        return wordIndexMaps.blockByWord[activeWordIndex] ?? -1;
    }, [activeWordIndex, wordIndexMaps]);

    const blockHeights = useMemo(() => blocks.map((b) => estimateBlockHeight(b)), [blocks]);
    const blockPrefixHeights = useMemo(() => {
        const prefix: number[] = [];
        let acc = 0;
        for (const h of blockHeights) {
            acc += h;
            prefix.push(acc);
        }
        return prefix;
    }, [blockHeights]);
    const totalContentHeight = blockPrefixHeights.length > 0 ? blockPrefixHeights[blockPrefixHeights.length - 1] : 0;

    const visibleRange = useMemo(() => {
        if (!hasWords || blocks.length === 0) {
            return { start: 0, end: -1, topSpacer: 0, bottomSpacer: 0 };
        }
        const startTarget = Math.max(0, scrollTop - OVERSCAN_PX);
        const endTarget = scrollTop + Math.max(viewportHeight, 200) + OVERSCAN_PX;
        let start = findIndexForOffset(blockPrefixHeights, startTarget);
        let end = findIndexForOffset(blockPrefixHeights, endTarget);

        start = Math.max(0, Math.min(start, blocks.length - 1));
        end = Math.max(start, Math.min(end, blocks.length - 1));

        // Always keep active block rendered while playing
        if (isPlaying && activeBlockIndex >= 0) {
            start = Math.min(start, activeBlockIndex);
            end = Math.max(end, activeBlockIndex);
        }

        const topSpacer = start > 0 ? blockPrefixHeights[start - 1] : 0;
        const bottomSpacer = totalContentHeight - (blockPrefixHeights[end] || 0);
        return { start, end, topSpacer, bottomSpacer };
    }, [hasWords, blocks.length, scrollTop, viewportHeight, blockPrefixHeights, totalContentHeight, isPlaying, activeBlockIndex]);

    // Auto-scroll to active word (with debounce to avoid scroll jank)
    useEffect(() => {
        if (activeWordRef.current && isPlaying) {
            // Use 'auto' instead of 'smooth' to prevent scroll lag during playback
            activeWordRef.current.scrollIntoView({
                behavior: 'auto',
                block: 'center',
            });
        }
    }, [activeWordIndex, isPlaying]);

    useEffect(() => {
        const container = containerRef.current;
        if (!container) return;

        const updateViewport = () => setViewportHeight(container.clientHeight || 600);
        updateViewport();
        const observer = new ResizeObserver(updateViewport);
        observer.observe(container);

        const onScroll = () => setScrollTop(container.scrollTop);
        container.addEventListener('scroll', onScroll, { passive: true });

        return () => {
            observer.disconnect();
            container.removeEventListener('scroll', onScroll);
        };
    }, []);

    // Audio event handlers with throttled timeupdate
    useEffect(() => {
        const audio = audioRef.current;
        if (!audio) return;

        // Throttle timeupdate using requestAnimationFrame
        const onTimeUpdate = () => {
            if (rafRef.current !== null) return;
            rafRef.current = requestAnimationFrame(() => {
                if (audioRef.current) {
                    setCurrentTime(audioRef.current.currentTime);
                }
                rafRef.current = null;
            });
        };

        const onDurationChange = () => setDuration(audio.duration || 0);
        const onPlay = () => setIsPlaying(true);
        const onPause = () => setIsPlaying(false);
        const onEnded = () => setIsPlaying(false);

        audio.addEventListener('timeupdate', onTimeUpdate);
        audio.addEventListener('durationchange', onDurationChange);
        audio.addEventListener('play', onPlay);
        audio.addEventListener('pause', onPause);
        audio.addEventListener('ended', onEnded);

        return () => {
            audio.removeEventListener('timeupdate', onTimeUpdate);
            audio.removeEventListener('durationchange', onDurationChange);
            audio.removeEventListener('play', onPlay);
            audio.removeEventListener('pause', onPause);
            audio.removeEventListener('ended', onEnded);
            // Cancel any pending RAF
            if (rafRef.current !== null) {
                cancelAnimationFrame(rafRef.current);
                rafRef.current = null;
            }
        };
    }, [mediaUrl]);

    // Update playback rate
    useEffect(() => {
        if (audioRef.current) {
            audioRef.current.playbackRate = playbackRate;
        }
    }, [playbackRate]);

    const handlePlayPause = useCallback(() => {
        const audio = audioRef.current;
        if (!audio) return;

        if (isPlaying) {
            audio.pause();
        } else {
            audio.play();
        }
    }, [isPlaying]);

    const handleSeek = useCallback((seconds: number) => {
        const audio = audioRef.current;
        if (audio) {
            const newTime = Math.max(0, Math.min(seconds, audio.duration || 0));
            audio.currentTime = newTime;
            // Immediately update currentTime for responsive UI
            // (timeupdate will also fire, but we want instant feedback)
            setCurrentTime(newTime);
        }
    }, []);

    const handleWordClick = useCallback(
        (word: Word) => {
            // Debug: log timestamp info
            if (process.env.NODE_ENV === 'development') {
                console.log('[WordClick]', {
                    word: word.word,
                    start: word.start,
                    end: word.end,
                    formatted: formatTimestamp(word.start),
                    audioDuration: audioRef.current?.duration,
                    currentAudioTime: audioRef.current?.currentTime,
                });
            }
            handleSeek(word.start);
            if (audioRef.current && !isPlaying) {
                audioRef.current.play();
            }
        },
        [handleSeek, isPlaying]
    );

    const handleMuteToggle = useCallback(() => {
        const audio = audioRef.current;
        if (audio) {
            audio.muted = !audio.muted;
            setIsMuted(!isMuted);
        }
    }, [isMuted]);

    const handleSkip = useCallback(
        (seconds: number) => {
            handleSeek(currentTime + seconds);
        },
        [currentTime, handleSeek]
    );

    return (
        <div className={cn('flex flex-col h-full', className)}>
            {/* Audio Player */}
            {hasAudio && (
                <div className="flex-shrink-0 border-b bg-muted/30 p-3 space-y-2">
                    <audio ref={audioRef} src={mediaUrl!} preload="metadata" />

                    <div className="flex items-center gap-2">
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => handleSkip(-10)}
                            title="Voltar 10s"
                        >
                            <SkipBack className="h-4 w-4" />
                        </Button>

                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-10 w-10"
                            onClick={handlePlayPause}
                        >
                            {isPlaying ? (
                                <Pause className="h-5 w-5" />
                            ) : (
                                <Play className="h-5 w-5" />
                            )}
                        </Button>

                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => handleSkip(10)}
                            title="Avançar 10s"
                        >
                            <SkipForward className="h-4 w-4" />
                        </Button>

                        <div className="flex-1 flex items-center gap-2">
                            <span className="text-xs font-mono text-muted-foreground w-14">
                                {formatTimestamp(currentTime)}
                            </span>
                            <Slider
                                value={[currentTime]}
                                min={0}
                                max={duration || 100}
                                step={0.1}
                                onValueChange={([v]) => handleSeek(v)}
                                className="flex-1"
                            />
                            <span className="text-xs font-mono text-muted-foreground w-14">
                                {formatTimestamp(duration)}
                            </span>
                        </div>

                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={handleMuteToggle}
                        >
                            {isMuted ? (
                                <VolumeX className="h-4 w-4" />
                            ) : (
                                <Volume2 className="h-4 w-4" />
                            )}
                        </Button>

                        <select
                            value={playbackRate}
                            onChange={(e) => setPlaybackRate(Number(e.target.value))}
                            className="h-8 rounded-md border border-input bg-background px-2 text-xs"
                        >
                            <option value={0.5}>0.5x</option>
                            <option value={0.75}>0.75x</option>
                            <option value={1}>1x</option>
                            <option value={1.25}>1.25x</option>
                            <option value={1.5}>1.5x</option>
                            <option value={2}>2x</option>
                        </select>
                    </div>
                </div>
            )}

            {/* Transcript with clickable words */}
            <div ref={containerRef} className="flex-1 overflow-y-auto p-4">
                {!hasWords ? (
                    // Fallback: show raw content without word-level interaction
                    <pre className="whitespace-pre-wrap text-sm font-mono text-foreground">
                        {rawContent}
                    </pre>
                ) : (
                    <div className="space-y-4">
                        {fallbackApproximate && (
                            <div className="rounded-md border border-blue-200 bg-blue-50 px-2 py-1 text-xs text-blue-900">
                                Navegação aproximada por palavra (gerada a partir de {normalizedData.source === 'segments' ? 'segmentos' : 'texto bruto'}).
                            </div>
                        )}
                        {normalizedData.convertedFromMs && (
                            <div className="rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-xs text-amber-900">
                                Timestamps normalizados automaticamente de ms para s.
                            </div>
                        )}
                        {visibleRange.topSpacer > 0 && <div style={{ height: visibleRange.topSpacer }} />}
                        {blocks.slice(visibleRange.start, visibleRange.end + 1).map((block, localIndex) => {
                            const blockIndex = visibleRange.start + localIndex;
                            const blockWords = block.words.map((word, wordIndex) => {
                                const globalIndex = wordIndexMaps.indices.get(`${blockIndex}-${wordIndex}`) ?? -1;
                                const isActive = globalIndex === activeWordIndex;

                                return (
                                    <span
                                        key={`${blockIndex}-${wordIndex}`}
                                        ref={isActive ? activeWordRef : null}
                                        onClick={() => handleWordClick(word)}
                                        className={cn(
                                            'cursor-pointer hover:bg-primary/20 rounded px-0.5 transition-colors',
                                            isActive && 'bg-primary/30 text-primary font-medium'
                                        )}
                                        title={`${formatTimestamp(word.start)} - Clique para ouvir`}
                                    >
                                        {word.word}
                                    </span>
                                );
                            });

                            return (
                                <div key={blockIndex} className="leading-relaxed">
                                    {/* Speaker label when diarization is active */}
                                    {block.speaker && (
                                        <span className="inline-block text-xs font-semibold text-secondary-foreground bg-secondary rounded px-1.5 py-0.5 mr-2 mb-1">
                                            {block.speaker}
                                        </span>
                                    )}
                                    {block.showTimestamp && (
                                        <span
                                            className="inline-block font-mono text-xs text-primary bg-primary/10 rounded px-1.5 py-0.5 mr-2 cursor-pointer hover:bg-primary/20"
                                            onClick={() => handleSeek(block.startTime)}
                                            title="Clique para ir a este momento"
                                        >
                                            [{formatTimestamp(block.startTime)}]
                                        </span>
                                    )}
                                    {blockWords.reduce<React.ReactNode[]>((acc, word, i) => {
                                        if (i > 0) acc.push(' ');
                                        acc.push(word);
                                        return acc;
                                    }, [])}
                                </div>
                            );
                        })}
                        {visibleRange.bottomSpacer > 0 && <div style={{ height: visibleRange.bottomSpacer }} />}
                    </div>
                )}
            </div>
        </div>
    );
}
