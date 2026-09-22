# 威的成长记录

一个使用 Hugo 构建、通过 GitHub Pages 发布的个人成长网站，目前包括日记和英语学习。

网站：<https://xiaowei2013-2026.github.io/>

## 内容目录

- `content/diary/`：每日日记
- `content/english/study/`：短文与每日英语学习记录
- `content/english/notes/`：英语笔记
- `content/english/exercises/`：英语题目、错题和解析

平时可以打开 `日记编辑.code-workspace` 或 `英语编辑.code-workspace`，只显示对应内容。

## 写一篇新日记

在 `content/diary/年/月/` 中复制一篇现有日记并修改内容。文件名建议使用 `YYYY-MM-DD.md`。

文章开头的 `draft`：

- `true`：草稿，不会公开发布
- `false`：正式公开

图片放在 `static/images/年/月/`，文章内写：

```markdown
![图片说明](/images/2026/09/example.webp)
```

提交并推送到 `main` 分支后，GitHub Actions 会自动构建网站。

## 本地预览

安装 Hugo Extended 后，在项目目录运行：

```powershell
hugo server -D
```

然后打开 `http://localhost:1313/`。

## 同步 Anki 热力图

```powershell
python scripts/sync_anki_stats.py
```

脚本默认统计“英语”及其子牌组，只导出日期、新学数量、复习数量和用时，不上传卡片内容或 Anki 数据库。

创建短文学习记录：

```powershell
hugo new content english/study/2026/09/2026-09-23.md --kind english-study
```

## 首次发布

在 GitHub 仓库中进入 `Settings > Pages`，将 `Source` 设置为 `GitHub Actions`，然后推送 `main` 分支。
