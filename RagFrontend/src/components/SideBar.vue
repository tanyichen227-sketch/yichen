<template>
  <aside :class="['sidebar', { 'sidebar--collapsed': isCollapsed }]">
    <div class="sidebar__logo">
      <div class="sidebar__logo-icon">R</div>
      <span v-if="!isCollapsed" class="sidebar__logo-text">RAGF-01</span>
      <button
        class="sidebar__collapse-btn"
        :title="isCollapsed ? '展开侧边栏' : '折叠侧边栏'"
        @click="toggleCollapse"
      >
        {{ isCollapsed ? '>' : '<' }}
      </button>
    </div>

    <div class="sidebar__quick-action">
      <button
        class="quick-new-btn"
        :title="isCollapsed ? '新建知识库' : ''"
        @click="$emit('quickCreate')"
      >
        <span class="quick-new-icon">+</span>
        <span v-if="!isCollapsed">快速新建</span>
      </button>
    </div>

    <nav class="sidebar__nav">
      <div class="sidebar__nav-section">
        <p v-if="!isCollapsed" class="sidebar__nav-label">主要功能</p>
        <ul class="sidebar__nav-list">
          <li v-for="item in mainNavItems" :key="item.path">
            <t-tooltip :content="isCollapsed ? item.label : ''" placement="right" :show-arrow="false">
              <button
                :class="['nav-item', { 'nav-item--active': isActive(item.path) }]"
                @click="navigateTo(item.path)"
              >
                <span class="nav-item__icon">{{ item.icon }}</span>
                <span v-if="!isCollapsed" class="nav-item__label">{{ item.label }}</span>
                <span v-if="!isCollapsed && item.badge" class="nav-item__badge">{{ item.badge }}</span>
              </button>
            </t-tooltip>
          </li>
        </ul>
      </div>

      <div class="sidebar__nav-section">
        <p v-if="!isCollapsed" class="sidebar__nav-label">工具</p>
        <ul class="sidebar__nav-list">
          <li v-for="item in toolNavItems" :key="item.path">
            <t-tooltip :content="isCollapsed ? item.label : ''" placement="right" :show-arrow="false">
              <button
                :class="['nav-item', { 'nav-item--active': isActive(item.path) }]"
                @click="navigateTo(item.path)"
              >
                <span class="nav-item__icon">{{ item.icon }}</span>
                <span v-if="!isCollapsed" class="nav-item__label">{{ item.label }}</span>
              </button>
            </t-tooltip>
          </li>
        </ul>
      </div>
    </nav>

    <div class="sidebar__footer">
      <button class="nav-item" :title="isCollapsed ? '搜索' : ''" @click="$emit('openSearch')">
        <span class="nav-item__icon">🔎</span>
        <span v-if="!isCollapsed" class="nav-item__label">搜索</span>
      </button>

      <button
        class="nav-item"
        :title="locale === 'zh' ? 'Switch to English' : '切换中文'"
        @click="handleToggleLocale"
      >
        <span class="nav-item__icon">🌐</span>
        <span v-if="!isCollapsed" class="nav-item__label">{{ locale === 'zh' ? 'EN' : '中文' }}</span>
      </button>

      <t-dropdown :min-column-width="160" trigger="click" placement="right-bottom">
        <div :class="['user-info', { 'user-info--collapsed': isCollapsed }]">
          <t-avatar :image="userAvatar" :hide-on-load-failed="false" size="small" class="user-avatar" />
          <div v-if="!isCollapsed" class="user-meta">
            <span class="user-name">{{ userName }}</span>
            <span class="user-email">{{ userEmail }}</span>
          </div>
        </div>
        <template #dropdown>
          <t-dropdown-menu>
            <t-dropdown-item @click="navigateTo('/user/userInfo')">
              <t-icon name="user" />
              <span class="ml-2">个人中心</span>
            </t-dropdown-item>
            <t-dropdown-item @click="navigateTo('/devtools')">
              <t-icon name="code" />
              <span class="ml-2">开发者模式</span>
            </t-dropdown-item>
            <t-dropdown-item divided class="text-red-500" @click="logout">
              <t-icon name="logout" />
              <span class="ml-2">退出登录</span>
            </t-dropdown-item>
          </t-dropdown-menu>
        </template>
      </t-dropdown>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { MessagePlugin } from 'tdesign-vue-next'
import { useDataUserStore } from '@/store'
import API_ENDPOINTS from '@/utils/apiConfig'
import { useI18n, locale as _locale } from '@/i18n'

interface NavItem {
  path: string
  label: string
  icon: string
  badge?: string
}

