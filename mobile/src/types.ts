export type CourseMode = 'interactive' | 'lectureOnly';

export type AssetKind = 'video' | 'audio' | 'image' | 'subtitle' | 'animation';

export interface ManifestAsset {
  assetId: string;
  path: string;
  kind: AssetKind;
  sha256: string;
  bytes: number;
  durationMs?: number | null;
}

export interface Manifest {
  packageId: string;
  courseId: string;
  revision: number;
  schemaVersion?: number;
  minimumAppVersion?: string;
  courseMode: CourseMode;
  requiredCapabilities?: string[];
  createdAt: string;
  assets: ManifestAsset[];
  totalUncompressedBytes: number;
}

export interface Option {
  id: string;
  label: string;
}

export type PracticeKind = 'singleChoice' | 'pairing' | 'ordering' | 'dragDrop';

export type Answer =
  | { kind: 'numeric'; value: number }
  | { kind: 'choice'; optionId: string }
  | { kind: 'pairing'; pairs: { leftId: string; rightId: string }[] }
  | { kind: 'ordering'; order: string[] };

export interface PairSide {
  id: string;
  label: string;
}

export interface PracticeItem {
  practiceId: string;
  kind: PracticeKind;
  prompt: string;
  options?: Option[];
  left?: PairSide[];
  right?: PairSide[];
  answer: Answer;
  hints: string[];
  explanation: string;
  knowledgePoints?: string[];
  maxAttempts: number;
}

export type StepType =
  | 'display'
  | 'narrate'
  | 'video'
  | 'character'
  | 'animateObjects'
  | 'interaction'
  | 'feedback'
  | 'reward'
  | 'finish';

export type FeedbackResult = 'correct' | 'incorrect' | 'assisted';

export interface LessonStep {
  id: string;
  type: StepType;
  assetId?: string | null;
  prompt?: string | null;
  text?: string | null;
  result?: FeedbackResult | null;
  interaction?: { practiceId: string } | Record<string, unknown> | null;
  nextStepId?: string | null;
  onCorrect?: string | null;
  onIncorrect?: string | null;
  maxAttempts?: number | null;
  onAttemptsExhausted?: string | null;
  rewardKey?: string | null;
  amount?: number | null;
}

export interface ChapterTime {
  chapterId: string;
  title: string;
  startMs: number;
}

export interface Lesson {
  lessonId: string;
  questionId: string;
  questionRevision: number;
  title: string;
  courseMode: CourseMode;
  videoAssetId: string;
  durationMs: number;
  subtitleAssetId?: string | null;
  chapters: ChapterTime[];
  entryStepId: string;
  steps: LessonStep[];
  practiceIds: string[];
}

export interface Course {
  schemaVersion?: number;
  courseId: string;
  revision: number;
  grade: 1 | 2 | 3;
  subject: 'math' | 'chinese' | 'english';
  knowledgePoints?: string[];
  lessons: Lesson[];
  practices: PracticeItem[];
}

export type AttemptResult = 'correct' | 'assisted' | 'incorrect';
