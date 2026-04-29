<template>
  <div class="p-6">
    <section v-if="currentId === '1'" class="space-y-6">
      <header>
        <h2 class="text-xl font-semibold text-gray-900">外观设置</h2>
        <p class="mt-1 text-sm text-gray-500">自定义主题色、布局和字号。</p>
      </header>

      <div class="rounded-xl border border-gray-200 bg-white p-5">
        <div class="flex items-center justify-between gap-4">
          <div>
            <h3 class="font-medium text-gray-900">深色模式</h3>
            <p class="mt-1 text-sm text-gray-500">切换系统整体明暗主题。</p>
          </div>
          <t-switch v-model="isDark" size="large" @change="value => applyDarkMode(Boolean(value))" />
        </div>
      </div>

      <div class="rounded-xl border border-gray-200 bg-white p-5">
        <h3 class="font-medium text-gray-900">主题颜色</h3>
        <div class="mt-4 flex flex-wrap gap-3">
          <button
            v-for="color in themeColors"
            :key="color.key"
            :title="color.label"
            :style="{ background: color.value }"
            :class="[
              'h-10 w-10 rounded-full border-4 shadow-sm transition',
              activeColor === color.key ? 'border-gray-900 scale-105' : 'border-white hover:border-gray-300'
            ]"
            @click="applyThemeColor(color)"
          />
        </div>
        <p class="mt-3 text-xs text-gray-400">当前颜色：{{ currentColorLabel }}</p>
      </div>

      <div class="rounded-xl border border-gray-200 bg-white p-5">
        <h3 class="font-medium text-gray-900">页面布局</h3>
        <div class="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <button
            v-for="layout in layoutOptions"
            :key="layout.key"
            :class="[
              'rounded-xl border p-4 text-left transition',
              activeLayout === layout.key
                ? 'border-blue-500 bg-blue-50 text-blue-700'
                : 'border-gray-200 hover:border-blue-300'
            ]"
            @click="applyLayout(layout.key)"
          >
            <div class="text-sm font-medium">{{ layout.label }}</div>
            <div class="mt-1 text-xs text-gray-500">{{ layout.desc }}</div>
          </button>
        </div>
      </div>

      <div class="rounded-xl border border-gray-200 bg-white p-5">
        <h3 class="font-medium text-gray-900">字号</h3>
        <t-radio-group class="mt-3" :value="fontSize" @change="value => applyFontSize(String(value))">
          <t-radio value="sm">小</t-radio>
          <t-radio value="md">中</t-radio>
          <t-radio value="lg">大</t-radio>
        </t-radio-group>
      </div>

      <t-button theme="primary" @click="saveAppearance">保存外观设置</t-button>
    </section>

    <section v-else-if="currentId === '2'" class="space-y-6">
      <header>
        <h2 class="text-xl font-semibold text-gray-900">第三方账号绑定</h2>
        <p class="mt-1 text-sm text-gray-500">将第三方账号与当前账户关联，便于快捷登录。</p>
      </header>

      <div class="space-y-3">
        <div
          v-for="provider in thirdPartyList"
          :key="provider.key"
          class="flex items-center justify-between rounded-xl border border-gray-200 bg-white p-4"
        >
          <div>
            <div class="font-medium text-gray-900">{{ provider.label }}</div>
            <div class="mt-1 text-sm text-gray-500">
              {{ bindingStatus[provider.key] ? `已绑定：${bindingStatus[provider.key]}` : '未绑定' }}
            </div>
          </div>
          <div class="flex gap-2">
            <t-button
              v-if="!bindingStatus[provider.key]"
              theme="primary"
              variant="outline"
              size="small"
              @click="bindAccount(provider)"
            >
              绑定
            </t-button>
            <t-button
              v-else
              theme="danger"
              variant="outline"
              size="small"
              @click="unbindAccount(provider)"
            >
              解绑
            </t-button>
          </div>
        </div>
      </div>

      <t-dialog v-model:visible="bindDialogVisible" :footer="false" header="绑定账号" width="420px">
        <div class="py-2">
          <p class="text-sm text-gray-600">请输入 {{ currentProvider?.label }} 账号标识。</p>
          <t-input v-model="bindInput" class="mt-4" clearable placeholder="账号 / 邮箱 / OpenID" />
          <div class="mt-6 flex justify-end gap-3">
            <t-button variant="outline" @click="bindDialogVisible = false">取消</t-button>
            <t-button theme="primary" @click="confirmBind">确认绑定</t-button>
          </div>
        </div>
      </t-dialog>
    </section>

    <section v-else-if="currentId === '3'" class="space-y-6">
      <header>
        <h2 class="text-xl font-semibold text-gray-900">探索功能</h2>
        <p class="mt-1 text-sm text-gray-500">这里放置实验性功能，可能会持续调整。</p>
      </header>

      <div class="rounded-xl border border-gray-200 bg-white p-5">
        <div class="flex items-center justify-between gap-4">
          <div>
            <h3 class="font-medium text-gray-900">语音交互</h3>
            <p class="mt-1 text-sm text-gray-500">启用录音入口，并尝试浏览器语音识别。</p>
          </div>
          <t-switch v-model="voiceEnabled" size="large" @change="value => onVoiceToggle(Boolean(value))" />
        </div>

        <div v-if="voiceEnabled" class="mt-4 border-t border-gray-100 pt-4">
          <div class="flex flex-wrap items-center gap-3">
            <t-button theme="primary" :disabled="isRecording" @click="startRecording">开始录音</t-button>
            <t-button variant="outline" :disabled="!isRecording" @click="stopRecording">停止录音</t-button>
            <span class="text-sm text-gray-500">{{ voiceStatus || '就绪' }}</span>
          </div>

          <div v-if="transcriptText" class="mt-4 rounded-lg border border-gray-200 bg-gray-50 p-3">
            <p class="text-xs text-gray-400">识别结果：</p>
            <p class="mt-1 text-sm text-gray-700">{{ transcriptText }}</p>
            <div class="mt-3 flex gap-2">
              <t-button size="small" theme="primary" @click="sendTranscript">发送到对话</t-button>
              <t-button size="small" variant="outline" @click="transcriptText = ''">清除</t-button>
            </div>
          </div>
        </div>
      </div>

      <div class="rounded-xl border border-gray-200 bg-white p-5">
        <div class="flex items-center justify-between gap-4">
          <div>
            <h3 class="font-medium text-gray-900">新布局模式</h3>
            <p class="mt-1 text-sm text-gray-500">切换到更简洁的沉浸式页面布局。</p>
          </div>
          <t-switch
            v-model="newLayoutEnabled"
            size="large"
            @change="value => applyNewLayout(Boolean(value))"
          />
        </div>
      </div>

      <div class="rounded-xl border border-gray-200 bg-white p-5">
        <div class="flex items-center justify-between gap-4">
          <div>
            <h3 class="font-medium text-gray-900">AI 智能摘要</h3>
            <p class="mt-1 text-sm text-gray-500">快速测试文本摘要能力。</p>
          </div>
          <t-switch
            v-model="aiSummaryEnabled"
            size="large"
            @change="value => onAiSummaryToggle(Boolean(value))"
          />
        </div>

        <div v-if="aiSummaryEnabled" class="mt-4 border-t border-gray-100 pt-4">
          <t-textarea
            v-model="summaryInput"
            placeholder="粘贴需要摘要的内容..."
            :rows="4"
            :maxlength="3000"
          />
          <div class="mt-3 flex gap-2">
            <t-button theme="primary" size="small" :loading="summaryLoading" @click="generateSummary">
              生成摘要
            </t-button>
            <t-button size="small" variant="outline" @click="clearSummary">清除</t-button>
          </div>
          <div v-if="summaryResult" class="mt-4 rounded-lg border border-gray-200 bg-gray-50 p-3">
            <p class="text-xs text-gray-400">AI 摘要结果：</p>
            <p class="mt-1 text-sm leading-relaxed text-gray-700">{{ summaryResult }}</p>
          </div>
        </div>
      </div>
    </section>

    <section v-else-if="currentId === '4'" class="space-y-6">
      <header>
        <h2 class="text-xl font-semibold text-gray-900">反馈与建议</h2>
        <p class="mt-1 text-sm text-gray-500">把问题、建议或体验反馈给开发者。</p>
      </header>

      <div class="rounded-xl border border-gray-200 bg-white p-5">
        <div class="space-y-4">
          <div>
            <label class="mb-2 block text-sm font-medium text-gray-700">反馈类型</label>
            <t-radio-group v-model="feedback.type">
              <t-radio value="bug">Bug</t-radio>
              <t-radio value="feature">功能建议</t-radio>
              <t-radio value="ui">界面改进</t-radio>
              <t-radio value="other">其他</t-radio>
            </t-radio-group>
          </div>

          <div>
            <label class="mb-2 block text-sm font-medium text-gray-700">标题</label>
            <t-input v-model="feedback.title" clearable :maxlength="80" show-limit-number />
          </div>

          <div>
            <label class="mb-2 block text-sm font-medium text-gray-700">详细描述</label>
            <t-textarea
              v-model="feedback.content"
              :rows="5"
              :maxlength="2000"
              show-limit-number
              placeholder="请尽量描述清楚复现步骤、预期结果和实际结果。"
            />
          </div>

          <div>
            <label class="mb-2 block text-sm font-medium text-gray-700">联系邮箱</label>
            <t-input v-model="feedback.email" type="text" placeholder="example@email.com" />
          </div>

          <div class="flex gap-3">
            <t-button theme="primary" :loading="feedbackLoading" @click="submitFeedback">提交反馈</t-button>
            <t-button variant="outline" @click="resetFeedback">重置</t-button>
          </div>

          <div v-if="feedbackSent" class="rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-700">
            反馈已提交，感谢你的帮助。
          </div>
        </div>
      </div>
    </section>

    <section v-else-if="currentId === '5'" class="space-y-4">
      <h2 class="text-xl font-semibold text-gray-900">隐私政策</h2>
      <div class="rounded-xl border border-gray-200 bg-white p-5 text-sm leading-7 text-gray-600">
        <p>我们仅在实现知识库与对话功能所需的范围内处理你上传的数据。</p>
        <p>知识库文件默认保存在本地环境，不会被用于模型训练。</p>
        <p>如需删除数据，可通过知识库管理或反馈入口联系维护者处理。</p>
      </div>
    </section>

    <section v-else-if="currentId === '6'" class="space-y-4">
      <h2 class="text-xl font-semibold text-gray-900">关于项目</h2>
      <div class="grid gap-4 sm:grid-cols-2">
        <div class="rounded-xl border border-gray-200 bg-white p-5">
          <div class="text-sm text-gray-400">前端</div>
          <div class="mt-1 font-medium text-gray-900">Vue 3 + TypeScript</div>
        </div>
        <div class="rounded-xl border border-gray-200 bg-white p-5">
          <div class="text-sm text-gray-400">后端</div>
          <div class="mt-1 font-medium text-gray-900">FastAPI</div>
        </div>
        <div class="rounded-xl border border-gray-200 bg-white p-5">
          <div class="text-sm text-gray-400">检索增强</div>
          <div class="mt-1 font-medium text-gray-900">RAG + 向量检索</div>
        </div>
        <div class="rounded-xl border border-gray-200 bg-white p-5">
          <div class="text-sm text-gray-400">模型推理</div>
          <div class="mt-1 font-medium text-gray-900">Ollama / LangChain</div>
        </div>
      </div>
    </section>

    <section v-else class="rounded-xl border border-gray-200 bg-white p-8 text-center">
      <h2 class="text-lg font-medium text-gray-900">功能建设中</h2>
      <p class="mt-2 text-sm text-gray-500">这个分区还在整理，稍后会继续补齐。</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Button as TButton,
  Dialog as TDialog,
  Input as TInput,
  MessagePlugin,
  Radio as TRadio,
  RadioGroup as TRadioGroup,
  Switch as TSwitch,
  Textarea as TTextarea
} from 'tdesign-vue-next'
import axios from 'axios'

