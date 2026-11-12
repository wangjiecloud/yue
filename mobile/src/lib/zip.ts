import { File, FileMode } from 'expo-file-system';
import { sha256 } from 'js-sha256';
import { Inflate } from 'pako';

import { PackError } from './util';

export const PACK_LIMITS = {
  maxPackageBytes: 300 * 1024 * 1024,
  maxEntries: 512,
  maxEntryUncompressedBytes: 256 * 1024 * 1024,
  maxTotalUncompressedBytes: 1024 * 1024 * 1024,
  maxCompressionRatio: 200,
  maxPathLength: 240,
  maxCentralDirectoryBytes: 4 * 1024 * 1024,
  readChunkBytes: 1024 * 1024,
} as const;

export const ALLOWED_SUFFIXES = new Set([
  '.json',
  '.mp4',
  '.m4a',
  '.wav',
  '.aac',
  '.mp3',
  '.srt',
  '.jpg',
  '.jpeg',
  '.png',
  '.webp',
]);

export const ALLOWED_ROOTS = new Set([
  'manifest.json',
  'courses',
  'assets',
  'checksums.json',
]);

const EOCD_SIGNATURE = 0x06054b50;
const ZIP64_LOCATOR_SIGNATURE = 0x07064b50;
const CENTRAL_SIGNATURE = 0x02014b50;
const LOCAL_SIGNATURE = 0x04034b50;

export interface ZipEntry {
  name: string;
  compressedSize: number;
  uncompressedSize: number;
  method: number;
  flags: number;
  crc32: number;
  localHeaderOffset: number;
}

function dataView(bytes: Uint8Array): DataView {
  return new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
}

function isAscii(bytes: Uint8Array): boolean {
  for (const byte of bytes) {
    if (byte > 0x7f) return false;
  }
  return true;
}

function bytesEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

export function checkEntryName(name: string): string {
  if (!name || name.length > PACK_LIMITS.maxPathLength) {
    throw new PackError(`无效或超长的文件路径: ${name}`);
  }
  if (name.startsWith('/') || name.startsWith('\\')) {
    throw new PackError(`禁止绝对路径: ${name}`);
  }
  if (name.includes('\\')) {
    throw new PackError(`禁止反斜杠路径: ${name}`);
  }
  const parts = name.split('/');
  if (parts.some((part) => part === '' || part === '.' || part === '..')) {
    throw new PackError(`禁止路径穿越: ${name}`);
  }
  if (!ALLOWED_ROOTS.has(parts[0])) {
    throw new PackError(`不允许的包内顶层路径: ${name}`);
  }
  const lower = name.toLowerCase();
  const suffix = lower.slice(lower.lastIndexOf('.'));
  if (!ALLOWED_SUFFIXES.has(suffix)) {
    throw new PackError(`不允许的文件类型: ${name}`);
  }
  return name;
}

export class RestrictedZipReader {
  private handle: import('expo-file-system').FileHandle;
  readonly file: File;
  readonly fileSize: number;
  readonly entries: ZipEntry[] = [];

  private constructor(file: File, handle: import('expo-file-system').FileHandle) {
    this.file = file;
    this.handle = handle;
    this.fileSize = file.size ?? 0;
  }

  static async open(file: File): Promise<RestrictedZipReader> {
    if (!file.exists) {
      throw new PackError('课程包文件不存在');
    }
    const fileSize = file.size ?? 0;
    if (fileSize < 22) {
      throw new PackError('文件不是有效的课程包');
    }
    if (fileSize > PACK_LIMITS.maxPackageBytes) {
      throw new PackError('课程包超过大小限制');
    }
    const handle = file.open(FileMode.ReadOnly);
    const reader = new RestrictedZipReader(file, handle);
    await reader.parseCentralDirectory();
    return reader;
  }

  close(): void {
    try {
      this.handle.close();
    } catch {
      // best effort during cleanup
    }
  }

