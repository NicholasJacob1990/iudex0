// Lightweight JS fallback for ws optional native dependency.
export function mask(source: Buffer, maskBuf: Buffer, output: Buffer, offset: number, length: number): void {
  for (let i = 0; i < length; i += 1) {
    output[offset + i] = source[i] ^ maskBuf[i & 3];
  }
}

export function unmask(buffer: Buffer, maskBuf: Buffer): void {
  for (let i = 0; i < buffer.length; i += 1) {
    buffer[i] ^= maskBuf[i & 3];
  }
}

const bufferutil = { mask, unmask };
export default bufferutil;