const route = useRoute()
const router = useRouter()
const currentId = computed(() => String(route.params.id ?? '1'))

function readStorage(key: string, fallback = '') {
  if (typeof window === 'undefined') return fallback
  return localStorage.getItem(key) ?? fallback
}

function writeStorage(key: string, value: string) {
  if (typeof window === 'undefined') return
  localStorage.setItem(key, value)
}

const isDark = ref(readStorage('theme') === 'dark')
const activeColor = ref(readStorage('themeColor', 'blue'))
const activeLayout = ref(readStorage('sidebarLayout', 'default'))
const fontSize = ref(readStorage('fontSize', 'md'))

const themeColors = [
  { key: 'blue', label: '科技蓝', value: '#2563eb' },
  { key: 'teal', label: '湖水绿', value: '#0f766e' },
  { key: 'orange', label: '暖橙', value: '#ea580c' },
  { key: 'rose', label: '玫瑰红', value: '#e11d48' }
]
const layoutOptions = [
  { key: 'default', label: '默认布局', desc: '左侧导航 + 主内容区' },
  { key: 'compact', label: '紧凑布局', desc: '更聚焦内容区域' },
  { key: 'top', label: '顶部导航', desc: '适合宽屏场景' }
]
const currentColorLabel = computed(
  () => themeColors.find(color => color.key === activeColor.value)?.label || '科技蓝'
)

