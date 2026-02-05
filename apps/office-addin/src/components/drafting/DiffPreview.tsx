import { useMemo } from 'react';

interface DiffPreviewProps {
  original: string;
  edited: string;
}

interface DiffSegment {
  type: 'equal' | 'insert' | 'delete';
  text: string;
}

/**
 * Componente de diff visual word-by-word entre texto original e editado.
 * Mostra delecoes em vermelho riscado e insercoes em verde.
 */
export function DiffPreview({ original, edited }: DiffPreviewProps) {
  const segments = useMemo(() => computeWordDiff(original, edited), [original, edited]);

  if (!original && !edited) return null;

  const stats = useMemo(() => {
    const added = segments.filter((s) => s.type === 'insert').length;
    const removed = segments.filter((s) => s.type === 'delete').length;
    const unchanged = segments.filter((s) => s.type === 'equal').length;
    return { added, removed, unchanged };
  }, [segments]);

  return (
    <div className="space-y-2">
      {/* Stats */}
      <div className="flex gap-3 text-office-xs">
        {stats.removed > 0 && (
          <span className="text-status-error">-{stats.removed} removidos</span>
        )}
        {stats.added > 0 && (
          <span className="text-status-success">+{stats.added} adicionados</span>
        )}
        <span className="text-text-tertiary">{stats.unchanged} inalterados</span>
      </div>

      {/* Diff view */}
      <div className="rounded border border-gray-200 bg-white p-3 text-office-sm leading-relaxed">
        {segments.map((seg, i) => {
          if (seg.type === 'delete') {
            return (
              <span
                key={i}
                className="bg-red-100 text-status-error line-through"
              >
                {seg.text}
              </span>
            );
          }
          if (seg.type === 'insert') {
            return (
              <span key={i} className="bg-green-100 text-green-800">
                {seg.text}
              </span>
            );
          }
          return <span key={i}>{seg.text}</span>;
        })}
      </div>
    </div>
  );
}

/**
 * Side-by-side diff: original a esquerda, editado a direita.
 */
export function SideBySideDiff({
  original,
  edited,
}: DiffPreviewProps) {
  return (
    <div className="grid grid-cols-2 gap-2">
      <div>
        <p className="mb-1 text-office-xs font-medium text-status-error">Original</p>
        <div className="rounded border border-red-200 bg-red-50 p-2 text-office-xs leading-relaxed text-red-900">
          {original}
        </div>
      </div>
      <div>
        <p className="mb-1 text-office-xs font-medium text-status-success">Editado</p>
        <div className="rounded border border-green-200 bg-green-50 p-2 text-office-xs leading-relaxed text-green-900">
          {edited}
        </div>
      </div>
    </div>
  );
}

// ── Word-level diff algorithm ──────────────────────────────────

function computeWordDiff(original: string, edited: string): DiffSegment[] {
  const wordsA = tokenize(original);
  const wordsB = tokenize(edited);

  // LCS-based diff
  const lcs = computeLCS(wordsA, wordsB);
  const segments: DiffSegment[] = [];

  let idxA = 0;
  let idxB = 0;

  for (const [lcsIdxA, lcsIdxB] of lcs) {
    // Deleted words (in A but not in LCS match)
    if (idxA < lcsIdxA) {
      segments.push({
        type: 'delete',
        text: wordsA.slice(idxA, lcsIdxA).join(''),
      });
    }

    // Inserted words (in B but not in LCS match)
    if (idxB < lcsIdxB) {
      segments.push({
        type: 'insert',
        text: wordsB.slice(idxB, lcsIdxB).join(''),
      });
    }

    // Equal word
    segments.push({
      type: 'equal',
      text: wordsA[lcsIdxA],
    });

    idxA = lcsIdxA + 1;
    idxB = lcsIdxB + 1;
  }

  // Remaining deleted
  if (idxA < wordsA.length) {
    segments.push({
      type: 'delete',
      text: wordsA.slice(idxA).join(''),
    });
  }

  // Remaining inserted
  if (idxB < wordsB.length) {
    segments.push({
      type: 'insert',
      text: wordsB.slice(idxB).join(''),
    });
  }

  return mergeSegments(segments);
}

/** Tokenize preservando espacos como parte dos tokens */
function tokenize(text: string): string[] {
  return text.match(/\S+\s*/g) || [];
}

/** LCS com limite de tamanho para performance */
function computeLCS(a: string[], b: string[]): Array<[number, number]> {
  const MAX = 500;
  const trimmedA = a.slice(0, MAX);
  const trimmedB = b.slice(0, MAX);

  const m = trimmedA.length;
  const n = trimmedB.length;

  // DP table (space-optimized: two rows)
  const prev = new Array(n + 1).fill(0);
  const curr = new Array(n + 1).fill(0);

  // Build LCS length table
  const dp: number[][] = [];
  for (let i = 0; i <= m; i++) {
    dp[i] = new Array(n + 1).fill(0);
  }

  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (trimmedA[i - 1] === trimmedB[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1] + 1;
      } else {
        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
      }
    }
  }

  // Backtrack to find LCS indices
  const result: Array<[number, number]> = [];
  let i = m;
  let j = n;

  while (i > 0 && j > 0) {
    if (trimmedA[i - 1] === trimmedB[j - 1]) {
      result.unshift([i - 1, j - 1]);
      i--;
      j--;
    } else if (dp[i - 1][j] > dp[i][j - 1]) {
      i--;
    } else {
      j--;
    }
  }

  return result;
}

/** Merge consecutive segments of the same type */
function mergeSegments(segments: DiffSegment[]): DiffSegment[] {
  if (segments.length === 0) return [];

  const merged: DiffSegment[] = [segments[0]];

  for (let i = 1; i < segments.length; i++) {
    const last = merged[merged.length - 1];
    if (last.type === segments[i].type) {
      last.text += segments[i].text;
    } else {
      merged.push({ ...segments[i] });
    }
  }

  return merged;
}
