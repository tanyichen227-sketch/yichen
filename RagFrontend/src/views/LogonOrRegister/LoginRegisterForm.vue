<template>
  <div class="w-full max-w-md mx-auto">
    <div v-if="currentMode !== 'forgot'" class="flex mb-8 bg-white/10 rounded-lg p-1">
      <button
        :class="[
          'flex-1 py-3 px-4 rounded-md text-sm font-medium transition-all duration-300',
          currentMode === 'login'
            ? 'bg-cyan-400 text-white shadow-lg'
            : 'text-white/70 hover:text-white hover:bg-white/10'
        ]"
        @click="switchMode('login')"
      >
        登录
      </button>
      <button
        :class="[
          'flex-1 py-3 px-4 rounded-md text-sm font-medium transition-all duration-300',
          currentMode === 'register'
            ? 'bg-cyan-400 text-white shadow-lg'
            : 'text-white/70 hover:text-white hover:bg-white/10'
        ]"
        @click="switchMode('register')"
      >
        注册
      </button>
    </div>

    <div v-else class="flex items-center mb-8">
      <button
        class="flex items-center text-white/60 hover:text-white transition-colors mr-3"
        @click="backToLogin"
      >
        <svg class="w-5 h-5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
        </svg>
        返回登录
      </button>
      <h2 class="text-xl font-medium text-white">重置密码</h2>
    </div>

    <transition name="form-slide" mode="out-in">
      <form :key="currentMode + '-' + String(forgotDone)" class="space-y-6" @submit.prevent="handleSubmit">
        <div v-if="currentMode === 'login'">
          <h2 class="text-2xl font-medium text-white mb-6 text-center">欢迎回来</h2>

          <div class="mb-4">
            <label class="block text-white/80 text-sm mb-2">邮箱</label>
            <input
              v-model="loginForm.username"
              type="email"
              required
              autocomplete="username"
              class="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-cyan-400 focus:border-transparent transition-all duration-300"
              placeholder="请输入邮箱"
            />
          </div>

          <div class="mb-6">
            <label class="block text-white/80 text-sm mb-2">密码</label>
            <div class="relative">
              <input
                v-model="loginForm.password"
                :type="showPassword ? 'text' : 'password'"
                required
                autocomplete="current-password"
                class="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-cyan-400 focus:border-transparent transition-all duration-300"
                placeholder="请输入密码"
              />
              <button
                type="button"
                class="absolute right-3 top-1/2 transform -translate-y-1/2 text-white/60 hover:text-white transition-colors"
                @click="showPassword = !showPassword"
              >
                <svg
                  v-if="showPassword"
                  class="w-5 h-5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                  />
                </svg>
                <svg v-else class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.878 9.878L3 3m6.878 6.878L21 21"
                  />
                </svg>
              </button>
            </div>
          </div>

          <div class="flex items-center justify-between mb-6">
            <label class="flex items-center">
              <input
                v-model="loginForm.remember"
                type="checkbox"
                class="rounded border-white/20 bg-white/10 text-cyan-400 focus:ring-cyan-400 focus:ring-offset-0"
              />
              <span class="ml-2 text-sm text-white/80">记住我</span>
            </label>
            <button
              type="button"
              class="text-sm text-cyan-400 hover:text-cyan-300 transition-colors"
              @click="showForgotPassword"
            >
              忘记密码？
            </button>
          </div>
        </div>

        <div v-else-if="currentMode === 'register'">
          <div class="mb-4">
            <label class="block text-white/80 text-sm mb-2">邮箱</label>
            <input
              v-model="registerForm.username"
              type="email"
              required
              autocomplete="email"
              class="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-cyan-400 focus:border-transparent transition-all duration-300"
              placeholder="请输入邮箱地址"
            />
          </div>

          <div class="mb-4">
            <label class="block text-white/80 text-sm mb-2">密码</label>
            <div class="relative">
              <input
                v-model="registerForm.password"
                :type="showPassword ? 'text' : 'password'"
                required
                autocomplete="new-password"
                class="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-cyan-400 focus:border-transparent transition-all duration-300"
                placeholder="请输入密码"
              />
              <button
                type="button"
                class="absolute right-3 top-1/2 transform -translate-y-1/2 text-white/60 hover:text-white transition-colors"
                @click="showPassword = !showPassword"
              >
                <svg
                  v-if="showPassword"
                  class="w-5 h-5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                  />
                </svg>
                <svg v-else class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.878 9.878L3 3m6.878 6.878L21 21"
                  />
                </svg>
              </button>
            </div>
          </div>

          <div class="mb-6">
            <label class="block text-white/80 text-sm mb-2">确认密码</label>
            <input
              v-model="registerForm.confirmPassword"
              :type="showPassword ? 'text' : 'password'"
              required
              autocomplete="new-password"
              class="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-cyan-400 focus:border-transparent transition-all duration-300"
              placeholder="请再次输入密码"
              :class="{
                'border-red-400':
                  registerForm.password &&
                  registerForm.confirmPassword &&
                  registerForm.password !== registerForm.confirmPassword
              }"
            />
            <p
              v-if="
                registerForm.password &&
                registerForm.confirmPassword &&
                registerForm.password !== registerForm.confirmPassword
              "
              class="text-red-400 text-xs mt-1"
            >
              两次密码不一致
            </p>
          </div>

          <div class="mb-6">
            <label class="flex items-start">
              <input
                v-model="registerForm.agreeTerms"
                type="checkbox"
                required
                class="rounded border-white/20 bg-white/10 text-cyan-400 focus:ring-cyan-400 focus:ring-offset-0 mt-1"
              />
              <span class="ml-2 text-sm text-white/80">
                我已阅读并同意
                <a href="#" class="text-cyan-400 hover:text-cyan-300 transition-colors">《服务条款》</a>
                和
                <a href="#" class="text-cyan-400 hover:text-cyan-300 transition-colors">《隐私政策》</a>
              </span>
            </label>
          </div>
        </div>

        <div v-else>
          <div v-if="forgotDone" class="text-center py-6 space-y-4">
            <div class="w-16 h-16 bg-green-400/20 rounded-full flex items-center justify-center mx-auto">
              <svg class="w-8 h-8 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p class="text-white text-lg font-medium">密码重置成功</p>
            <p class="text-white/60 text-sm">请使用新密码重新登录</p>
            <button
              type="button"
              class="w-full py-3 px-4 bg-gradient-to-r from-cyan-500 to-blue-500 text-white font-medium rounded-lg shadow-lg hover:from-cyan-600 hover:to-blue-600 transition-all duration-300 transform hover:scale-[1.02]"
              @click="backToLogin"
            >
              返回登录
            </button>
          </div>

          <div v-else class="space-y-5">
            <div>
              <label class="block text-white/80 text-sm mb-2">登录邮箱</label>
              <input
                v-model="forgotForm.email"
                type="email"
                required
                class="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-cyan-400 focus:border-transparent transition-all duration-300"
                placeholder="请输入注册邮箱"
              />
            </div>

            <div>
              <label class="block text-white/80 text-sm mb-2">新密码</label>
              <div class="relative">
                <input
                  v-model="forgotForm.newPassword"
                  :type="showNewPassword ? 'text' : 'password'"
                  class="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-cyan-400 focus:border-transparent transition-all duration-300"
                  placeholder="请输入新密码（至少6位）"
                />
                <button
                  type="button"
                  class="absolute right-3 top-1/2 transform -translate-y-1/2 text-white/60 hover:text-white transition-colors"
                  @click="showNewPassword = !showNewPassword"
                >
                  <svg
                    v-if="showNewPassword"
                    class="w-5 h-5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    <path
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      stroke-width="2"
                      d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                    />
                  </svg>
                  <svg v-else class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      stroke-width="2"
                      d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.878 9.878L3 3m6.878 6.878L21 21"
                    />
                  </svg>
                </button>
              </div>
            </div>

            <div>
              <label class="block text-white/80 text-sm mb-2">确认新密码</label>
              <input
                v-model="forgotForm.confirmPassword"
                :type="showNewPassword ? 'text' : 'password'"
                class="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-lg text-white placeholder-white/50 focus:outline-none focus:ring-2 focus:ring-cyan-400 focus:border-transparent transition-all duration-300"
                :class="{
                  'border-red-400':
                    forgotForm.newPassword &&
                    forgotForm.confirmPassword &&
                    forgotForm.newPassword !== forgotForm.confirmPassword
                }"
                placeholder="请再次输入新密码"
              />
              <p
                v-if="
                  forgotForm.newPassword &&
                  forgotForm.confirmPassword &&
                  forgotForm.newPassword !== forgotForm.confirmPassword
                "
                class="text-red-400 text-xs mt-1"
              >
                两次密码不一致
              </p>
            </div>
          </div>
        </div>

        <button
          v-if="currentMode !== 'forgot' || !forgotDone"
          type="submit"
          :disabled="isSubmitting || !isFormValid"
          class="w-full py-3 px-4 bg-gradient-to-r from-cyan-500 to-blue-500 text-white font-medium rounded-lg shadow-lg hover:from-cyan-600 hover:to-blue-600 focus:outline-none focus:ring-2 focus:ring-cyan-400 focus:ring-offset-2 focus:ring-offset-transparent transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed transform hover:scale-[1.02] active:scale-[0.98]"
        >
          <span v-if="isSubmitting" class="flex items-center justify-center">
            <svg
              class="animate-spin -ml-1 mr-3 h-5 w-5 text-white"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path
                class="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
            {{
              currentMode === 'login'
                ? '登录中...'
                : currentMode === 'register'
                  ? '注册中...'
                  : '重置中...'
            }}
          </span>
          <span v-else>
            {{ currentMode === 'login' ? '登录' : currentMode === 'register' ? '注册' : '确认重置密码' }}
          </span>
        </button>
      </form>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { MessagePlugin } from 'tdesign-vue-next'
