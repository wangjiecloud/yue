import type { Course, Lesson, LessonStep, PracticeItem } from '../types';
import { gradeAnswer, type Submission } from './grade';

export type Phase =
  | { kind: 'video' }
  | { kind: 'interaction'; stepId: string; practice: PracticeItem; attempts: number; hintsUsed: number; lastCorrect: boolean | null }
  | { kind: 'message'; stepId: string; text: string; audioAssetId: string | null; result: 'correct' | 'incorrect' | 'assisted' | null }
  | { kind: 'finished' };

export type LessonEvent =
  | {
      type: 'practiceConcluded';
      practiceId: string;
      practiceKind: string;
      result: 'correct' | 'assisted';
      firstAnswerCorrect: boolean;
      attemptCount: number;
      hintsUsed: number;
    }
  | { type: 'reward'; dedupKey: string; amount: number }
  | { type: 'completed' };

export class LessonRuntime {
  private readonly course: Course;
  private readonly lesson: Lesson;
  private readonly steps: Map<string, LessonStep>;
  private readonly onEvent: (event: LessonEvent) => void;
  private currentStepId = '';
  private practiceState = new Map<string, { attempts: number; hintsUsed: number; concluded: boolean }>();
  private activePracticeId: string | null = null;
  private concluded = new Set<string>();

  phase: Phase = { kind: 'video' };

  constructor(course: Course, lesson: Lesson, onEvent: (event: LessonEvent) => void) {
    this.course = course;
    this.lesson = lesson;
    this.steps = new Map(lesson.steps.map((step) => [step.id, step]));
    this.onEvent = onEvent;
  }

  start(videoWatched: boolean, completedPracticeIds: string[]): void {
    for (const practiceId of completedPracticeIds) {
      this.concluded.add(practiceId);
    }
    const entry = this.steps.get(this.lesson.entryStepId);
    if (!entry) {
      this.phase = { kind: 'finished' };
      return;
    }
    if (entry.type === 'video' && videoWatched) {
      this.enterStep(this.skipCompleted(entry.nextStepId ?? ''), true);
      return;
    }
    this.enterStep(this.lesson.entryStepId, false);
  }

  private skipCompleted(stepId: string): string {
    let current = stepId;
    let guard = 0;
    while (guard < 200) {
      guard += 1;
      const step = this.steps.get(current);
      if (!step) return current;
      if (step.type === 'interaction') {
        const practiceId = (step.interaction as { practiceId?: string } | null)?.practiceId ?? '';
        if (this.concluded.has(practiceId)) {
          current = step.onCorrect ?? step.nextStepId ?? '';
          continue;
        }
      }
      return current;
    }
    return current;
  }

  private enterStep(stepId: string, silent: boolean): void {
    const step = this.steps.get(stepId);
    if (!step) {
      this.phase = { kind: 'finished' };
      return;
    }
    this.currentStepId = stepId;
    switch (step.type) {
      case 'video':
        this.phase = { kind: 'video' };
        break;
      case 'interaction': {
        const practiceId = (step.interaction as { practiceId?: string } | null)?.practiceId ?? '';
        const practice = this.course.practices.find((candidate) => candidate.practiceId === practiceId);
        if (!practice) {
          this.phase = { kind: 'finished' };
          return;
        }
        this.activePracticeId = practiceId;
        const state = this.stateFor(practiceId);
        this.phase = {
          kind: 'interaction',
          stepId,
          practice,
          attempts: state.attempts,
          hintsUsed: state.hintsUsed,
          lastCorrect: null,
        };
        break;
      }
      case 'feedback':
      case 'display':
      case 'narrate':
      case 'character':
      case 'animateObjects': {
        if (step.type === 'display' && step.id.startsWith('hint-') && this.activePracticeId) {
          const state = this.practiceState.get(this.activePracticeId);
          if (state) state.hintsUsed += 1;
        }
        this.phase = {
          kind: 'message',
          stepId,
          text: step.text ?? step.prompt ?? '',
          audioAssetId: step.assetId ?? null,
          result: step.result ?? null,
        };
        if (step.rewardKey && step.amount && !silent) {
          this.onEvent({ type: 'reward', dedupKey: step.rewardKey, amount: step.amount });
        }
        break;
      }
      case 'reward':
        if (step.rewardKey && step.amount && !silent) {
          this.onEvent({ type: 'reward', dedupKey: step.rewardKey, amount: step.amount });
        }
        this.enterStep(step.nextStepId ?? '', silent);
        break;
      case 'finish':
        this.phase = { kind: 'finished' };
        if (!silent) {
          this.onEvent({ type: 'completed' });
        }
        break;
      default:
        this.enterStep(step.nextStepId ?? '', silent);
    }
  }

  private stateFor(practiceId: string): { attempts: number; hintsUsed: number; concluded: boolean } {
    let state = this.practiceState.get(practiceId);
    if (!state) {
      state = { attempts: 0, hintsUsed: 0, concluded: false };
      this.practiceState.set(practiceId, state);
    }
    return state;
  }

  onVideoEnded(): void {
    const step = this.steps.get(this.currentStepId);
    if (!step || step.type !== 'video') return;
    this.enterStep(this.skipCompleted(step.nextStepId ?? ''), false);
  }

  skipVideo(): void {
    const step = this.steps.get(this.currentStepId);
    if (!step || step.type !== 'video') return;
    this.enterStep(this.skipCompleted(step.nextStepId ?? ''), false);
  }

  replayVideo(): void {
    const entry = this.steps.get(this.lesson.entryStepId);
    if (entry?.type === 'video') {
      this.enterStep(this.lesson.entryStepId, false);
    }
  }

  submitAnswer(submission: Submission): boolean {
    const step = this.steps.get(this.currentStepId);
    if (!step || step.type !== 'interaction') return false;
    const practiceId = (step.interaction as { practiceId?: string } | null)?.practiceId ?? '';
    const practice = this.course.practices.find((candidate) => candidate.practiceId === practiceId);
    if (!practice) return false;
    const state = this.stateFor(practiceId);
    if (state.concluded) return false;
    state.attempts += 1;
    const correct = gradeAnswer(practice, submission);
    const maxAttempts = step.maxAttempts ?? practice.maxAttempts;
    if (correct) {
      state.concluded = true;
      this.concluded.add(practiceId);
      const result = state.hintsUsed > 0 ? 'assisted' : 'correct';
      this.onEvent({
        type: 'practiceConcluded',
        practiceId,
        practiceKind: practice.kind,
        result,
        firstAnswerCorrect: state.attempts === 1,
        attemptCount: state.attempts,
        hintsUsed: state.hintsUsed,
      });
      this.enterStep(step.onCorrect ?? '', false);
      return true;
    }
    if (state.attempts >= maxAttempts) {
      state.concluded = true;
      this.concluded.add(practiceId);
      this.onEvent({
        type: 'practiceConcluded',
        practiceId,
        practiceKind: practice.kind,
        result: 'assisted',
        firstAnswerCorrect: false,
        attemptCount: state.attempts,
        hintsUsed: state.hintsUsed,
      });
      this.enterStep(step.onAttemptsExhausted ?? step.onCorrect ?? '', false);
      return false;
    }
    this.enterStep(step.onIncorrect ?? '', false);
    return false;
  }

  continueFromMessage(): void {
    const step = this.steps.get(this.currentStepId);
    if (!step) return;
    if (step.type === 'interaction') return;
    this.enterStep(this.skipCompleted(step.nextStepId ?? ''), false);
  }

  get currentPracticeIds(): string[] {
    return this.lesson.practiceIds;
  }
}
