export interface Health {
  status: string;
  deepseekConfigured: boolean;
  tts: {
    ready: boolean;
    macos_say?: boolean;
    cosyvoice_importable?: boolean;
    placeholder_allowed?: boolean;
    cosyvoice_model_dir?: string;
  };
  dataDir: string;
}

export interface Job {
  jobId: string;
  uploadId: string;
  status: "queued" | "running" | "waitingReview" | "succeeded" | "failed" | "cancelled";
  stage: string;
  progress: number;
  demo: boolean;
  error: string | null;
  videoPath: string | null;
  packagePath: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface TeachingPlanSummary {
  planId: string;
  question: {
    stem: string;
    grade: number;
    subject: string;
    knowledgePoints: string[];
    answer: { kind: string; optionId?: string; value?: number };
  };
  solution: { steps: { index: number; text: string; expression: string | null }[]; finalAnswer: string };
  practice: { practiceId: string; kind: string; prompt: string; hints: string[] }[];
  diagnosis: { visibleError: string | null; commonMisconceptions: string[] };
  meta: { placeholderAudio: boolean; generator: string };
}

export interface AssetRecord {
  asset_id: string;
  kind: string;
  path: string;
  source_note: string;
  rights_status: string;
  allowed_uses: string;
  transcript: string;
  language: string;
  emotion: string;
  duration_ms: number | null;
  checksum: string;
  created_at: string;
}
