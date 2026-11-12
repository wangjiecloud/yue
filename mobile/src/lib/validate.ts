import type { Course, Lesson, Manifest, PracticeItem } from '../types';
import { compareVersions, PackError } from './util';

export const SUPPORTED_CAPABILITIES = new Set([
  'video.h264',
  'video.aac',
  'subtitle.srt',
  'interaction.singleChoice',
  'interaction.pairing',
  'interaction.ordering',
  'interaction.dragDrop',
  'audio.wav',
  'audio.aac',
  'audio.mp3',
  'audio.m4a',
]);

function collectErrors(throwMessage: string, errors: string[]): never {
  throw new PackError(`${throwMessage}: ${errors.join('; ')}`);
}

export function validateManifest(manifest: Manifest, appVersion: string): void {
  const errors: string[] = [];
  if (manifest.schemaVersion !== undefined && manifest.schemaVersion !== 1) {
    errors.push(`不支持的协议版本 schemaVersion=${manifest.schemaVersion}`);
  }
  if (manifest.courseMode !== 'interactive' && manifest.courseMode !== 'lectureOnly') {
    errors.push(`未知课程模式: ${manifest.courseMode}`);
  }
  if (manifest.revision < 1) {
    errors.push('revision 必须 >= 1');
  }
  if (manifest.minimumAppVersion && compareVersions(appVersion, manifest.minimumAppVersion) < 0) {
    errors.push(`App 版本过低（需要 ${manifest.minimumAppVersion}，当前 ${appVersion}）`);
  }
  if (!manifest.assets.length) {
    errors.push('manifest 未声明任何资源');
  }
  const unsupported = (manifest.requiredCapabilities ?? []).filter(
    (capability) => !SUPPORTED_CAPABILITIES.has(capability),
  );
  if (unsupported.length) {
    errors.push(`App 不支持的课程能力: ${unsupported.join(', ')}`);
  }
  const assetIds = new Set(manifest.assets.map((asset) => asset.assetId));
  if (assetIds.size !== manifest.assets.length) {
    errors.push('manifest 内 assetId 重复');
  }
  if (errors.length) collectErrors('课程包 manifest 校验失败', errors);
}

function validatePractice(practice: PracticeItem, errors: string[]): void {
  const { answer, kind } = practice;
  if (!practice.prompt) errors.push(`练习 ${practice.practiceId} 缺少题干`);
  if (!practice.hints.length || practice.hints.length > 3) {
    errors.push(`练习 ${practice.practiceId} 提示数量须为 1 至 3 条`);
  }
  if (!practice.explanation) {
    errors.push(`练习 ${practice.practiceId} 缺少讲解`);
  }
  if (practice.maxAttempts < 1 || practice.maxAttempts > 3) {
    errors.push(`练习 ${practice.practiceId} 作答次数须为 1 至 3`);
  }
  if (kind === 'singleChoice' || kind === 'dragDrop') {
    if (!practice.options?.length) {
      errors.push(`练习 ${practice.practiceId} 缺少选项`);
      return;
    }
    if (answer.kind !== 'choice' && answer.kind !== 'numeric') {
      errors.push(`练习 ${practice.practiceId} 的答案类型与题型不匹配`);
      return;
    }
    if (answer.kind === 'choice' && !practice.options.some((option) => option.id === answer.optionId)) {
      errors.push(`练习 ${practice.practiceId} 的答案选项不存在`);
    }
    const optionIds = new Set(practice.options.map((option) => option.id));
    if (optionIds.size !== practice.options.length) {
      errors.push(`练习 ${practice.practiceId} 选项 id 重复`);
    }
  } else if (kind === 'pairing') {
    if (!practice.left?.length || !practice.right?.length) {
      errors.push(`练习 ${practice.practiceId} 缺少配对两侧内容`);
      return;
    }
    if (answer.kind !== 'pairing') {
      errors.push(`练习 ${practice.practiceId} 的答案类型与题型不匹配`);
      return;
    }
    const leftIds = new Set(practice.left.map((side) => side.id));
    const rightIds = new Set(practice.right.map((side) => side.id));
    for (const pair of answer.pairs) {
      if (!leftIds.has(pair.leftId) || !rightIds.has(pair.rightId)) {
        errors.push(`练习 ${practice.practiceId} 的配对答案引用了不存在的选项`);
      }
    }
  } else if (kind === 'ordering') {
    if (!practice.options?.length) {
      errors.push(`练习 ${practice.practiceId} 缺少排序选项`);
      return;
    }
    if (answer.kind !== 'ordering') {
      errors.push(`练习 ${practice.practiceId} 的答案类型与题型不匹配`);
      return;
    }
    const optionIds = new Set(practice.options.map((option) => option.id));
    if (answer.order.length !== practice.options.length) {
      errors.push(`练习 ${practice.practiceId} 的排序答案长度与选项不一致`);
    }
    for (const id of answer.order) {
      if (!optionIds.has(id)) {
        errors.push(`练习 ${practice.practiceId} 的排序答案引用了不存在的选项`);
      }
    }
  } else {
    errors.push(`练习 ${practice.practiceId} 使用未知题型 ${kind}`);
  }
}

