import { Directory, File, Paths } from 'expo-file-system';
import { sha256 } from 'js-sha256';

import type { Course, Manifest } from '../types';
import * as db from './db';
import { RestrictedZipReader, decodeUtf8 } from './zip';
import { isSafeId, nowIso, PackError, uuid } from './util';
import { validateCourse, validateManifest } from './validate';

const MIN_FREE_HEADROOM_BYTES = 50 * 1024 * 1024;

export function appVersion(): string {
  return '0.1.0';
}

export function coursesRoot(): Directory {
  return new Directory(Paths.document, 'courses');
}

export function courseDir(dirName: string): Directory {
  return new Directory(coursesRoot(), dirName);
}

export interface InstalledCourse {
  row: db.CourseRow;
  manifest: Manifest;
  course: Course;
}

export interface ImportResult {
  status: 'installed' | 'duplicate';
  packageId: string;
  courseId: string;
  revision: number;
}

function fileFromParts(base: Directory, relative: string): File {
  return new File(base, ...relative.split('/'));
}

async function parseJsonFile<T>(file: File): Promise<T> {
  const text = await file.text();
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new PackError('课程包内 JSON 文件格式错误');
  }
}

export async function importPack(sourceUri: string, isDemo = false): Promise<ImportResult> {
  const source = new File(sourceUri);
  if (!source.exists) {
    throw new PackError('课程包文件不存在或无法读取');
  }
  const reader = await RestrictedZipReader.open(source);
  const tempDir = new Directory(Paths.cache, `pack-import-${uuid()}`);
  try {
    const totalUncompressed = reader.entries.reduce((sum, entry) => sum + entry.uncompressedSize, 0);
    if (Paths.availableDiskSpace < totalUncompressed * 1.2 + MIN_FREE_HEADROOM_BYTES) {
      throw new PackError('设备可用存储空间不足，无法导入该课程包');
    }

    const checksumsBytes = await reader.extractBytes(reader.findEntry('checksums.json'));
    let checksums: { algorithm?: string; files?: Record<string, string> };
    try {
      checksums = JSON.parse(decodeUtf8(checksumsBytes));
    } catch {
      throw new PackError('checksums.json 格式错误');
    }
    if (checksums.algorithm !== 'sha256' || typeof checksums.files !== 'object' || checksums.files === null) {
      throw new PackError('checksums.json 缺少 sha256 文件清单');
    }
    const declaredFiles = checksums.files;
    const entryNames = new Set(reader.entries.map((entry) => entry.name));
    for (const entry of reader.entries) {
      if (entry.name !== 'checksums.json' && !(entry.name in declaredFiles)) {
        throw new PackError(`文件缺少校验和声明: ${entry.name}`);
      }
    }
    for (const name of Object.keys(declaredFiles)) {
      if (!entryNames.has(name)) {
        throw new PackError(`校验和声明了不存在的文件: ${name}`);
      }
    }

    tempDir.create({ intermediates: true, overwrite: true });

    let manifest: Manifest | null = null;
    let course: Course | null = null;
    for (const entry of reader.entries) {
      const expectedSha = entry.name === 'checksums.json' ? null : declaredFiles[entry.name];
      const destination = fileFromParts(tempDir, entry.name);
      const parent = destination.parentDirectory;
      if (parent instanceof Directory) {
        parent.create({ intermediates: true, idempotent: true });
      }
      if (entry.name === 'checksums.json') {
        destination.writeSync(checksumsBytes);
      } else if (entry.name === 'manifest.json' || entry.name === 'courses/course.json') {
        const bytes = await reader.extractBytes(entry);
        const digest = sha256(bytes);
        if (digest !== expectedSha) {
          throw new PackError(`文件校验失败（SHA-256 不匹配）: ${entry.name}`);
        }
        destination.writeSync(bytes);
        if (entry.name === 'manifest.json') {
          manifest = JSON.parse(decodeUtf8(bytes)) as Manifest;
        } else {
          course = JSON.parse(decodeUtf8(bytes)) as Course;
        }
      } else {
        await reader.extractToFile(entry, destination, expectedSha as string);
      }
    }
    if (!manifest || !course) {
      throw new PackError('课程包缺少 manifest 或课程定义');
    }
    validateManifest(manifest, appVersion());
    validateCourse(course, manifest);

    const assetByPath = new Map(manifest.assets.map((asset) => [asset.path, asset]));
    for (const entry of reader.entries) {
      if (entry.name === 'checksums.json') continue;
      const asset = assetByPath.get(entry.name);
      if (asset) {
        if (asset.bytes !== entry.uncompressedSize) {
          throw new PackError(`manifest 资源大小与实际不一致: ${entry.name}`);
        }
        if (asset.sha256 !== declaredFiles[entry.name]) {
          throw new PackError(`manifest 与 checksums 的校验和不一致: ${entry.name}`);
        }
        assetByPath.delete(entry.name);
      }
    }
    if (assetByPath.size > 0) {
      throw new PackError(`manifest 声明的资源在包内缺失: ${[...assetByPath.keys()].join(', ')}`);
    }
    if (!isSafeId(manifest.packageId)) {
      throw new PackError('packageId 含有不允许的字符');
    }

    const manifestSha = sha256(JSON.stringify(manifest));
    const existing = await db.findCourseRow(manifest.packageId);
    if (existing) {
      return {
        status: 'duplicate',
        packageId: existing.packageId,
        courseId: existing.courseId,
        revision: existing.revision,
      };
    }
    const sameIdentity = await db.findCourseRowByIdentity(manifest.courseId, manifest.revision);
    if (sameIdentity) {
      if (sameIdentity.manifestSha !== manifestSha) {
        throw new PackError('同一课程版本的内容不同，请发布新的 revision 后重新导入');
      }
      return {
        status: 'duplicate',
        packageId: sameIdentity.packageId,
        courseId: sameIdentity.courseId,
        revision: sameIdentity.revision,
      };
    }

    const targetDir = courseDir(manifest.packageId);
    if (targetDir.exists) {
      targetDir.delete();
    }
    const marker = new File(tempDir, 'install.json');
    marker.writeSync(
      JSON.stringify({
        packageId: manifest.packageId,
        courseId: manifest.courseId,
        revision: manifest.revision,
        installedAt: nowIso(),
      }),
    );
    coursesRoot().create({ intermediates: true, idempotent: true });
    await tempDir.move(targetDir);

    try {
      await db.insertCourseRow({
        packageId: manifest.packageId,
        courseId: manifest.courseId,
        revision: manifest.revision,
        title: course.lessons[0]?.title ?? manifest.courseId,
        courseMode: manifest.courseMode,
        grade: course.grade ?? null,
        subject: course.subject ?? null,
        dirName: manifest.packageId,
        manifestSha,
        isDemo: isDemo ? 1 : 0,
        installedAt: nowIso(),
      });
    } catch (error) {
      if (targetDir.exists) {
        targetDir.delete();
      }
      throw error;
    }
    return {
      status: 'installed',
      packageId: manifest.packageId,
      courseId: manifest.courseId,
      revision: manifest.revision,
    };
  } finally {
    reader.close();
    if (tempDir.exists) {
      tempDir.delete();
    }
  }
}

