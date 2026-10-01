# 威的成长记录

一个使用 Hugo 构建、通过 GitHub Pages 发布的个人成长网站，包括日记、英语学习、阅读和每日金句。

网站：<https://xiaowei2013-2026.github.io/>

## 内容目录

- `content/diary/`：每日日记
- `content/english/study/`：短文与每日英语学习记录
- `content/english/notes/`：英语笔记
- `content/english/exercises/`：英语题目、错题和解析
- `content/reading/books/分类/`：每本书一个页面，放书籍信息、笔记和读后感
- `content/reading/logs/年/月/`：每本书每天一条记录，按阅读分钟数参与热力图
- `content/reading/other/`：不属于书籍的文章、清单等资料
- `content/quotes/`：每日金句归档

平时可以打开 `日记编辑.code-workspace`、`英语编辑.code-workspace`、`阅读编辑.code-workspace` 或 `金句编辑.code-workspace`，只显示对应内容。

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
.\.tools\hugo\hugo.exe server -D
```

然后打开 `http://localhost:1313/`。

## 同步 Anki 热力图

```powershell
python scripts/sync_anki_stats.py
```

脚本默认统计“英语”及其子牌组，只导出日期、新学数量、复习数量和用时，不上传卡片内容或 Anki 数据库。

创建短文学习记录：

```powershell
.\.tools\hugo\hugo.exe new content english/study/2026/09/2026-09-23.md --kind english-study
```

## 阅读与热力图

阅读内容只写一份，再从两个方向查看：分类书架按书整理，书籍页自动列出读过它的日期；阅读时间线按日期排列，能看到当天读了哪些书。

先在合适的分类下创建书籍页，例如：

```powershell
.\.tools\hugo\hugo.exe new content reading/books/literature/the-little-prince.md --kind reading-book
```

把标题改成真实书名，并填写作者。`book_id` 是这本书的固定编号，例如 `the-little-prince`；今后即使调整分类，也不要改这个编号。已有“文学、人文社科、技术与科学”三个书籍分类，可以自行增加。不属于书籍的资料放在 `content/reading/other/`，不需要 `book_id`。

读完书的当天，为**每本书**写一条记录。文件名以日期开头，后面接书的编号：

```powershell
.\.tools\hugo\hugo.exe new content reading/logs/2026/09/2026-09-30-the-little-prince.md --kind reading-log
```

将记录的 `book_id` 填为 `the-little-prince`，填写 `reading_minutes`，可选填 `pages`，再把标题改成 `2026-09-30 · 小王子`。同一天读了两本书，就创建两个不同文件；热力图会把分钟数相加。书籍页的笔记不会额外计分。阅读 30 分钟达到阅读栏满格；综合热力图按日记 30%、英语 50%、阅读 20% 计算。

书籍和记录创建时默认是草稿。准备公开时，将对应文件的 `draft` 改为 `false`。正式记录关联的书籍也需要公开。发布前运行 `python scripts/check_reading.py`，检查书籍编号、日期和重复记录；GitHub Actions 也会执行这一步。

## 每日金句

金句存放在 `content/quotes/年/月/YYYY-MM-DD.md`，每天一条。文章头填写 `quote`、`author`、`work`、`kind` 和 `date`；正文可以补充感想。首页显示当天的金句，如果当天尚未更新，就显示最近的一条。

```powershell
.\.tools\hugo\hugo.exe new content quotes/2026/10/2026-10-01.md --kind quote
python scripts/check_quotes.py
```

检查脚本会比较去掉空格、标点并统一大小写后的原文，也会检查日期重复。尚未填写原文的草稿会跳过；正式发布的金句必须填写原文和日期。推送后的 GitHub Actions 构建会运行同一检查；重复时构建会失败。金句可以是诗词、名言或电影台词，记得核对原文和出处。

## 首次发布

在 GitHub 仓库中进入 `Settings > Pages`，将 `Source` 设置为 `GitHub Actions`，然后推送 `main` 分支。