function applyDarkMode(value: boolean) {
  isDark.value = value
  document.documentElement.classList.toggle('dark', value)
  writeStorage('theme', value ? 'dark' : 'light')
}

function applyThemeColor(color: (typeof themeColors)[number]) {
  activeColor.value = color.key
  document.documentElement.style.setProperty('--color-primary', color.value)
  writeStorage('themeColor', color.key)
  MessagePlugin.success(`主题颜色已切换为 ${color.label}`)
}

function applyLayout(layoutKey: string) {
  activeLayout.value = layoutKey
  writeStorage('sidebarLayout', layoutKey)
  MessagePlugin.success('布局设置已更新')
}

function applyFontSize(value: string) {
  fontSize.value = value
  const mapping: Record<string, string> = { sm: '13px', md: '14px', lg: '16px' }
  const fontPx = mapping[value] || '14px'
  document.documentElement.style.fontSize = fontPx
  document.documentElement.style.setProperty('--td-font-size-base', fontPx)
  document.body.setAttribute('data-font-size', value)
  writeStorage('fontSize', value)
}

function saveAppearance() {
  applyDarkMode(isDark.value)
  applyFontSize(fontSize.value)
  MessagePlugin.success('外观设置已保存')
}

const thirdPartyList = [
  { key: 'github', label: 'GitHub' },
  { key: 'wechat', label: '微信' },
  { key: 'qq', label: 'QQ' },
  { key: 'feishu', label: '飞书' }
]
const bindingStatus = reactive<Record<string, string>>(
  JSON.parse(readStorage('thirdPartyBindings', '{}'))
)
const bindDialogVisible = ref(false)
const currentProvider = ref<(typeof thirdPartyList)[number] | null>(null)
const bindInput = ref('')