defineEmits(['openSearch', 'quickCreate'])

const router = useRouter()
const route = useRoute()
const userStore = useDataUserStore()
const isCollapsed = ref(false)

const { toggleLocale } = useI18n()
const locale = _locale

const handleToggleLocale = () => {
  toggleLocale()
  MessagePlugin.success(locale.value === 'en' ? 'Language: English' : '语言：中文')
}

const toggleCollapse = () => {
  isCollapsed.value = !isCollapsed.value
}

const isActive = (path: string) => {
  if (path === '/chat') return route.path.startsWith('/chat')
  if (path === '/user') return route.path.startsWith('/user')
  return route.path === path || route.path.startsWith(path + '/')
}

const navigateTo = (path: string) => router.push(path)

const logout = async () => {
  await router.push('/LogonOrRegister')
  MessagePlugin.success('已退出账号')
}

const userAvatar = computed(() => {
  if (!userStore.userData) return 'https://tdesign.gtimg.com/site/avatar.jpg'
  const avatar = userStore.userData?.avatar || ''
  if (avatar && avatar.startsWith('/static/')) return API_ENDPOINTS.USER.AVATAR(avatar)
  return avatar || 'https://tdesign.gtimg.com/site/avatar.jpg'
})

const userName = computed(() => userStore.userData?.name || userStore.userData?.email?.split('@')[0] || '用户')

const userEmail = computed(() => {
  const email = userStore.userData?.email || ''
  if (email.length > 18) return email.substring(0, 15) + '...'
  return email
})

onMounted(async () => {
  try {
    await userStore.fetchUserData()
  } catch {
    // ignore
  }
})

const mainNavItems: NavItem[] = [
  { path: '/knowledge', label: '知识库', icon: '📚' },
  { path: '/chat', label: 'AI 对话', icon: '💬' },
  { path: '/agent', label: '任务模式', icon: '🧠', badge: 'Beta' }
]

const toolNavItems: NavItem[] = [
  { path: '/history', label: '历史记录', icon: '🕘' },
  { path: '/creation', label: '文档创作', icon: '📝', badge: 'New' },
  { path: '/files', label: '文件管理', icon: '📁' },
  { path: '/service', label: '模型管理', icon: '🧩' },
  { path: '/settings', label: '系统设置', icon: '⚙️' }
]
</script>

<style scoped>
.sidebar {
  width: 240px;
  height: 100vh;
  background: #fff;
  border-right: 1px solid #f0f0f0;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  transition: width 0.25s ease;
  overflow: hidden;
}

.sidebar--collapsed {
  width: 64px;
}

.sidebar__logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 10px;
  border-bottom: 1px solid #f5f5f5;
}

.sidebar__logo-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: linear-gradient(135deg, #4f7ef8, #8b5cf6);
  font-weight: 700;
}

.sidebar__logo-text {
  font-size: 14px;
  font-weight: 700;
  color: #111827;
}

.sidebar__collapse-btn {
  margin-left: auto;
  width: 26px;
  height: 26px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
}

.sidebar__quick-action {
  padding: 10px;
  border-bottom: 1px solid #f8fafc;
}

.quick-new-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px 10px;
  border: none;
  border-radius: 10px;
  color: #fff;
  background: linear-gradient(135deg, #2563eb, #0ea5e9);
  cursor: pointer;
}

.quick-new-icon {
  font-size: 16px;
  font-weight: 700;
}

.sidebar__nav {
  flex: 1;
  overflow-y: auto;
  padding: 10px 8px;
}

.sidebar__nav-section + .sidebar__nav-section {
  margin-top: 12px;
}

.sidebar__nav-label {
  margin: 6px 10px;
  font-size: 11px;
  color: #9ca3af;
}

.sidebar__nav-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.nav-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #374151;
  cursor: pointer;
}

.nav-item:hover {
  background: #f3f4f6;
}

.nav-item--active {
  background: #eef2ff;
  color: #1f2937;
}

.nav-item__icon {
  width: 18px;
  text-align: center;
}

.nav-item__label {
  flex: 1;
  text-align: left;
  font-size: 13px;
}

.nav-item__badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 999px;
  color: #fff;
  background: #6366f1;
}

.sidebar__footer {
  padding: 8px;
  border-top: 1px solid #f5f5f5;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
}

.user-info:hover {
  background: #f3f4f6;
}

.user-info--collapsed {
  justify-content: center;
}

.user-meta {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.user-name {
  font-size: 12px;
  color: #111827;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-email {
  font-size: 11px;
  color: #6b7280;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