function validateLesson(lesson: Lesson, course: Course, manifest: Manifest, errors: string[]): void {
  const steps = new Map(lesson.steps.map((step) => [step.id, step]));
  if (steps.size !== lesson.steps.length) {
    errors.push(`课时 ${lesson.lessonId} 存在重复步骤 id`);
  }
  if (!steps.has(lesson.entryStepId)) {
    errors.push(`课时 ${lesson.lessonId} 的入口步骤不存在`);
    return;
  }
  const practiceIds = new Set(course.practices.map((practice) => practice.practiceId));
  const assetIds = new Set(manifest.assets.map((asset) => asset.assetId));

  for (const step of lesson.steps) {
    for (const target of [step.nextStepId, step.onCorrect, step.onIncorrect, step.onAttemptsExhausted]) {
      if (target && !steps.has(target)) {
        errors.push(`步骤 ${step.id} 引用了不存在的步骤 ${target}`);
      }
    }
    if (step.type === 'interaction') {
      const practiceId = (step.interaction as { practiceId?: string } | null)?.practiceId;
      if (!practiceId || !practiceIds.has(practiceId)) {
        errors.push(`步骤 ${step.id} 引用了不存在的练习 ${String(practiceId)}`);
      }
      if (!step.onCorrect || !step.onIncorrect) {
        errors.push(`互动步骤 ${step.id} 必须定义答对与答错分支`);
      }
      if (step.maxAttempts && !step.onAttemptsExhausted) {
        errors.push(`互动步骤 ${step.id} 必须定义次数用尽分支`);
      }
    }
    if (step.assetId && !assetIds.has(step.assetId)) {
      errors.push(`步骤 ${step.id} 引用了不存在的资源 ${step.assetId}`);
    }
    if (step.type !== 'finish' && step.type !== 'feedback' && step.type !== 'interaction' && !step.nextStepId) {
      errors.push(`步骤 ${step.id} 是没有后续的死路`);
    }
  }

  const reachable = new Set<string>();
  const stack = [lesson.entryStepId];
  while (stack.length) {
    const current = stack.pop() as string;
    if (reachable.has(current)) continue;
    reachable.add(current);
    const step = steps.get(current);
    if (!step) continue;
    for (const target of [step.nextStepId, step.onCorrect, step.onIncorrect, step.onAttemptsExhausted]) {
      if (target) stack.push(target);
    }
  }
  const unreachable = [...steps.keys()].filter((id) => !reachable.has(id));
  if (unreachable.length) {
    errors.push(`课时 ${lesson.lessonId} 存在不可达步骤: ${unreachable.join(', ')}`);
  }

  if (lesson.courseMode === 'interactive' && !lesson.practiceIds.length) {
    errors.push(`互动课时 ${lesson.lessonId} 没有练习`);
  }
  if (lesson.courseMode === 'lectureOnly' && lesson.practiceIds.length) {
    errors.push(`仅讲解课时 ${lesson.lessonId} 不应声明练习`);
  }
  if (!assetIds.has(lesson.videoAssetId)) {
    errors.push(`课时 ${lesson.lessonId} 引用了不存在的视频资源 ${lesson.videoAssetId}`);
  }
  if (lesson.chapters.length) {
    const starts = lesson.chapters.map((chapter) => chapter.startMs);
    const ordered = [...starts].sort((a, b) => a - b);
    if (starts.some((start, index) => start !== ordered[index])) {
      errors.push(`课时 ${lesson.lessonId} 章节时间未排序`);
    }
    if (lesson.durationMs && starts[starts.length - 1] >= lesson.durationMs) {
      errors.push(`课时 ${lesson.lessonId} 章节起点超出视频时长`);
    }
  }
  for (const practiceId of lesson.practiceIds) {
    if (!practiceIds.has(practiceId)) {
      errors.push(`课时 ${lesson.lessonId} 引用了不存在的练习 ${practiceId}`);
    }
  }
}

export function validateCourse(course: Course, manifest: Manifest): void {
  const errors: string[] = [];
  if (course.schemaVersion !== undefined && course.schemaVersion !== 1) {
    errors.push(`不支持的课程协议版本 schemaVersion=${course.schemaVersion}`);
  }
  if (!course.lessons.length) {
    errors.push('课程没有课时');
  }
  const lessonIds = new Set(course.lessons.map((lesson) => lesson.lessonId));
  if (lessonIds.size !== course.lessons.length) {
    errors.push('课程内 lessonId 重复');
  }
  const practiceIds = new Set(course.practices.map((practice) => practice.practiceId));
  if (practiceIds.size !== course.practices.length) {
    errors.push('课程内 practiceId 重复');
  }
  for (const practice of course.practices) {
    validatePractice(practice, errors);
  }
  for (const lesson of course.lessons) {
    validateLesson(lesson, course, manifest, errors);
  }
  if (manifest.courseId !== course.courseId || manifest.revision !== course.revision) {
    errors.push('manifest 与课程标识不一致');
  }
  if (course.lessons[0] && manifest.courseMode !== course.lessons[0].courseMode) {
    errors.push('manifest 与课时的课程模式不一致');
  }
  if (errors.length) collectErrors('课程定义校验失败', errors);
}