  async readRange(offset: number, length: number): Promise<Uint8Array> {
    this.handle.offset = offset;
    const bytes = await this.handle.readBytes(length);
    if (bytes.length !== length) {
      throw new PackError('课程包数据不完整（读取越界）');
    }
    return bytes;
  }

  private async parseCentralDirectory(): Promise<void> {
    const tailLength = Math.min(this.fileSize, 22 + 65535 + 64);
    const tail = await this.readRange(this.fileSize - tailLength, tailLength);
    let eocdOffset = -1;
    for (let i = tail.length - 22; i >= 0; i -= 1) {
      const view = dataView(tail);
      if (view.getUint32(i, true) === EOCD_SIGNATURE) {
        eocdOffset = i;
        break;
      }
    }
    if (eocdOffset < 0) {
      throw new PackError('文件不是有效的课程包（缺少 ZIP 目录）');
    }
    for (let i = tail.length - 20; i >= 0; i -= 1) {
      if (dataView(tail).getUint32(i, true) === ZIP64_LOCATOR_SIGNATURE) {
        throw new PackError('课程包使用了不支持的 ZIP64 格式');
      }
    }
    const view = dataView(tail);
    const diskNumber = view.getUint16(eocdOffset + 4, true);
    const entryCount = view.getUint16(eocdOffset + 10, true);
    const directorySize = view.getUint32(eocdOffset + 12, true);
    const directoryOffset = view.getUint32(eocdOffset + 16, true);
    if (diskNumber !== 0) {
      throw new PackError('不支持多磁盘课程包');
    }
    if (entryCount === 0xffff || directorySize === 0xffffffff || directoryOffset === 0xffffffff) {
      throw new PackError('课程包使用了不支持的 ZIP64 格式');
    }
    if (entryCount > PACK_LIMITS.maxEntries) {
      throw new PackError('课程包内文件数量超过限制');
    }
    if (directorySize > PACK_LIMITS.maxCentralDirectoryBytes) {
      throw new PackError('课程包目录过大');
    }
    if (directoryOffset + directorySize > this.fileSize) {
      throw new PackError('课程包目录越界，文件已损坏');
    }

    let totalUncompressed = 0;
    const seen = new Set<string>();
    const directory = await this.readRange(directoryOffset, directorySize);
    const directoryView = dataView(directory);
    let cursor = 0;
    for (let index = 0; index < entryCount; index += 1) {
      if (cursor + 46 > directory.length || directoryView.getUint32(cursor, true) !== CENTRAL_SIGNATURE) {
        throw new PackError('课程包目录损坏');
      }
      const versionMadeBy = directoryView.getUint16(cursor + 4, true);
      const flags = directoryView.getUint16(cursor + 8, true);
      const method = directoryView.getUint16(cursor + 10, true);
      const crc32 = directoryView.getUint32(cursor + 16, true);
      const compressedSize = directoryView.getUint32(cursor + 20, true);
      const uncompressedSize = directoryView.getUint32(cursor + 24, true);
      const nameLength = directoryView.getUint16(cursor + 28, true);
      const extraLength = directoryView.getUint16(cursor + 30, true);
      const commentLength = directoryView.getUint16(cursor + 32, true);
      const externalAttrs = directoryView.getUint32(cursor + 38, true);
      const localHeaderOffset = directoryView.getUint32(cursor + 42, true);
      if (cursor + 46 + nameLength + extraLength + commentLength > directory.length) {
        throw new PackError('课程包目录损坏');
      }
      const nameBytes = directory.subarray(cursor + 46, cursor + 46 + nameLength);
      if (!isAscii(nameBytes)) {
        throw new PackError('包内文件名仅支持 ASCII 字符');
      }
      const name = String.fromCharCode(...nameBytes);
      checkEntryName(name);
      if (seen.has(name)) {
        throw new PackError(`重复的包内路径: ${name}`);
      }
      seen.add(name);
      if ((flags & 0x1) !== 0) {
        throw new PackError(`不支持加密条目: ${name}`);
      }
      if ((flags & 0x8) !== 0) {
        throw new PackError(`不支持依赖数据描述符的条目: ${name}`);
      }
      if (method !== 0 && method !== 8) {
        throw new PackError(`不支持的压缩方式: ${name}`);
      }
      const unixMode = externalAttrs >>> 16;
      if (versionMadeBy >>> 8 === 3 && (unixMode & 0xf000) === 0xa000) {
        throw new PackError(`禁止符号链接条目: ${name}`);
      }
      if (uncompressedSize === 0 || compressedSize === 0) {
        throw new PackError(`无效的条目大小: ${name}`);
      }
      if (uncompressedSize > PACK_LIMITS.maxEntryUncompressedBytes) {
        throw new PackError(`文件超过单文件大小限制: ${name}`);
      }
      if (compressedSize > uncompressedSize) {
        throw new PackError(`压缩数据大于原始数据，包已损坏: ${name}`);
      }
      if (uncompressedSize / compressedSize > PACK_LIMITS.maxCompressionRatio) {
        throw new PackError(`可疑的压缩比，可能为压缩炸弹: ${name}`);
      }
      if (localHeaderOffset + 30 > this.fileSize) {
        throw new PackError(`条目本地头越界: ${name}`);
      }
      totalUncompressed += uncompressedSize;
      if (totalUncompressed > PACK_LIMITS.maxTotalUncompressedBytes) {
        throw new PackError('课程包展开后超过总大小限制');
      }
      this.entries.push({
        name,
        compressedSize,
        uncompressedSize,
        method,
        flags,
        crc32,
        localHeaderOffset,
      });
      cursor += 46 + nameLength + extraLength + commentLength;
    }
    for (const required of ['manifest.json', 'courses/course.json', 'checksums.json']) {
      if (!seen.has(required)) {
        throw new PackError(`课程包缺少必需文件: ${required}`);
      }
    }
  }