export async function loadInstalledCourse(packageId: string): Promise<InstalledCourse> {
  const row = await db.findCourseRow(packageId);
  if (!row) {
    throw new PackError(`课程未安装: ${packageId}`);
  }
  const dir = courseDir(row.dirName);
  if (!dir.exists) {
    throw new PackError(`课程数据缺失: ${packageId}`);
  }
  const manifest = await parseJsonFile<Manifest>(fileFromParts(dir, 'manifest.json'));
  const course = await parseJsonFile<Course>(fileFromParts(dir, 'courses/course.json'));
  return { row, manifest, course };
}

export async function listInstalledCourses(): Promise<InstalledCourse[]> {
  const rows = await db.listCourseRows();
  const installed: InstalledCourse[] = [];
  for (const row of rows) {
    try {
      installed.push(await loadInstalledCourse(row.packageId));
    } catch {
      // Skip broken course directories; the parent zone reports them.
    }
  }
  return installed;
}

export function assetFile(installed: InstalledCourse, assetId: string): File {
  const asset = installed.manifest.assets.find((candidate) => candidate.assetId === assetId);
  if (!asset) {
    throw new PackError(`课程资源不存在: ${assetId}`);
  }
  return fileFromParts(courseDir(installed.row.dirName), asset.path);
}

export function assetUri(installed: InstalledCourse, assetId: string): string {
  return assetFile(installed, assetId).uri;
}

export async function uninstallCourse(packageId: string, alsoRecords: boolean): Promise<void> {
  const row = await db.findCourseRow(packageId);
  if (!row) {
    throw new PackError(`课程未安装: ${packageId}`);
  }
  const dir = courseDir(row.dirName);
  if (dir.exists) {
    dir.delete();
  }
  await db.deleteCourseRow(packageId, alsoRecords);
}

export function cleanupInterruptedImports(): void {
  const cache = Paths.cache;
  if (!cache.exists) return;
  for (const entry of cache.list()) {
    if (entry instanceof Directory && entry.name.startsWith('pack-import-')) {
      entry.delete();
    }
  }
}

export function sweepOrphanCourseDirs(): void {
  void (async () => {
    try {
      const rows = await db.listCourseRows();
      const known = new Set(rows.map((row) => row.dirName));
      const root = coursesRoot();
      if (!root.exists) return;
      for (const entry of root.list()) {
        if (entry instanceof Directory && !known.has(entry.name)) {
          entry.delete();
        }
      }
    } catch {
      // Best effort startup cleanup.
    }
  })();
}
