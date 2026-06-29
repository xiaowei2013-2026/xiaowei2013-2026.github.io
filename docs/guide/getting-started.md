# 快速开始

本指南将帮助你从零搭建自己的 VitePress 知识库。

## 前提条件

- **Node.js** 18 或更高版本
- 基本的 **Markdown** 语法知识
- 一个 **GitHub** 账号

## 第一步：创建项目

```bash
# 创建项目目录
mkdir my-knowledge-base
cd my-knowledge-base

# 初始化 npm 项目
npm init -y

# 安装 VitePress
npm install -D vitepress
```

## 第二步：配置 VitePress

创建 `docs/.vitepress/config.ts`：

```ts
import { defineConfig } from 'vitepress'

export default defineConfig({
  title: '我的知识库',
  description: '个人知识管理系统',
  lang: 'zh-CN',

  themeConfig: {
    nav: [
      { text: '首页', link: '/' },
      { text: '指南', link: '/guide/' },
    ],

    sidebar: {
      '/guide/': [
        {
          text: '学习指南',
          items: [
            { text: '快速开始', link: '/guide/getting-started' },
          ],
        },
      ],
    },

    search: {
      provider: 'local',  // 本地搜索
    },
  },
})
```

## 第三步：添加启动脚本

在 `package.json` 中添加：

```json
{
  "scripts": {
    "docs:dev": "vitepress dev docs",
    "docs:build": "vitepress build docs",
    "docs:preview": "vitepress preview docs"
  }
}
```

## 第四步：启动开发服务器

```bash
npm run docs:dev
```

浏览器打开 `http://localhost:5173` 即可看到你的知识库！

## 下一步

- 学习 [Markdown 语法](/notes/markdown-demo) 写出漂亮文档
- 探索 [VitePress 功能](/notes/vitepress-features) 挖掘更多可能性
- 配置 [GitHub Pages 部署](#) 让你的知识库上线
