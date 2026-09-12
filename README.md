# 小威的日记

一个使用 Hugo 构建、通过 GitHub Pages 发布的个人公开日记。

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

然后打开 `http://localhost:1313/daily-journal/`。

## 首次发布

在 GitHub 仓库中进入 `Settings > Pages`，将 `Source` 设置为 `GitHub Actions`，然后推送 `main` 分支。

