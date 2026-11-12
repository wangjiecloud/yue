<script setup lang="ts">
import { onMounted, ref } from "vue";
import { createAsset, fetchAssets } from "../api";
import type { AssetRecord } from "../types";

const assets = ref<AssetRecord[]>([]);
const error = ref("");
const saved = ref(false);
const form = ref({
  assetId: "",
  kind: "image",
  path: "",
  sourceNote: "",
  rightsStatus: "未确认",
  allowedUses: "",
  transcript: "",
  language: "zh",
  emotion: "neutral",
});

async function refresh() {
  try {
    assets.value = await fetchAssets();
  } catch (exc) {
    error.value = String(exc instanceof Error ? exc.message : exc);
  }
}

async function submit() {
  error.value = "";
  saved.value = false;
  try {
    await createAsset({ ...form.value });
    saved.value = true;
    form.value.assetId = "";
    form.value.path = "";
    await refresh();
  } catch (exc) {
    error.value = String(exc instanceof Error ? exc.message : exc);
  }
}

onMounted(refresh);
</script>

<template>
  <div class="card">
    <h2>素材库</h2>
    <p class="hint">
      登记本地素材及其来源与用途限制。来源不明或权限未确认的素材会被明确标记，不视为已获得授权。
    </p>
    <form class="grid" @submit.prevent="submit">
      <input v-model="form.assetId" placeholder="素材标识，如 mlp-wave-01" required />
      <select v-model="form.kind">
        <option value="image">图片</option>
        <option value="character">角色动作</option>
        <option value="audio">短句音频</option>
        <option value="video">短视频</option>
      </select>
      <input v-model="form.path" placeholder="本地文件绝对路径" required />
      <input v-model="form.sourceNote" placeholder="来源说明（不填账号密码）" />
      <select v-model="form.rightsStatus">
        <option value="未确认">未确认</option>
        <option value="允许指定用途">允许指定用途</option>
        <option value="禁止使用">禁止使用</option>
      </select>
      <input v-model="form.allowedUses" placeholder="允许用途及限制" />
      <input v-model="form.transcript" placeholder="音频原文（如是）" />
      <select v-model="form.language">
        <option value="zh">中文</option>
        <option value="en">英文</option>
      </select>
      <button type="submit">登记素材</button>
    </form>
    <p v-if="saved" class="ok">已登记。</p>
    <p v-if="error" class="bad">{{ error }}</p>
    <table v-if="assets.length">
      <thead>
        <tr>
          <th>标识</th>
          <th>类型</th>
          <th>权利状态</th>
          <th>用途</th>
          <th>来源</th>
          <th>校验和</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="asset in assets" :key="asset.asset_id">
          <td>{{ asset.asset_id }}</td>
          <td>{{ asset.kind }}</td>
          <td>
            <span class="badge" :class="asset.rights_status === '允许指定用途' ? 'ok' : 'warn'">
              {{ asset.rights_status }}
            </span>
          </td>
          <td>{{ asset.allowed_uses }}</td>
          <td>{{ asset.source_note }}</td>
          <td class="mono">{{ asset.checksum.slice(0, 12) }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else>暂无登记素材。</p>
  </div>
</template>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin: 12px 0;
}

.hint {
  color: var(--muted);
  font-size: 13px;
}

.ok {
  color: #0a8f6c;
}

.bad {
  color: #b3285b;
}

.mono {
  font-family: ui-monospace, monospace;
  font-size: 12px;
}
</style>
