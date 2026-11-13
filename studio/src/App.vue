<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import AssetsPanel from "./components/AssetsPanel.vue";
import {
  cancelJob,
  createJob,
  exportPackage,
  fetchHealth,
  fetchJob,
  fetchJobs,
  fetchPlan,
  jobPackageUrl,
  jobSubtitleUrl,
  jobVideoUrl,
  loadSession,
  regenerateJob,
  uploadImage,
} from "./api";
import type { Health, Job, TeachingPlanSummary } from "./types";

type Tab = "make" | "tasks" | "assets";

const health = ref<Health | null>(null);
const tab = ref<Tab>("make");
const file = ref<File | null>(null);
const grade = ref<number>(1);
const subjectHint = ref<string>("math");
const creating = ref(false);
const error = ref<string>("");
const job = ref<Job | null>(null);
const plan = ref<TeachingPlanSummary | null>(null);
const jobs = ref<Job[]>([]);
const exportUrl = ref<string>("");
const regenMode = ref<string>("simpler");
const regenFeedback = ref<string>("");
const regenerating = ref(false);
let pollTimer: number | null = null;

const previewUrl = computed(() => (file.value ? URL.createObjectURL(file.value) : ""));

const stageLabels: Record<string, string> = {
  queued: "排队中",
  preprocess: "检查图片",
  recognize: "识题与教学规划",
  tts: "生成配音",
  render: "渲染动画",
  package: "打包课程",
  done: "等待确认",
  cancelled: "已取消",
};

function stageLabel(stage: string): string {
  return stageLabels[stage] ?? stage;
}

function statusBadge(status: string): string {
  if (status === "waitingReview" || status === "succeeded") return "ok";
  if (status === "failed") return "bad";
  if (status === "cancelled") return "warn";
  return "warn";
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  file.value = input.files?.[0] ?? null;
  error.value = "";
}

async function refreshJobs() {
  jobs.value = await fetchJobs();
}

async function start(demo: boolean) {
  error.value = "";
  plan.value = null;
  exportUrl.value = "";
  if (!demo && !file.value) {
    error.value = "请先选择一张错题图片。";
    return;
  }
  creating.value = true;
  try {
    let uploadId: string | undefined;
    if (!demo && file.value) {
      uploadId = (await uploadImage(file.value)).uploadId;
    }
    const created = await createJob({
      uploadId,
      grade: grade.value,
      subjectHint: subjectHint.value,
      demo,
    });
    job.value = created;
    tab.value = "make";
    startPolling();
    void refreshJobs();
  } catch (exc) {
    error.value = String(exc instanceof Error ? exc.message : exc);
  } finally {
    creating.value = false;
  }
}

function startPolling() {
  stopPolling();
  pollTimer = window.setInterval(async () => {
    if (!job.value) return;
    try {
      job.value = await fetchJob(job.value.jobId);
      if (["waitingReview", "succeeded", "failed", "cancelled"].includes(job.value.status)) {
        stopPolling();
        if (job.value.status === "waitingReview") {
          plan.value = await fetchPlan(job.value.jobId);
        }
        void refreshJobs();
      }
    } catch {
      /* keep polling on transient errors */
    }
  }, 1200);
}

