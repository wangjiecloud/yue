import * as SQLite from 'expo-sqlite';
import { sha256 } from 'js-sha256';

import { nowIso } from './util';

export interface CourseRow {
  packageId: string;
  courseId: string;
  revision: number;
  title: string;
  courseMode: string;
  grade: number | null;
  subject: string | null;
  dirName: string;
  manifestSha: string;
  isDemo: number;
  installedAt: string;
}

export interface AttemptRow {
  profileId: string;
  packageId: string;
  courseId: string;
  questionId: string;
  questionRevision: number;
  practiceId: string;
  practiceKind: string;
  firstAnswerCorrect: number;
  attemptCount: number;
  hintsUsed: number;
  result: 'correct' | 'assisted' | 'incorrect';
  knowledgePoints: string[];
  createdAt: string;
}

let database: SQLite.SQLiteDatabase | null = null;

export async function getDb(): Promise<SQLite.SQLiteDatabase> {
  if (database) return database;
  const db = await SQLite.openDatabaseAsync('yue.db');
  await db.execAsync('PRAGMA journal_mode = WAL;');
  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS settings (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS courses (
      packageId TEXT PRIMARY KEY,
      courseId TEXT NOT NULL,
      revision INTEGER NOT NULL,
      title TEXT NOT NULL,
      courseMode TEXT NOT NULL,
      grade INTEGER,
      subject TEXT,
      dirName TEXT NOT NULL,
      manifestSha TEXT NOT NULL,
      isDemo INTEGER NOT NULL DEFAULT 0,
      installedAt TEXT NOT NULL,
      UNIQUE(courseId, revision)
    );
    CREATE TABLE IF NOT EXISTS attempts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      profileId TEXT NOT NULL,
      packageId TEXT NOT NULL,
      courseId TEXT NOT NULL,
      questionId TEXT NOT NULL,
      questionRevision INTEGER NOT NULL,
      practiceId TEXT NOT NULL,
      practiceKind TEXT NOT NULL,
      firstAnswerCorrect INTEGER NOT NULL,
      attemptCount INTEGER NOT NULL,
      hintsUsed INTEGER NOT NULL,
      result TEXT NOT NULL,
      knowledgePoints TEXT NOT NULL,
      createdAt TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_attempts_course ON attempts (packageId, practiceId, createdAt);
    CREATE TABLE IF NOT EXISTS completions (
      profileId TEXT NOT NULL,
      packageId TEXT NOT NULL,
      lessonId TEXT NOT NULL,
      courseId TEXT NOT NULL,
      revision INTEGER NOT NULL,
      completedAt TEXT NOT NULL,
      effectiveMs INTEGER NOT NULL,
      PRIMARY KEY (profileId, packageId, lessonId)
    );
    CREATE TABLE IF NOT EXISTS reward_events (
      dedupKey TEXT PRIMARY KEY,
      profileId TEXT NOT NULL,
      amount INTEGER NOT NULL,
      reason TEXT NOT NULL,
      createdAt TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS review_queue (
      profileId TEXT NOT NULL,
      packageId TEXT NOT NULL,
      practiceId TEXT NOT NULL,
      reason TEXT NOT NULL,
      priority INTEGER NOT NULL,
      updatedAt TEXT NOT NULL,
      PRIMARY KEY (profileId, packageId, practiceId)
    );
    CREATE TABLE IF NOT EXISTS active_time (
      day TEXT NOT NULL,
      profileId TEXT NOT NULL,
      ms INTEGER NOT NULL,
      PRIMARY KEY (day, profileId)
    );
    CREATE TABLE IF NOT EXISTS lesson_progress (
      profileId TEXT NOT NULL,
      packageId TEXT NOT NULL,
      lessonId TEXT NOT NULL,
      videoWatched INTEGER NOT NULL DEFAULT 0,
      completedPracticeIds TEXT NOT NULL DEFAULT '[]',
      updatedAt TEXT NOT NULL,
      PRIMARY KEY (profileId, packageId, lessonId)
    );
  `);
  database = db;
  return db;
}

export async function getSetting(key: string): Promise<string | null> {
  const db = await getDb();
  const row = await db.getFirstAsync<{ value: string }>(
    'SELECT value FROM settings WHERE key = ?',
    key,
  );
  return row?.value ?? null;
}

export async function setSetting(key: string, value: string): Promise<void> {
  const db = await getDb();
  await db.runAsync(
    'INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value',
    key,
    value,
  );
}

export async function verifyPin(pin: string): Promise<boolean> {
  const stored = await getSetting('pinHash');
  if (!stored) return false;
  return sha256(pin) === stored;
}

export async function hasPin(): Promise<boolean> {
  return (await getSetting('pinHash')) !== null;
}

export async function setPin(pin: string): Promise<void> {
  await setSetting('pinHash', sha256(pin));
}

export async function clearPin(): Promise<void> {
  const db = await getDb();
  await db.runAsync('DELETE FROM settings WHERE key = ?', 'pinHash');
}

export async function insertCourseRow(row: CourseRow): Promise<void> {
  const db = await getDb();
  await db.runAsync(
    `INSERT INTO courses
      (packageId, courseId, revision, title, courseMode, grade, subject, dirName, manifestSha, isDemo, installedAt)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      row.packageId,
      row.courseId,
      row.revision,
      row.title,
      row.courseMode,
      row.grade,
      row.subject,
      row.dirName,
      row.manifestSha,
      row.isDemo,
      row.installedAt,
    ],
  );
}

