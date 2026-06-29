# 📚 我的知识库

基于 [VitePress](https://vitepress.dev) 构建的个人知识管理系统。

访问地址：**[xiaowei2013-2026.github.io](https://xiaowei2013-2026.github.io)**

## 本地开发

```bash
# 安装依赖
npm install

# 启动开发服务器
npm run docs:dev

# 构建生产版本
npm run docs:build

# 预览构建结果
npm run docs:preview
```

## 部署到 GitHub Pages

```bash
git init
git add .
git commit -m "feat: init knowledge base"
git branch -M main
git remote add origin https://github.com/xiaowei2013-2026/xiaowei2013-2026.github.io.git
git push -u origin main
```

推送后 GitHub Actions 自动构建部署。去仓库 **Settings → Pages** 确认 Source 为 **"GitHub Actions"**。

> 因为仓库名是 `用户名.github.io`，部署后直接通过 `https://xiaowei2013-2026.github.io` 访问，无需路径前缀。

## 项目结构

```
.
├── .github/workflows/deploy.yml  # GitHub Actions 自动部署
├── docs/                         # VitePress 文档根目录
│   ├── .vitepress/
│   │   ├── config.ts             # 站点配置
│   │   └── theme/                # 自定义主题
│   ├── public/                   # 静态资源
│   ├── guide/                    # 学习指南
│   ├── notes/                    # 技术笔记
│   └── skills/                   # 技能工具箱
└── package.json
```

## 技术栈

- ⚡ VitePress — 基于 Vite & Vue 的静态站点生成器
- 📝 Markdown — 内容编写
- 🚀 GitHub Pages — 免费托管
- 🔧 GitHub Actions — 自动部署