function stopPolling() {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function onCancel() {
  if (!job.value) return;
  try {
    await cancelJob(job.value.jobId);
    job.value = await fetchJob(job.value.jobId);
    stopPolling();
  } catch (exc) {
    error.value = String(exc instanceof Error ? exc.message : exc);
  }
}

async function onExport() {
  if (!job.value) return;
  try {
    const result = await exportPackage(job.value.jobId);
    exportUrl.value = jobPackageUrl(job.value.jobId);
    void result;
  } catch (exc) {
    error.value = String(exc instanceof Error ? exc.message : exc);
  }
}

async function onRegenerate() {
  if (!job.value) return;
  regenerating.value = true;
  error.value = "";
  try {
    const created = await regenerateJob(job.value.jobId, {
      mode: regenMode.value,
      feedback: regenFeedback.value,
    });
    plan.value = null;
    exportUrl.value = "";
    regenFeedback.value = "";
    job.value = created;
    startPolling();
    void refreshJobs();
  } catch (exc) {
    error.value = String(exc instanceof Error ? exc.message : exc);
  } finally {
    regenerating.value = false;
  }
}

onMounted(async () => {
  try {
    await loadSession();
    health.value = await fetchHealth();
    await refreshJobs();
    const active = jobs.value.find((item) =>
      ["queued", "running"].includes(item.status),
    );
    if (active) {
      job.value = active;
      startPolling();
    } else {
      const latest = jobs.value[0];
      if (latest && latest.status === "waitingReview") {
        job.value = latest;
        plan.value = await fetchPlan(latest.jobId);
      }
    }
  } catch (exc) {
    error.value = String(exc instanceof Error ? exc.message : exc);
  }
});

onBeforeUnmount(stopPolling);
</script>

<template>
  <main class="wrap">
    <header class="hero">
      <div>
        <h1>Yue 制课后台</h1>
        <p>上传一张错题图片，自动生成教学视频、配音、字幕和互动练习。</p>
      </div>
      <div v-if="health" class="status">
        <span class="badge" :class="health.deepseekConfigured ? 'ok' : 'bad'">
          识题模型{{ health.deepseekConfigured ? "已配置" : "未配置" }}
        </span>
        <span class="badge" :class="health.tts.ready ? 'ok' : 'warn'">
          本地配音{{ health.tts.ready ? "就绪" : "未就绪" }}
        </span>
      </div>
    </header>

    <p v-if="error" class="error">{{ error }}</p>

    <nav class="tabs">
      <button :class="{ secondary: tab !== 'make' }" @click="tab = 'make'">制作课程</button>
      <button :class="{ secondary: tab !== 'tasks' }" @click="tab = 'tasks'; refreshJobs()">
        任务中心
      </button>
      <button :class="{ secondary: tab !== 'assets' }" @click="tab = 'assets'">素材库</button>
    </nav>

    <section v-if="tab === 'make'">
      <div class="card">
        <h2>上传错题图片</h2>
        <p class="hint">图片会发送到内部识题接口。请先遮挡或裁掉孩子姓名、班级等信息。</p>
        <div class="row">
          <input type="file" accept="image/png,image/jpeg,image/webp" @change="onFileChange" />
          <select v-model.number="grade">
            <option :value="1">一年级</option>
            <option :value="2">二年级</option>
            <option :value="3">三年级</option>
          </select>
          <select v-model="subjectHint">
            <option value="math">数学</option>
            <option value="chinese">语文</option>
            <option value="english">英语</option>
          </select>
          <button :disabled="creating" @click="start(false)">自动生成</button>
          <button class="secondary" :disabled="creating" @click="start(true)">
            运行内置演示（工程自检）
          </button>
        </div>
        <img v-if="file" class="preview" :src="previewUrl" alt="题目预览" />
      </div>

      <div v-if="job" class="card">
        <h2>生成进度</h2>
        <p>
          <span class="badge" :class="statusBadge(job.status)">{{ job.status }}</span>
          阶段：{{ stageLabel(job.stage) }}
          <template v-if="job.demo"> · 内置演示</template>
          <template v-if="job.regenerationOf"> · 重新生成自 {{ job.regenerationOf }}</template>
        </p>
        <div class="progress-track">
          <div class="progress-fill" :style="{ width: `${Math.round(job.progress * 100)}%` }" />
        </div>
        <p v-if="job.error" class="error">{{ job.error }}</p>
        <div class="row">
          <button
            v-if="['queued', 'running'].includes(job.status)"
            class="secondary"
            @click="onCancel"
          >
            取消任务
          </button>
        </div>
      </div>

      <div v-if="plan" class="card">
        <h2>结果预览</h2>
        <p>
          <strong>{{ plan.question.stem }}</strong>
          · {{ plan.question.grade }} 年级
          · {{ plan.question.subject }}
        </p>
        <p>答案：{{ plan.question.answer.value ?? plan.question.answer.optionId }}</p>
        <video controls :src="jobVideoUrl(job!.jobId)" />
        <p>
          <a :href="jobSubtitleUrl(job!.jobId)" target="_blank">下载字幕 (SRT)</a>
        </p>
        <h3>讲解步骤</h3>
        <ol>
          <li v-for="step in plan.solution.steps" :key="step.index">
            {{ step.text }}
            <code v-if="step.expression">{{ step.expression }}</code>
          </li>
        </ol>
        <h3>附带练习</h3>
        <ul>
          <li v-for="practice in plan.practice" :key="practice.practiceId">
            {{ practice.prompt }}（{{ practice.kind }}，提示 {{ practice.hints.length }} 层）
          </li>
        </ul>
        <p v-if="plan.diagnosis.visibleError">
          图片可观察的错误：{{ plan.diagnosis.visibleError }}
        </p>
        <p v-else>图片中未看到明确作答痕迹，讲解按常见误区设计。</p>
        <p v-if="plan.meta.placeholderAudio" class="hint">
          注意：本课程使用占位配音（工程探针），不是验收用正式旁白。
        </p>
        <div class="row">
          <button @click="onExport">确认并导出课程包</button>
          <a v-if="exportUrl" :href="exportUrl" download>下载 .yuepack</a>
        </div>
        <hr />
        <h3>重新生成</h3>
        <p class="hint">对讲解不满意时，可基于本任务重新生成一节课。</p>
        <div class="row">
          <select v-model="regenMode" :disabled="regenerating">
            <option value="simpler">讲得更简单</option>
            <option value="slower">放慢节奏、更细</option>
            <option value="error">我发现了错误</option>
          </select>
          <input
            v-model="regenFeedback"
            type="text"
            placeholder="补充说明（可选）"
            :disabled="regenerating"
          />
          <button :disabled="regenerating" @click="onRegenerate">
            {{ regenerating ? "提交中…" : "重新生成" }}
          </button>
        </div>
      </div>
    </section>

    <section v-if="tab === 'tasks'">
      <div class="card">
        <h2>任务中心</h2>
        <table>
          <thead>
            <tr>
              <th>任务</th>
              <th>状态</th>
              <th>阶段</th>
              <th>演示</th>
              <th>创建时间</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in jobs" :key="item.jobId">
              <td>{{ item.jobId }}</td>
              <td>
                <span class="badge" :class="statusBadge(item.status)">{{ item.status }}</span>
              </td>
              <td>{{ stageLabel(item.stage) }}</td>
              <td>{{ item.demo ? "是" : "否" }}</td>
              <td>{{ new Date(item.createdAt).toLocaleString() }}</td>
              <td>
                <button
                  class="secondary"
                  @click="
                    job = item;
                    tab = 'make';
                    if (item.status === 'waitingReview') plan = null;
                    if (item.status === 'waitingReview') fetchPlan(item.jobId).then((p) => (plan = p));
                  "
                >
                  查看
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-if="tab === 'assets'">
      <AssetsPanel />
    </section>
  </main>
</template>

<style scoped>
.wrap {
  max-width: 960px;
  margin: 0 auto;
  padding: 24px;
}

.hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}

.hero h1 {
  margin: 0;
}

.hint {
  color: var(--muted);
  font-size: 13px;
}

.error {
  color: #b3285b;
}

.row {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  margin: 12px 0;
}

.preview {
  max-width: 360px;
  border-radius: 12px;
  margin-top: 12px;
  border: 1px solid #e3e0f5;
}

.tabs {
  display: flex;
  gap: 8px;
  margin: 8px 0 20px;
}

code {
  background: #f3f0ff;
  padding: 1px 6px;
  border-radius: 6px;
}

a {
  color: var(--violet);
}
</style>