import { computed, ref, watch } from 'vue'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').trim()
const apiUrl = (path: string) => `${API_BASE_URL}${path}`

const emit = defineEmits<{
  'image-change': [imageKey: string]
  'form-submit': [data: any]
}>()

const currentMode = ref<'login' | 'register' | 'forgot'>('login')
const showPassword = ref(false)
const showNewPassword = ref(false)
const isSubmitting = ref(false)
const forgotDone = ref(false)

const loginForm = ref({
  username: '',
  password: '',
  remember: false
})

const registerForm = ref({
  username: '',
  password: '',
  confirmPassword: '',
  agreeTerms: false
})

const forgotForm = ref({
  email: '',
  newPassword: '',
  confirmPassword: ''
})

const isEmail = (value: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)

const isFormValid = computed(() => {
  if (currentMode.value === 'login') {
    return isEmail(loginForm.value.username.trim()) && loginForm.value.password.length > 0
  }

  if (currentMode.value === 'register') {
    return (
      isEmail(registerForm.value.username.trim()) &&
      registerForm.value.password.length >= 6 &&
      registerForm.value.password === registerForm.value.confirmPassword &&
      registerForm.value.agreeTerms
    )
  }

  return (
    isEmail(forgotForm.value.email.trim()) &&
    forgotForm.value.newPassword.length >= 6 &&
    forgotForm.value.newPassword === forgotForm.value.confirmPassword
  )
})

