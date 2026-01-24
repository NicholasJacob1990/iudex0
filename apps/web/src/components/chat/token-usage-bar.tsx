import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

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

interface TokenUsageBarProps {
    data: TokenTelemetry;
    compact?: boolean;
}

export function TokenUsageBar({ data, compact = false }: TokenUsageBarProps) {
    if (!data?.usage || !data?.limits) return null;

    const { percent_used } = data.limits;
    const { total_tokens } = data.usage;
    const context_window = data.limits.context_window;

    // Cor baseada no uso
    let colorClass = "bg-green-500";
    if (percent_used > 90) colorClass = "bg-red-500";
    else if (percent_used > 75) colorClass = "bg-yellow-500";

    return (
        <div className={cn("flex flex-col gap-1 w-full max-w-md", compact ? "text-[11px]" : "text-xs")}>
            <div className="flex justify-between items-center text-muted-foreground">
                <span>Contexto ({data.model})</span>
                <span className={percent_used > 90 ? "text-red-500 font-bold" : ""}>
                    {total_tokens.toLocaleString()} / {context_window.toLocaleString()} ({percent_used.toFixed(1)}%)
                </span>
            </div>

            <div className="h-2 w-full bg-secondary rounded-full overflow-hidden">
                <div
                    className={cn("h-full transition-all duration-500", colorClass)}
                    style={{ width: `${Math.min(percent_used, 100)}%` }}
                />
            </div>

            {!compact && (
                <div className="flex gap-4 text-[10px] text-muted-foreground/70">
                    <span>Input: {data.usage.input_tokens.toLocaleString()}</span>
                    <span>Output: {data.usage.output_tokens.toLocaleString()}</span>
                </div>
            )}
        </div>
    );
}