export async function findCourseRow(packageId: string): Promise<CourseRow | null> {
  const db = await getDb();
  return db.getFirstAsync<CourseRow>('SELECT * FROM courses WHERE packageId = ?', packageId);
}

export async function findCourseRowByIdentity(
  courseId: string,
  revision: number,
): Promise<CourseRow | null> {
  const db = await getDb();
  return db.getFirstAsync<CourseRow>(
    'SELECT * FROM courses WHERE courseId = ? AND revision = ?',
    courseId,
    revision,
  );
}

export async function listCourseRows(): Promise<CourseRow[]> {
  const db = await getDb();
  return db.getAllAsync<CourseRow>('SELECT * FROM courses ORDER BY installedAt DESC');
}

export async function deleteCourseRow(packageId: string, alsoRecords: boolean): Promise<void> {
  const db = await getDb();
  await db.withTransactionAsync(async () => {
    await db.runAsync('DELETE FROM courses WHERE packageId = ?', packageId);
    if (alsoRecords) {
      await db.runAsync('DELETE FROM attempts WHERE packageId = ?', packageId);
      await db.runAsync('DELETE FROM completions WHERE packageId = ?', packageId);
      await db.runAsync('DELETE FROM review_queue WHERE packageId = ?', packageId);
      await db.runAsync('DELETE FROM lesson_progress WHERE packageId = ?', packageId);
    }
  });
}

