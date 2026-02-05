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

interface WordLevelTranscriptViewerProps {
    /** Raw transcript text with [MM:SS] timestamps */
    rawContent: string;
    /** Word-level timestamps array */
    words: Word[];
    /** Audio/video URL */
    mediaUrl?: string | null;
    /** Interval for visual timestamps (seconds) - default 60 */
    timestampInterval?: number;
    className?: string;
}

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

    const hasDiarization = words.some(w => w.speaker);
    const blocks: WordBlock[] = [];
    let currentBlock: Word[] = [];
    let currentSpeaker: string | undefined = undefined;
    let lastTimestamp = -intervalSeconds;
    let blockStartTime = 0;

    for (const word of words) {
        const speakerChanged = hasDiarization && word.speaker !== currentSpeaker;
        const timeIntervalReached = intervalSeconds > 0 && word.start - lastTimestamp >= intervalSeconds;
        const shouldStartNewBlock = speakerChanged || (!hasDiarization && timeIntervalReached);

        if (shouldStartNewBlock && currentBlock.length > 0) {
            blocks.push({
                startTime: blockStartTime,
                words: currentBlock,
                showTimestamp: true,
                speaker: currentSpeaker,
            });
            currentBlock = [];
            lastTimestamp = word.start;
            blockStartTime = word.start;
        }

        if (currentBlock.length === 0) {
            blockStartTime = word.start;
            currentSpeaker = word.speaker;
        }

        currentBlock.push(word);
    }

    // Add remaining words
    if (currentBlock.length > 0) {
        blocks.push({
            startTime: blockStartTime,
            words: currentBlock,
            showTimestamp: true,
            speaker: currentSpeaker,
        });
    }

    // When no diarization, apply interval-based timestamp visibility
    if (!hasDiarization && intervalSeconds > 0) {
        let lastShownTimestamp = -intervalSeconds;
        return blocks.map((block) => {
            const shouldShow = block.startTime - lastShownTimestamp >= intervalSeconds;
            if (shouldShow) {
                lastShownTimestamp = block.startTime;
            }
            return { ...block, showTimestamp: shouldShow };
        });
    }

    return blocks;
}

export function WordLevelTranscriptViewer({
    rawContent,
    words,
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

    const hasAudio = Boolean(mediaUrl);
    const hasWords = words && words.length > 0;

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
        for (let i = 0; i < words.length; i += 1) {
            const w = words[i];
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
            count: words.length,
            unordered,
            endBeforeStart,
            negative,
            msLikely,
            maxStart,
            firstUnorderedIndex,
            firstEndBeforeStartIndex,
        });
    }, [words, hasWords]);

    // Group words into blocks with timestamps
    const blocks = useMemo(
        () => (hasWords ? groupWordsIntoBlocks(words, timestampInterval) : []),
        [words, timestampInterval, hasWords]
    );

    // Binary search to find active word index based on current time
    const activeWordIndex = useMemo(() => {
        if (!hasWords || words.length === 0) return -1;

        // First, check for exact match (word.start <= time <= word.end)
        let left = 0;
        let right = words.length - 1;
        let lastBefore = -1;

        while (left <= right) {
            const mid = Math.floor((left + right) / 2);
            const word = words[mid];

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
    }, [currentTime, words, hasWords]);

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

    // Pre-compute global index for each word in blocks for accurate highlighting
    const wordGlobalIndices = useMemo(() => {
        const indices = new Map<string, number>();
        let globalIdx = 0;
        blocks.forEach((block, blockIndex) => {
            block.words.forEach((_, wordIndex) => {
                indices.set(`${blockIndex}-${wordIndex}`, globalIdx++);
            });
        });
        return indices;
    }, [blocks]);

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
                        {blocks.map((block, blockIndex) => {
                            const blockWords = block.words.map((word, wordIndex) => {
                                const globalIndex = wordGlobalIndices.get(`${blockIndex}-${wordIndex}`) ?? -1;
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
                    </div>
                )}
            </div>
        </div>
    );
}
