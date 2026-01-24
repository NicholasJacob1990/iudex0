'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Play, Pause, Volume2, VolumeX, ChevronDown, FileAudio } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { cn } from '@/lib/utils';

interface MediaFile {
    name: string;
    url: string;
}

interface ParsedSegment {
    id: string;
    fileIndex: number;
    startSeconds: number;
    text: string;
    isSpeakerHeader: boolean;
    isFileHeader: boolean;
}

interface SyncedTranscriptViewerProps {
    rawContent: string;
    /** Single media URL (legacy support) */
    mediaUrl?: string | null;
    /** Multiple media files for batch mode - order must match file order in rawContent */
    mediaFiles?: MediaFile[];
    className?: string;
}

/**
 * Parses timestamps in [MM:SS] or [HH:MM:SS] format to seconds
 */
function parseTimestampToSeconds(timestamp: string): number {
    const parts = timestamp.split(':').map(Number);
    if (parts.length === 3) {
        return parts[0] * 3600 + parts[1] * 60 + parts[2];
    } else if (parts.length === 2) {
        return parts[0] * 60 + parts[1];
    }
    return 0;
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

/**
 * Detects file/block headers in consolidated transcripts
 */
function isFileHeader(line: string): boolean {
    const trimmed = line.trim();
    // Pattern 1: # filename
    if (/^#\s+\S/.test(trimmed) && !trimmed.startsWith('##')) return true;
    // Pattern 2: BLOCO N
    if (/^BLOCO\s+\d+/i.test(trimmed)) return true;
    // Pattern 3: ━━━━ separator followed by text
    if (/^[━─═]{10,}$/.test(trimmed)) return true;
    return false;
}

/**
 * Parses raw transcript text into segments with file boundaries
 */
function parseRawContent(content: string): { segments: ParsedSegment[]; fileHeaders: string[] } {
    const lines = content.split('\n');
    const segments: ParsedSegment[] = [];
    const fileHeaders: string[] = [];
    const timestampRegex = /^\[(\d{1,2}:\d{2}(?::\d{2})?)\]\s*/;
    const speakerRegex = /^\*\*SPEAKER\s+\d+\*\*$|^SPEAKER\s+\d+$/i;

    let currentFileIndex = 0;
    let lastTimestamp = 0;
    let lastLineWasSeparator = false;

    lines.forEach((line, index) => {
        const trimmed = line.trim();
        if (!trimmed) return;

        // Check for file separator (━━━ pattern)
        if (/^[━─═]{10,}$/.test(trimmed)) {
            lastLineWasSeparator = true;
            return;
        }

        // Check for file/block header after separator or at start
        if (lastLineWasSeparator || (index === 0 && isFileHeader(trimmed))) {
            if (/^BLOCO\s+\d+/i.test(trimmed) || /^#\s+\S/.test(trimmed) || /^\[#/.test(trimmed)) {
                // New file/block detected
                const headerText = trimmed.replace(/^#\s*/, '').replace(/^BLOCO\s+/i, 'Bloco ').replace(/^\[#\s*/, '').replace(/^\[/, '');
                fileHeaders.push(headerText);

                if (segments.length > 0) {
                    currentFileIndex++;
                }

                segments.push({
                    id: `file-header-${currentFileIndex}`,
                    fileIndex: currentFileIndex,
                    startSeconds: 0,
                    text: headerText,
                    isSpeakerHeader: false,
                    isFileHeader: true,
                });

                lastTimestamp = 0; // Reset timestamp for new file
                lastLineWasSeparator = false;
                return;
            }
        }

        lastLineWasSeparator = false;

        // Check if it's a speaker header
        if (speakerRegex.test(trimmed)) {
            segments.push({
                id: `segment-${index}`,
                fileIndex: currentFileIndex,
                startSeconds: lastTimestamp,
                text: trimmed,
                isSpeakerHeader: true,
                isFileHeader: false,
            });
            return;
        }

        // Regex for inline timestamps
        const parts = trimmed.split(/(\[\d{1,2}:\d{2}(?::\d{2})?\])/);

        if (parts.length === 1) {
            // No inline timestamps, use existing logic checks (fallback)
            // Check start of line (already covered by split if it starts)
            // Just add text with lastTimestamp
            segments.push({
                id: `segment-${index}`,
                fileIndex: currentFileIndex,
                startSeconds: lastTimestamp,
                text: trimmed,
                isSpeakerHeader: false,
                isFileHeader: false,
            });
        } else {
            // Process parts
            parts.forEach((part, partIndex) => {
                const tsMatch = part.match(/^\[(\d{1,2}:\d{2}(?::\d{2})?)\]$/);
                if (tsMatch) {
                    lastTimestamp = parseTimestampToSeconds(tsMatch[1]);
                } else if (part.trim()) {
                    segments.push({
                        id: `segment-${index}-${partIndex}`,
                        fileIndex: currentFileIndex,
                        startSeconds: lastTimestamp,
                        text: part,
                        isSpeakerHeader: false,
                        isFileHeader: false,
                    });
                }
            });
        }
    });

    // If no file headers found, add a default one
    if (fileHeaders.length === 0) {
        fileHeaders.push('Arquivo 1');
    }

    return { segments, fileHeaders };
}

export function SyncedTranscriptViewer({
    rawContent,
    mediaUrl,
    mediaFiles = [],
    className
}: SyncedTranscriptViewerProps) {
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const containerRef = useRef<HTMLDivElement | null>(null);
    const activeSegmentRef = useRef<HTMLDivElement | null>(null);

    const [activeFileIndex, setActiveFileIndex] = useState(0);
    const [isPlaying, setIsPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);
    const [isMuted, setIsMuted] = useState(false);
    const [playbackRate, setPlaybackRate] = useState(1);
    const [showFileSelector, setShowFileSelector] = useState(false);

    // Parse content into segments
    const { segments, fileHeaders } = useMemo(() => parseRawContent(rawContent), [rawContent]);

    // Build media sources list
    const mediaSources = useMemo(() => {
        if (mediaFiles.length > 0) {
            return mediaFiles;
        }
        if (mediaUrl) {
            return [{ name: 'Arquivo', url: mediaUrl }];
        }
        return [];
    }, [mediaUrl, mediaFiles]);

    const hasAudio = mediaSources.length > 0;
    const hasMultipleFiles = fileHeaders.length > 1 && mediaSources.length > 1;
    const currentMediaUrl = mediaSources[activeFileIndex]?.url || mediaSources[0]?.url;

    // Find active segment based on current time and file
    const activeSegmentIndex = useMemo(() => {
        if (segments.length === 0) return -1;

        let lastValidIndex = -1;
        for (let i = 0; i < segments.length; i++) {
            const seg = segments[i];
            if (seg.fileIndex === activeFileIndex && !seg.isSpeakerHeader && !seg.isFileHeader) {
                if (seg.startSeconds <= currentTime) {
                    lastValidIndex = i;
                }
            }
        }
        return lastValidIndex;
    }, [segments, currentTime, activeFileIndex]);

    const activeTimestamp = useMemo(() => {
        if (activeSegmentIndex === -1) return -1;
        return segments[activeSegmentIndex]?.startSeconds ?? -1;
    }, [activeSegmentIndex, segments]);

    // Auto-scroll to active segment
    useEffect(() => {
        if (activeSegmentRef.current && isPlaying) {
            activeSegmentRef.current.scrollIntoView({
                behavior: 'smooth',
                block: 'center',
            });
        }
    }, [activeSegmentIndex, isPlaying]);

    // Audio event handlers
    useEffect(() => {
        const audio = audioRef.current;
        if (!audio) return;

        const onTimeUpdate = () => setCurrentTime(audio.currentTime);
        const onDurationChange = () => setDuration(audio.duration || 0);
        const onPlay = () => setIsPlaying(true);
        const onPause = () => setIsPlaying(false);
        const onEnded = () => {
            setIsPlaying(false);
            // Auto-advance to next file if available
            if (hasMultipleFiles && activeFileIndex < mediaSources.length - 1) {
                setActiveFileIndex(activeFileIndex + 1);
                setCurrentTime(0);
            }
        };

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
        };
    }, [currentMediaUrl, activeFileIndex, hasMultipleFiles, mediaSources.length]);

    // Update playback rate
    useEffect(() => {
        if (audioRef.current) {
            audioRef.current.playbackRate = playbackRate;
        }
    }, [playbackRate]);

    // Reset player when file changes
    useEffect(() => {
        setCurrentTime(0);
        setIsPlaying(false);
        if (audioRef.current) {
            audioRef.current.currentTime = 0;
        }
    }, [activeFileIndex]);

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
            audio.currentTime = seconds;
            setCurrentTime(seconds);
        }
    }, []);

    const handleMuteToggle = useCallback(() => {
        const audio = audioRef.current;
        if (audio) {
            audio.muted = !audio.muted;
            setIsMuted(!isMuted);
        }
    }, [isMuted]);

    const handleSegmentClick = useCallback((segment: ParsedSegment) => {
        if (segment.isSpeakerHeader) return;

        // Switch to correct file if needed
        if (segment.fileIndex !== activeFileIndex && segment.fileIndex < mediaSources.length) {
            setActiveFileIndex(segment.fileIndex);
            // Wait for audio to load then seek
            setTimeout(() => {
                handleSeek(segment.startSeconds);
                if (audioRef.current) {
                    audioRef.current.play();
                }
            }, 100);
        } else if (!segment.isFileHeader) {
            handleSeek(segment.startSeconds);
            if (audioRef.current && !isPlaying) {
                audioRef.current.play();
            }
        }
    }, [handleSeek, isPlaying, activeFileIndex, mediaSources.length]);

    const handleFileSelect = useCallback((index: number) => {
        setActiveFileIndex(index);
        setShowFileSelector(false);
    }, []);

    return (
        <div className={cn("flex flex-col h-full", className)}>
            {/* Audio Player */}
            {hasAudio && (
                <div className="flex-shrink-0 border-b bg-muted/30 p-3 space-y-2">
                    <audio ref={audioRef} src={currentMediaUrl} preload="metadata" />

                    {/* File selector for batch mode */}
                    {hasMultipleFiles && (
                        <div className="relative mb-2">
                            <Button
                                variant="outline"
                                size="sm"
                                className="w-full justify-between"
                                onClick={() => setShowFileSelector(!showFileSelector)}
                            >
                                <span className="flex items-center gap-2">
                                    <FileAudio className="h-4 w-4" />
                                    {mediaSources[activeFileIndex]?.name || `Arquivo ${activeFileIndex + 1}`}
                                </span>
                                <ChevronDown className="h-4 w-4" />
                            </Button>

                            {showFileSelector && (
                                <div className="absolute top-full left-0 right-0 mt-1 bg-popover border rounded-md shadow-lg z-10 max-h-48 overflow-y-auto">
                                    {mediaSources.map((file, index) => (
                                        <button
                                            key={index}
                                            className={cn(
                                                "w-full text-left px-3 py-2 text-sm hover:bg-muted",
                                                index === activeFileIndex && "bg-primary/10 text-primary"
                                            )}
                                            onClick={() => handleFileSelect(index)}
                                        >
                                            {file.name || `Arquivo ${index + 1}`}
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    <div className="flex items-center gap-3">
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={handlePlayPause}
                        >
                            {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                        </Button>

                        <div className="flex-1 flex items-center gap-2">
                            <span className="text-xs font-mono text-muted-foreground w-14">
                                {formatTimestamp(currentTime)}
                            </span>
                            <Slider
                                value={[currentTime]}
                                min={0}
                                max={duration || 100}
                                step={1}
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
                            {isMuted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />}
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

            {/* Transcript with highlights */}
            <div
                ref={containerRef}
                className="flex-1 overflow-y-auto p-4 space-y-1"
            >
                {segments.length === 0 ? (
                    <pre className="whitespace-pre-wrap text-sm font-mono text-foreground">
                        {rawContent}
                    </pre>
                ) : (
                    segments.map((segment, index) => {
                        const isCurrentFile = segment.fileIndex === activeFileIndex;
                        const isActive =
                            isCurrentFile &&
                            !segment.isSpeakerHeader &&
                            !segment.isFileHeader &&
                            activeTimestamp !== -1 &&
                            segment.startSeconds === activeTimestamp;

                        if (segment.isFileHeader) {
                            return (
                                <div
                                    key={segment.id}
                                    className={cn(
                                        "font-bold text-base mt-6 mb-3 pb-2 border-b flex items-center gap-2",
                                        isCurrentFile ? "text-primary" : "text-muted-foreground"
                                    )}
                                >
                                    <FileAudio className="h-4 w-4" />
                                    {segment.text}
                                    {hasAudio && segment.fileIndex < mediaSources.length && (
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            className="ml-auto h-6 text-xs"
                                            onClick={() => handleFileSelect(segment.fileIndex)}
                                        >
                                            Reproduzir
                                        </Button>
                                    )}
                                </div>
                            );
                        }

                        if (segment.isSpeakerHeader) {
                            return (
                                <div
                                    key={segment.id}
                                    className={cn(
                                        "font-semibold text-sm mt-4 mb-2",
                                        isCurrentFile ? "text-primary" : "text-muted-foreground"
                                    )}
                                >
                                    {segment.text.replace(/\*\*/g, '')}
                                </div>
                            );
                        }

                        return (
                            <div
                                key={segment.id}
                                ref={isActive ? activeSegmentRef : null}
                                onClick={() => handleSegmentClick(segment)}
                                className={cn(
                                    "flex gap-2 py-1 px-2 rounded-md transition-colors text-sm",
                                    hasAudio && "cursor-pointer hover:bg-muted/50",
                                    isActive && "bg-primary/10 border-l-2 border-primary",
                                    !isCurrentFile && "opacity-60"
                                )}
                            >
                                {hasAudio && (
                                    <span className="font-mono text-xs text-muted-foreground flex-shrink-0 w-14">
                                        [{formatTimestamp(segment.startSeconds)}]
                                    </span>
                                )}
                                <span className="text-foreground">{segment.text}</span>
                            </div>
                        );
                    })
                )}
            </div>
        </div>
    );
}