const resetForgotForm = () => {
  forgotForm.value = {
    email: '',
    newPassword: '',
    confirmPassword: ''
  }
  forgotDone.value = false
  showNewPassword.value = false
}

const switchMode = (mode: 'login' | 'register') => {
  currentMode.value = mode
  showPassword.value = false
  resetForgotForm()
}

const showForgotPassword = () => {
  currentMode.value = 'forgot'
  resetForgotForm()
  emit('image-change', 'forgot')
}

const backToLogin = () => {
  currentMode.value = 'login'
  resetForgotForm()
  emit('image-change', 'login')
}

const handleSubmit = async () => {
  if (!isFormValid.value || isSubmitting.value) return
  isSubmitting.value = true

  try {
    if (currentMode.value === 'forgot') {
      const res = await fetch(apiUrl('/api/reset/password/email-direct'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: forgotForm.value.email.trim().toLowerCase(),
          new_password: forgotForm.value.newPassword,
          confirm_password: forgotForm.value.confirmPassword
        })
      })
      const data = await res.json()
      if (res.ok && data.status === 'success') {
        forgotDone.value = true
        emit('image-change', 'success')
        MessagePlugin.success('密码已重置，请使用新密码登录')
      } else {
        MessagePlugin.error(data.detail || '重置失败，请稍后重试')
      }
      return
    }

    let response: Response
    if (currentMode.value === 'login') {
      response = await fetch(apiUrl('/api/login/json'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: loginForm.value.username.trim(),
          password: loginForm.value.password
        })
      })
    } else {
      response = await fetch(apiUrl('/api/register'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: registerForm.value.username.trim(),
          password: registerForm.value.password
        })
      })
    }

    const result = await response.json()

    if (result.status === 'success' || result.access_token) {
      const token = result.access_token || result.token
      emit('form-submit', {
        type: currentMode.value,
        email:
          currentMode.value === 'login'
            ? loginForm.value.username.trim()
            : registerForm.value.username.trim(),
        password:
          currentMode.value === 'login' ? loginForm.value.password : registerForm.value.password,
        token
      })
    } else {
      const msg = result.detail || '未知错误'
      MessagePlugin.error(`${currentMode.value === 'login' ? '登录' : '注册'}失败: ${msg}`)
    }

    if (currentMode.value === 'login') {
      loginForm.value = { username: '', password: '', remember: false }
    } else {
      registerForm.value = { username: '', password: '', confirmPassword: '', agreeTerms: false }
    }
  } catch (error) {
    console.error('提交失败:', error)
    MessagePlugin.error('认证过程中发生错误，请稍后重试')
  } finally {
    isSubmitting.value = false
  }
}

watch(
  currentMode,
  newMode => {
    if (newMode !== 'forgot') emit('image-change', newMode)
  },
  { immediate: true }
)
</script>

<style scoped>
.form-slide-enter-active,
.form-slide-leave-active {
  transition: all 0.3s ease-in-out;
}

.form-slide-enter-from {
  opacity: 0;
  transform: translateX(20px);
}

.form-slide-leave-to {
  opacity: 0;
  transform: translateX(-20px);
}

input:focus {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(34, 211, 238, 0.15);
}

button:not(:disabled):hover {
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
}

input[type='checkbox'] {
  width: 16px;
  height: 16px;
}
</style>