  findEntry(name: string): ZipEntry {
    const entry = this.entries.find((candidate) => candidate.name === name);
    if (!entry) {
      throw new PackError(`课程包缺少文件: ${name}`);
    }
    return entry;
  }

  async readText(entry: ZipEntry): Promise<string> {
    const bytes = await this.extractBytes(entry);
    let result = '';
    const step = 0x8000;
    for (let i = 0; i < bytes.length; i += step) {
      result += String.fromCharCode(...bytes.subarray(i, i + step));
    }
    return decodeUtf8(result);
  }

  async extractBytes(entry: ZipEntry): Promise<Uint8Array> {
    const chunks: Uint8Array[] = [];
    let written = 0;
    await this.inflateEntry(entry, (chunk) => {
      chunks.push(chunk);
      written += chunk.length;
    });
    const out = new Uint8Array(written);
    let offset = 0;
    for (const chunk of chunks) {
      out.set(chunk, offset);
      offset += chunk.length;
    }
    return out;
  }

  async extractToFile(entry: ZipEntry, destination: File, expectedSha256: string): Promise<void> {
    const digest = sha256.create();
    await this.inflateEntry(entry, (chunk) => {
      digest.update(chunk as unknown as string);
      destination.writeSync(chunk, { append: true });
    });
    if (digest.hex() !== expectedSha256) {
      throw new PackError(`文件校验失败（SHA-256 不匹配）: ${entry.name}`);
    }
  }