function bindAccount(provider: (typeof thirdPartyList)[number]) {
  currentProvider.value = provider
  bindInput.value = ''
  bindDialogVisible.value = true
}

function confirmBind() {
  if (!bindInput.value.trim() || !currentProvider.value) {
    MessagePlugin.warning('请输入账号标识')
    return
  }
  bindingStatus[currentProvider.value.key] = bindInput.value.trim()
  writeStorage('thirdPartyBindings', JSON.stringify(bindingStatus))
  bindDialogVisible.value = false
  MessagePlugin.success('账号绑定成功')
}

function unbindAccount(provider: (typeof thirdPartyList)[number]) {
  delete bindingStatus[provider.key]
  writeStorage('thirdPartyBindings', JSON.stringify(bindingStatus))
  MessagePlugin.success('账号已解绑')
}

const voiceEnabled = ref(readStorage('voiceEnabled') === 'true')
const isRecording = ref(false)
const transcriptText = ref('')
const voiceStatus = ref('')
let mediaRecorder: MediaRecorder | null = null
let audioChunks: BlobPart[] = []

function onVoiceToggle(value: boolean) {
  voiceEnabled.value = value
  writeStorage('voiceEnabled', String(value))
  MessagePlugin.success(value ? '语音交互已启用' : '语音交互已关闭')
}