export async function recordAttempt(attempt: AttemptRow): Promise<void> {
  const db = await getDb();
  await db.withTransactionAsync(async () => {
    await db.runAsync(
      `INSERT INTO attempts
        (profileId, packageId, courseId, questionId, questionRevision, practiceId, practiceKind,
         firstAnswerCorrect, attemptCount, hintsUsed, result, knowledgePoints, createdAt)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        attempt.profileId,
        attempt.packageId,
        attempt.courseId,
        attempt.questionId,
        attempt.questionRevision,
        attempt.practiceId,
        attempt.practiceKind,
        attempt.firstAnswerCorrect ? 1 : 0,
        attempt.attemptCount,
        attempt.hintsUsed,
        attempt.result,
        JSON.stringify(attempt.knowledgePoints ?? []),
        attempt.createdAt,
      ],
    );
    const needsReview =
      attempt.result === 'incorrect' ||
      (attempt.result === 'assisted' && attempt.hintsUsed > 0);
    if (needsReview) {
      const reason =
        attempt.result === 'incorrect' ? '回答有误，待复习' : '需要提示后完成，待复习';
      await db.runAsync(
        `INSERT INTO review_queue (profileId, packageId, practiceId, reason, priority, updatedAt)
         VALUES (?, ?, ?, ?, 2, ?)
         ON CONFLICT(profileId, packageId, practiceId) DO UPDATE SET
           reason = excluded.reason, priority = MAX(review_queue.priority, 2), updatedAt = excluded.updatedAt`,
        [attempt.profileId, attempt.packageId, attempt.practiceId, reason, nowIso()],
      );
    } else if (attempt.result === 'correct' && attempt.firstAnswerCorrect && attempt.hintsUsed === 0) {
      await db.runAsync(
        'DELETE FROM review_queue WHERE profileId = ? AND packageId = ? AND practiceId = ?',
        [attempt.profileId, attempt.packageId, attempt.practiceId],
      );
    }
  });
}

export async function recordCompletion(
  profileId: string,
  packageId: string,
  lessonId: string,
  courseId: string,
  revision: number,
  effectiveMs: number,
): Promise<void> {
  const db = await getDb();
  await db.runAsync(
    `INSERT INTO completions (profileId, packageId, lessonId, courseId, revision, completedAt, effectiveMs)
     VALUES (?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(profileId, packageId, lessonId) DO UPDATE SET
       completedAt = excluded.completedAt, effectiveMs = excluded.effectiveMs`,
    [profileId, packageId, lessonId, courseId, revision, nowIso(), effectiveMs],
  );
}

export async function grantReward(
  profileId: string,
  dedupKey: string,
  amount: number,
  reason: string,
): Promise<boolean> {
  const db = await getDb();
  const result = await db.runAsync(
    'INSERT OR IGNORE INTO reward_events (dedupKey, profileId, amount, reason, createdAt) VALUES (?, ?, ?, ?, ?)',
    [dedupKey, profileId, amount, reason, nowIso()],
  );
  return result.changes > 0;
}

export async function totalRewardStars(): Promise<number> {
  const db = await getDb();
  const row = await db.getFirstAsync<{ total: number | null }>(
    'SELECT SUM(amount) AS total FROM reward_events',
  );
  return row?.total ?? 0;
}

export async function addActiveTime(profileId: string, ms: number): Promise<void> {
  const day = nowIso().slice(0, 10);
  const db = await getDb();
  await db.runAsync(
    `INSERT INTO active_time (day, profileId, ms) VALUES (?, ?, ?)
     ON CONFLICT(day, profileId) DO UPDATE SET ms = ms + excluded.ms`,
    [day, profileId, ms],
  );
}

export async function recentActiveTime(profileId: string, days: number): Promise<{ day: string; ms: number }[]> {
  const db = await getDb();
  return db.getAllAsync<{ day: string; ms: number }>(
    'SELECT day, ms FROM active_time WHERE profileId = ? ORDER BY day DESC LIMIT ?',
    [profileId, days],
  );
}

export interface LessonProgress {
  videoWatched: boolean;
  completedPracticeIds: string[];
}

export async function saveLessonProgress(
  profileId: string,
  packageId: string,
  lessonId: string,
  progress: LessonProgress,
): Promise<void> {
  const db = await getDb();
  await db.runAsync(
    `INSERT INTO lesson_progress (profileId, packageId, lessonId, videoWatched, completedPracticeIds, updatedAt)
     VALUES (?, ?, ?, ?, ?, ?)
     ON CONFLICT(profileId, packageId, lessonId) DO UPDATE SET
       videoWatched = MAX(lesson_progress.videoWatched, excluded.videoWatched),
       completedPracticeIds = excluded.completedPracticeIds,
       updatedAt = excluded.updatedAt`,
    [
      profileId,
      packageId,
      lessonId,
      progress.videoWatched ? 1 : 0,
      JSON.stringify(progress.completedPracticeIds),
      nowIso(),
    ],
  );
}

export async function loadLessonProgress(
  profileId: string,
  packageId: string,
  lessonId: string,
): Promise<LessonProgress> {
  const db = await getDb();
  const row = await db.getFirstAsync<{ videoWatched: number; completedPracticeIds: string }>(
    'SELECT videoWatched, completedPracticeIds FROM lesson_progress WHERE profileId = ? AND packageId = ? AND lessonId = ?',
    [profileId, packageId, lessonId],
  );
  if (!row) return { videoWatched: false, completedPracticeIds: [] };
  let ids: string[] = [];
  try {
    const parsed = JSON.parse(row.completedPracticeIds);
    if (Array.isArray(parsed)) ids = parsed.filter((id): id is string => typeof id === 'string');
  } catch {
    ids = [];
  }
  return { videoWatched: row.videoWatched === 1, completedPracticeIds: ids };
}

export async function countCompletions(profileId: string): Promise<number> {
  const db = await getDb();
  const row = await db.getFirstAsync<{ total: number }>(
    'SELECT COUNT(*) AS total FROM completions WHERE profileId = ?',
    profileId,
  );
  return row?.total ?? 0;
}

export interface AttemptSummary {
  total: number;
  firstTryCorrect: number;
  independent: number;
  assisted: number;
  incorrect: number;
}

export async function attemptSummary(profileId: string): Promise<AttemptSummary> {
  const db = await getDb();
  const row = await db.getFirstAsync<{
    total: number;
    firstTryCorrect: number;
    independent: number;
    assisted: number;
    incorrect: number;
  }>(
    `SELECT COUNT(*) AS total,
       SUM(firstAnswerCorrect) AS firstTryCorrect,
       SUM(CASE WHEN result = 'correct' AND hintsUsed = 0 THEN 1 ELSE 0 END) AS independent,
       SUM(CASE WHEN result = 'assisted' THEN 1 ELSE 0 END) AS assisted,
       SUM(CASE WHEN result = 'incorrect' THEN 1 ELSE 0 END) AS incorrect
     FROM attempts WHERE profileId = ?`,
    profileId,
  );
  return {
    total: row?.total ?? 0,
    firstTryCorrect: row?.firstTryCorrect ?? 0,
    independent: row?.independent ?? 0,
    assisted: row?.assisted ?? 0,
    incorrect: row?.incorrect ?? 0,
  };
}

export async function reviewList(profileId: string): Promise<
  { packageId: string; practiceId: string; reason: string; priority: number; updatedAt: string }[]
> {
  const db = await getDb();
  return db.getAllAsync(
    'SELECT packageId, practiceId, reason, priority, updatedAt FROM review_queue WHERE profileId = ? ORDER BY priority DESC, updatedAt DESC',
    profileId,
  );
}