  private async inflateEntry(
    entry: ZipEntry,
    onChunk: (chunk: Uint8Array) => void,
  ): Promise<void> {
    const header = await this.readRange(entry.localHeaderOffset, 30);
    const headerView = dataView(header);
    if (headerView.getUint32(0, true) !== LOCAL_SIGNATURE) {
      throw new PackError(`条目本地头损坏: ${entry.name}`);
    }
    const localFlags = headerView.getUint16(6, true);
    const localMethod = headerView.getUint16(8, true);
    const localCompressed = headerView.getUint32(18, true);
    const localUncompressed = headerView.getUint32(22, true);
    const nameLength = headerView.getUint16(26, true);
    const extraLength = headerView.getUint16(28, true);
    if (localFlags !== entry.flags || localMethod !== entry.method) {
      throw new PackError(`条目本地头与目录不一致: ${entry.name}`);
    }
    if ((localFlags & 0x8) === 0) {
      if (localCompressed !== entry.compressedSize || localUncompressed !== entry.uncompressedSize) {
        throw new PackError(`条目本地头大小与目录不一致: ${entry.name}`);
      }
    }
    const localName = await this.readRange(entry.localHeaderOffset + 30, nameLength);
    const centralNameBytes = new Uint8Array(entry.name.length);
    for (let i = 0; i < entry.name.length; i += 1) {
      centralNameBytes[i] = entry.name.charCodeAt(i);
    }
    if (!bytesEqual(localName, centralNameBytes)) {
      throw new PackError(`条目名称与目录不一致: ${entry.name}`);
    }

    const dataOffset = entry.localHeaderOffset + 30 + nameLength + extraLength;
    let written = 0;
    const fail = (message: string): never => {
      throw new PackError(`${message}: ${entry.name}`);
    };

    if (entry.method === 0) {
      let remaining = entry.compressedSize;
      this.handle.offset = dataOffset;
      while (remaining > 0) {
        const take = Math.min(remaining, PACK_LIMITS.readChunkBytes);
        const chunk = await this.handle.readBytes(take);
        if (chunk.length !== take) {
          fail('数据不完整');
        }
        written += chunk.length;
        if (written > entry.uncompressedSize) {
          fail('展开数据超过声明大小');
        }
        onChunk(chunk);
        remaining -= take;
      }
    } else {
      const inflate = new Inflate({ raw: true, chunkSize: 256 * 1024 });
      let aborted: string | null = null;
      inflate.onData = (chunk: Uint8Array) => {
        if (aborted) return;
        written += chunk.length;
        if (written > entry.uncompressedSize) {
          aborted = '展开数据超过声明大小';
          return;
        }
        onChunk(chunk);
      };
      let remaining = entry.compressedSize;
      this.handle.offset = dataOffset;
      while (remaining > 0 && !aborted) {
        const take = Math.min(remaining, PACK_LIMITS.readChunkBytes);
        const chunk = await this.handle.readBytes(take);
        if (chunk.length !== take) {
          fail('数据不完整');
        }
        remaining -= take;
        inflate.push(chunk, remaining === 0);
        if (inflate.err !== 0) {
          fail(`解压失败 (${inflate.msg ?? '数据损坏'})`);
        }
      }
      if (aborted) fail(aborted);
    }
    if (written !== entry.uncompressedSize) {
      fail('展开后大小与声明不一致');
    }
  }
}

export function decodeUtf8(bytes: Uint8Array): string {
  let out = '';
  let i = 0;
  while (i < bytes.length) {
    const byte = bytes[i];
    let codePoint: number;
    let extra: number;
    if (byte < 0x80) {
      codePoint = byte;
      extra = 0;
    } else if (byte < 0xc2) {
      throw new PackError('课程包内 JSON 不是有效的 UTF-8');
    } else if (byte < 0xe0) {
      codePoint = byte & 0x1f;
      extra = 1;
    } else if (byte < 0xf0) {
      codePoint = byte & 0x0f;
      extra = 2;
    } else if (byte < 0xf5) {
      codePoint = byte & 0x07;
      extra = 3;
    } else {
      throw new PackError('课程包内 JSON 不是有效的 UTF-8');
    }
    if (i + extra >= bytes.length) {
      throw new PackError('课程包内 JSON 不是有效的 UTF-8');
    }
    for (let j = 1; j <= extra; j += 1) {
      const next = bytes[i + j];
      if ((next & 0xc0) !== 0x80) {
        throw new PackError('课程包内 JSON 不是有效的 UTF-8');
      }
      codePoint = (codePoint << 6) | (next & 0x3f);
    }
    out += String.fromCodePoint(codePoint);
    i += extra + 1;
  }
  return out;
}