async function startRecording() {
  if (isRecording.value) return
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    audioChunks = []
    mediaRecorder = new MediaRecorder(stream)
    mediaRecorder.ondataavailable = event => {
      if (event.data.size > 0) audioChunks.push(event.data)
    }
    mediaRecorder.onstop = async () => {
      const nativeResult = await tryBrowserSpeech()
      if (nativeResult) {
        transcriptText.value = nativeResult
        voiceStatus.value = '识别完成'
      } else {
        voiceStatus.value = '浏览器未返回识别结果'
      }
    }
    mediaRecorder.start()
    isRecording.value = true
    voiceStatus.value = '录音中...'
  } catch {
    MessagePlugin.error('无法访问麦克风，请检查浏览器权限')
  }
}

function stopRecording() {
  if (!mediaRecorder || !isRecording.value) return
  mediaRecorder.stop()
  mediaRecorder.stream.getTracks().forEach(track => track.stop())
  isRecording.value = false
  voiceStatus.value = '正在处理录音...'
}

function tryBrowserSpeech(): Promise<string | null> {
  return new Promise(resolve => {
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SpeechRecognition) {
      resolve(null)
      return
    }

    const recognition = new SpeechRecognition()
    recognition.lang = 'zh-CN'
    recognition.continuous = false
    recognition.interimResults = false

    const timer = setTimeout(() => {
      recognition.stop()
      resolve(null)
    }, 5000)

    recognition.onresult = (event: any) => {
      clearTimeout(timer)
      resolve(event.results[0]?.[0]?.transcript || null)
    }
    recognition.onerror = () => {
      clearTimeout(timer)
      resolve(null)
    }
    recognition.start()
  })
}

function sendTranscript() {
  if (!transcriptText.value) return
  router.push({ path: '/chat', query: { prefill: transcriptText.value } })
}

const newLayoutEnabled = ref(readStorage('newLayoutEnabled') === 'true')
const aiSummaryEnabled = ref(readStorage('aiSummaryEnabled') === 'true')
const summaryInput = ref('')
const summaryResult = ref('')
const summaryLoading = ref(false)

function applyNewLayout(value: boolean) {
  newLayoutEnabled.value = value
  document.body.setAttribute('data-new-layout', value ? 'true' : 'false')
  writeStorage('newLayoutEnabled', String(value))
  MessagePlugin.success(value ? '新布局模式已启用' : '新布局模式已关闭')
}

function onAiSummaryToggle(value: boolean) {
  aiSummaryEnabled.value = value
  writeStorage('aiSummaryEnabled', String(value))
  MessagePlugin.success(value ? 'AI 摘要已启用' : 'AI 摘要已关闭')
}

function clearSummary() {
  summaryInput.value = ''
  summaryResult.value = ''
}

