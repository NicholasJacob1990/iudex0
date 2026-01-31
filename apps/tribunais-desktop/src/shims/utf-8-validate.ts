// Lightweight JS fallback for ws optional native dependency.
export function isValidUTF8(buffer: Buffer): boolean {
  try {
    // TextDecoder exists in Node 18+ (Electron 28).
    const decoder = new TextDecoder('utf-8', { fatal: true });
    decoder.decode(buffer);
    return true;
  } catch {
    return false;
  }
}

export default isValidUTF8;
