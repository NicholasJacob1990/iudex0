'use client';

import { cn } from '@/lib/utils';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

interface TokenTelemetry {
    provider: string;
    model: string;
    usage: {
        input_tokens: number;
        output_tokens: number;
        total_tokens: number;
    };
    limits: {
        context_window: number;
        percent_used: number;
    };
}

interface TokenUsageCircleProps {
    data: TokenTelemetry;
    size?: 'sm' | 'md';
    showLabel?: boolean;
}

export function TokenUsageCircle({ data, size = 'sm', showLabel = true }: TokenUsageCircleProps) {
    if (!data?.usage || !data?.limits) return null;

    const { percent_used } = data.limits;
    const { total_tokens, input_tokens, output_tokens } = data.usage;

    // Size config
    const sizeConfig = size === 'sm'
        ? { container: 'h-6 w-6', stroke: 3, radius: 9, textSize: 'text-[8px]' }
        : { container: 'h-8 w-8', stroke: 3.5, radius: 12, textSize: 'text-[10px]' };

    const circumference = 2 * Math.PI * sizeConfig.radius;
    const strokeDashoffset = circumference - (Math.min(percent_used, 100) / 100) * circumference;

    // Color based on usage
    let colorClass = 'text-emerald-500';
    let bgClass = 'text-emerald-100';
    if (percent_used > 90) {
        colorClass = 'text-red-500';
        bgClass = 'text-red-100';
    } else if (percent_used > 75) {
        colorClass = 'text-amber-500';
        bgClass = 'text-amber-100';
    }

    const formatNumber = (n: number) => {
        if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
        if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
        return n.toString();
    };

    return (
        <TooltipProvider>
            <Tooltip>
                <TooltipTrigger asChild>
                    <div className="flex items-center gap-1.5 cursor-help">
                        {/* Circular Progress */}
                        <div className={cn('relative', sizeConfig.container)}>
                            <svg className="transform -rotate-90 w-full h-full" viewBox="0 0 24 24">
                                {/* Background circle */}
                                <circle
                                    cx="12"
                                    cy="12"
                                    r={sizeConfig.radius}
                                    stroke="currentColor"
                                    strokeWidth={sizeConfig.stroke}
                                    fill="none"
                                    className={bgClass}
                                />
                                {/* Progress circle */}
                                <circle
                                    cx="12"
                                    cy="12"
                                    r={sizeConfig.radius}
                                    stroke="currentColor"
                                    strokeWidth={sizeConfig.stroke}
                                    fill="none"
                                    strokeLinecap="round"
                                    className={colorClass}
                                    style={{
                                        strokeDasharray: circumference,
                                        strokeDashoffset,
                                        transition: 'stroke-dashoffset 0.5s ease',
                                    }}
                                />
                            </svg>
                            {/* Center text */}
                            <div className={cn(
                                'absolute inset-0 flex items-center justify-center font-bold',
                                sizeConfig.textSize,
                                colorClass
                            )}>
                                {Math.round(percent_used)}%
                            </div>
                        </div>

                        {/* Label */}
                        {showLabel && (
                            <span className="text-xs text-muted-foreground">
                                {formatNumber(total_tokens)}
                            </span>
                        )}
                    </div>
                </TooltipTrigger>
                <TooltipContent side="bottom" className="text-xs">
                    <div className="space-y-1">
                        <div className="font-semibold">{data.model}</div>
                        <div className="flex justify-between gap-4">
                            <span className="text-muted-foreground">Input:</span>
                            <span>{input_tokens.toLocaleString()}</span>
                        </div>
                        <div className="flex justify-between gap-4">
                            <span className="text-muted-foreground">Output:</span>
                            <span>{output_tokens.toLocaleString()}</span>
                        </div>
                        <div className="flex justify-between gap-4 border-t pt-1">
                            <span className="text-muted-foreground">Total:</span>
                            <span className="font-medium">{total_tokens.toLocaleString()}</span>
                        </div>
                        <div className="flex justify-between gap-4">
                            <span className="text-muted-foreground">Janela:</span>
                            <span>{data.limits.context_window.toLocaleString()}</span>
                        </div>
                    </div>
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    );
}
