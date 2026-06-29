import { defineConfig } from 'vitepress'

// https://vitepress.dev/reference/site-config
export default defineConfig({
  title: '肖威的知识库',
  description: '个人知识管理系统',
  lang: 'zh-CN',
  base: '/',  // 用户名.github.io 仓库直接使用根路径

  // 清理 URL（去掉 .html 后缀）
  cleanUrls: true,

  // 头部配置
  head: [
    ['link', { rel: 'icon', href: '/favicon.ico' }],
  ],

  // 主题配置
  themeConfig: {
    // 站点 logo
    logo: '📚',

    // 导航栏
    nav: [
      { text: '首页', link: '/' },
      { text: '刻己', link: '/engravings/' },
      { text: '工作', link: '/work/' },
      { text: '阅读', link: '/reading/' },
      { text: '其他', link: '/other/' },
    ],

    // 侧边栏
    sidebar: {
      '/engravings/': [
        {
          text: '刻己',
          items: [
            { text: '概览', link: '/engravings/' },
            { text: '什么才算"做完了"', link: '/engravings/2026-06-26-done' },
            { text: '第一步总是最重的', link: '/engravings/2026-06-20-first-step' },
          ],
        },
      ],
      '/work/': [
        {
          text: '工作',
          items: [
            { text: '概览', link: '/work/' },
            { text: '滴滴工作', link: '/work/didi/' },
            { text: '后端开发', link: '/work/backend/' },
            { text: 'AI', link: '/work/ai/' },
            { text: '工具链', link: '/work/toolchain/' },
          ],
        },
      ],
      '/reading/': [
        {
          text: '阅读',
          items: [
            { text: '概览', link: '/reading/' },
          ],
        },
      ],
      '/other/': [
        {
          text: '其他',
          items: [
            { text: '概览', link: '/other/' },
          ],
        },
      ],
    },

    // 社交链接
    socialLinks: [
      { icon: 'github', link: 'https://github.com/xiaowei2013-2026/xiaowei2013-2026.github.io' },
    ],

    // 页脚
    footer: {
      message: '基于 VitePress 构建',
      copyright: 'Copyright © 2026',
    },

    // 搜索
    search: {
      provider: 'local',
      options: {
        translations: {
          button: {
            buttonText: '搜索',
            buttonAriaLabel: '搜索文档',
          },
          modal: {
            noResultsText: '无法找到相关结果',
            resetButtonTitle: '清除查询条件',
            footer: {
              selectText: '选择',
              navigateText: '切换',
              closeText: '关闭',
            },
          },
        },
      },
    },

    // 编辑链接
    editLink: {
      pattern: 'https://github.com/xiaowei2013-2026/xiaowei2013-2026.github.io/edit/main/docs/:path',
      text: '在 GitHub 上编辑此页',
    },

    // 最后更新时间
    lastUpdated: {
      text: '最后更新于',
    },

    // 大纲标题
    outline: {
      label: '页面导航',
      level: [2, 3],
    },

    // 文档页脚（上一篇/下一篇）
    docFooter: {
      prev: '上一页',
      next: '下一页',
    },

    // 暗色模式
    darkModeSwitchLabel: '主题',
    lightModeSwitchTitle: '切换到浅色模式',
    darkModeSwitchTitle: '切换到深色模式',
    sidebarMenuLabel: '菜单',
    returnToTopLabel: '回到顶部',
  },

  // Markdown 配置
  markdown: {
    lineNumbers: true,
    image: {
      lazyLoading: true,
    },
  },
})