async function generateSummary() {
  if (!summaryInput.value.trim()) {
    MessagePlugin.warning('请先输入需要摘要的文本')
    return
  }
  if (summaryInput.value.length < 50) {
    MessagePlugin.warning('文本太短，无需摘要')
    return
  }

  summaryLoading.value = true
  summaryResult.value = ''
  try {
    const settings = JSON.parse(readStorage('ollamaSettings', '{}'))
    const serverUrl = settings.serverUrl || 'http://localhost:11434'
    const model = readStorage('selected_model', 'qwen2:0.5b')
    const prompt = `请用3-5句话对以下内容进行简洁摘要，只输出摘要内容，不要有任何前缀：\n\n${summaryInput.value.substring(0, 2000)}`
    const response = await fetch(`${serverUrl}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model, prompt, stream: false }),
      signal: AbortSignal.timeout(30000)
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json()
    summaryResult.value = data.response?.trim() || '摘要生成失败'
  } catch {
    const fallback = summaryInput.value
      .replace(/\n+/g, ' ')
      .split(/[。！？?!]/)
      .filter(item => item.trim().length > 5)
      .slice(0, 3)
      .join('。')
      .trim()
    summaryResult.value = fallback ? `${fallback}。` : `${summaryInput.value.substring(0, 100)}...`
    MessagePlugin.info('Ollama 不可用，已生成基础摘要')
  } finally {
    summaryLoading.value = false
  }
}

const feedbackLoading = ref(false)
const feedbackSent = ref(false)
const feedback = reactive({
  type: 'feature',
  title: '',
  content: '',
  email: ''
})

function resetFeedback() {
  feedback.type = 'feature'
  feedback.title = ''
  feedback.content = ''
  feedback.email = ''
  feedbackSent.value = false
}

function openMailto() {
  const subject = encodeURIComponent(`[RAG-F 反馈][${feedback.type}] ${feedback.title}`)
  const body = encodeURIComponent(
    `反馈类型：${feedback.type}\n标题：${feedback.title}\n\n详情：\n${feedback.content}\n\n联系邮箱：${feedback.email}`
  )
  window.open(`mailto:13425121993@163.com?subject=${subject}&body=${body}`, '_blank')
}

async function submitFeedback() {
  if (!feedback.title.trim()) {
    MessagePlugin.warning('请填写标题')
    return
  }
  if (!feedback.content.trim()) {
    MessagePlugin.warning('请填写详细描述')
    return
  }

  feedbackLoading.value = true
  let submitted = false
  try {
    const jwt = readStorage('jwt')
    const response = await axios.post(
      '/api/feedback/submit',
      {
        type: feedback.type,
        title: feedback.title,
        content: feedback.content,
        email: feedback.email,
        to: '13425121993@163.com'
      },
      {
        headers: jwt ? { Authorization: `Bearer ${jwt}` } : {},
        timeout: 8000
      }
    )

    if (response.data?.message === 'email_sent') {
      MessagePlugin.success('反馈已发送给开发者')
    } else {
      openMailto()
    }
    submitted = true
  } catch {
    openMailto()
    submitted = true
  } finally {
    if (submitted) {
      feedbackSent.value = true
      feedback.title = ''
      feedback.content = ''
      feedback.email = ''
    }
    feedbackLoading.value = false
  }
}

onMounted(() => {
  applyDarkMode(isDark.value)
  const savedColor = themeColors.find(color => color.key === activeColor.value)
  if (savedColor) {
    document.documentElement.style.setProperty('--color-primary', savedColor.value)
  }
  applyFontSize(fontSize.value)
  document.body.setAttribute('data-new-layout', newLayoutEnabled.value ? 'true' : 'false')
})

onUnmounted(() => {
  if (mediaRecorder?.state === 'recording') {
    mediaRecorder.stop()
    mediaRecorder.stream.getTracks().forEach(track => track.stop())
  }
})
</script>
