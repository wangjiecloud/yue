import { File, Paths } from 'expo-file-system';
import type { SQLiteBindValue } from 'expo-sqlite';
import * as Sharing from 'expo-sharing';

import * as db from './db';
import { nowIso, PackError } from './util';

export interface BackupPayload {
  schemaVersion: 1;
  exportedAt: string;
  attempts: unknown[];
  completions: unknown[];
  rewardEvents: unknown[];
  reviewQueue: unknown[];
  activeTime: unknown[];
}

export async function exportBackup(): Promise<File> {
  const database = await db.getDb();
  const payload: BackupPayload = {
    schemaVersion: 1,
    exportedAt: nowIso(),
    attempts: await database.getAllAsync('SELECT profileId, packageId, courseId, questionId, questionRevision, practiceId, practiceKind, firstAnswerCorrect, attemptCount, hintsUsed, result, knowledgePoints, createdAt FROM attempts'),
    completions: await database.getAllAsync('SELECT profileId, packageId, lessonId, courseId, revision, completedAt, effectiveMs FROM completions'),
    rewardEvents: await database.getAllAsync('SELECT dedupKey, profileId, amount, reason, createdAt FROM reward_events'),
    reviewQueue: await database.getAllAsync('SELECT profileId, packageId, practiceId, reason, priority, updatedAt FROM review_queue'),
    activeTime: await database.getAllAsync('SELECT day, profileId, ms FROM active_time'),
  };
  const file = new File(Paths.cache, `yue-backup-${payload.exportedAt.replace(/[:.]/g, '-')}.json`);
  file.create({ overwrite: true });
  file.write(JSON.stringify(payload, null, 2), { append: true });
  return file;
}

export async function shareBackup(file: File): Promise<void> {
  const available = await Sharing.isAvailableAsync();
  if (!available) {
    throw new PackError('当前设备不支持系统分享，无法导出备份');
  }
  await Sharing.shareAsync(file.uri, {
    mimeType: 'application/json',
    dialogTitle: '导出学习备份',
  });
}

export async function restoreBackup(sourceUri: string): Promise<{ restored: boolean; items: number }> {
  const source = new File(sourceUri);
  if (!source.exists) {
    throw new PackError('备份文件不存在或无法读取');
  }
  let payload: BackupPayload;
  try {
    payload = JSON.parse(await source.text()) as BackupPayload;
  } catch {
    throw new PackError('备份文件不是有效的 JSON');
  }
  if (payload.schemaVersion !== 1 || !Array.isArray(payload.attempts) || !Array.isArray(payload.completions)) {
    throw new PackError('备份协议版本不受支持或数据不完整');
  }
  const database = await db.getDb();
  const lastRestoreId = await db.getSetting('lastRestoreId');
  if (lastRestoreId === payload.exportedAt) {
    return { restored: false, items: 0 };
  }
  const record = (value: unknown, keys: string[]): SQLiteBindValue[] | null => {
    if (typeof value !== 'object' || value === null) return null;
    const row = value as Record<string, unknown>;
    if (!keys.every((key) => key in row)) return null;
    return keys.map((key) => (row[key] ?? null) as SQLiteBindValue);
  };
  let items = 0;
  await database.withTransactionAsync(async () => {
    for (const value of payload.attempts) {
      const row = record(value, [
        'profileId', 'packageId', 'courseId', 'questionId', 'questionRevision', 'practiceId',
        'practiceKind', 'firstAnswerCorrect', 'attemptCount', 'hintsUsed', 'result', 'knowledgePoints', 'createdAt',
      ]);
      if (!row) continue;
      await database.runAsync(
        `INSERT INTO attempts
          (profileId, packageId, courseId, questionId, questionRevision, practiceId, practiceKind,
           firstAnswerCorrect, attemptCount, hintsUsed, result, knowledgePoints, createdAt)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        row,
      );
      items += 1;
    }
    for (const value of payload.completions) {
      const row = record(value, ['profileId', 'packageId', 'lessonId', 'courseId', 'revision', 'completedAt', 'effectiveMs']);
      if (!row) continue;
      await database.runAsync(
        `INSERT INTO completions (profileId, packageId, lessonId, courseId, revision, completedAt, effectiveMs)
         VALUES (?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT(profileId, packageId, lessonId) DO UPDATE SET
           completedAt = excluded.completedAt, effectiveMs = excluded.effectiveMs`,
        row,
      );
      items += 1;
    }
    for (const value of payload.rewardEvents) {
      const row = record(value, ['dedupKey', 'profileId', 'amount', 'reason', 'createdAt']);
      if (!row) continue;
      await database.runAsync(
        'INSERT OR IGNORE INTO reward_events (dedupKey, profileId, amount, reason, createdAt) VALUES (?, ?, ?, ?, ?)',
        row,
      );
      items += 1;
    }
    for (const value of payload.reviewQueue) {
      const row = record(value, ['profileId', 'packageId', 'practiceId', 'reason', 'priority', 'updatedAt']);
      if (!row) continue;
      await database.runAsync(
        `INSERT INTO review_queue (profileId, packageId, practiceId, reason, priority, updatedAt)
         VALUES (?, ?, ?, ?, ?, ?)
         ON CONFLICT(profileId, packageId, practiceId) DO UPDATE SET
           reason = excluded.reason, priority = MAX(review_queue.priority, excluded.priority), updatedAt = excluded.updatedAt`,
        row,
      );
      items += 1;
    }
    for (const value of payload.activeTime) {
      const row = record(value, ['day', 'profileId', 'ms']);
      if (!row) continue;
      await database.runAsync(
        `INSERT INTO active_time (day, profileId, ms) VALUES (?, ?, ?)
         ON CONFLICT(day, profileId) DO UPDATE SET ms = MAX(active_time.ms, excluded.ms)`,
        row,
      );
      items += 1;
    }
    await db.setSetting('lastRestoreId', payload.exportedAt);
  });
  return { restored: true, items };
}
