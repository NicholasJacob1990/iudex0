/**
 * Utilities for transforming API responses between snake_case and camelCase
 */

/**
 * Converts a snake_case string to camelCase
 */
export function snakeToCamel(str: string): string {
    return str.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
}

/**
 * Converts a camelCase string to snake_case
 */
export function camelToSnake(str: string): string {
    return str.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);
}

/**
 * Recursively transforms all object keys from snake_case to camelCase
 */
export function transformKeysToCamel<T>(obj: unknown): T {
    if (Array.isArray(obj)) {
        return obj.map(transformKeysToCamel) as T;
    }

    if (obj !== null && typeof obj === 'object' && !(obj instanceof Date)) {
        return Object.fromEntries(
            Object.entries(obj as Record<string, unknown>).map(([key, value]) => [
                snakeToCamel(key),
                transformKeysToCamel(value),
            ])
        ) as T;
    }

    return obj as T;
}

/**
 * Recursively transforms all object keys from camelCase to snake_case
 */
export function transformKeysToSnake<T>(obj: unknown): T {
    if (Array.isArray(obj)) {
        return obj.map(transformKeysToSnake) as T;
    }

    if (obj !== null && typeof obj === 'object' && !(obj instanceof Date)) {
        return Object.fromEntries(
            Object.entries(obj as Record<string, unknown>).map(([key, value]) => [
                camelToSnake(key),
                transformKeysToSnake(value),
            ])
        ) as T;
    }

    return obj as T;
}

/**
 * Parses an ISO date string to a Date object
 * Returns null for invalid dates
 */
export function parseDate(dateStr: string | null | undefined): Date | null {
    if (!dateStr) return null;
    const date = new Date(dateStr);
    return isNaN(date.getTime()) ? null : date;
}
