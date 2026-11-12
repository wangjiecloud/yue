export class PackError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'PackError';
  }
}

export function nowIso(): string {
  return new Date().toISOString();
}

export function uuid(): string {
  let out = '';
  for (let i = 0; i < 32; i += 1) {
    const n = Math.floor(Math.random() * 16);
    if (i === 12) out += '4';
    else if (i === 16) out += ((n & 3) | 8).toString(16);
    else out += n.toString(16);
    if (i === 7 || i === 11 || i === 15 || i === 19) out += '';
  }
  return out;
}

export function compareVersions(a: string, b: string): number {
  const pa = a.split('.').map((n) => Number.parseInt(n, 10) || 0);
  const pb = b.split('.').map((n) => Number.parseInt(n, 10) || 0);
  for (let i = 0; i < Math.max(pa.length, pb.length); i += 1) {
    const diff = (pa[i] || 0) - (pb[i] || 0);
    if (diff !== 0) return diff > 0 ? 1 : -1;
  }
  return 0;
}

export function isSafeId(value: unknown): value is string {
  return typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(value);
}
