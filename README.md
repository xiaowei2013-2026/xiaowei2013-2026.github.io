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

工作区文件统一放在 `growth-workspace/` 中。平时双击对应的 `日记编辑.code-workspace`、`英语编辑.code-workspace`、`阅读编辑.code-workspace`、`金句编辑.code-workspace` 或 `其他编辑.code-workspace`，只显示对应内容。也可以在 VS Code 中选择“文件 → 从文件打开工作区”。这些工作区直接编辑项目原文件，后续内容修改在对应工作区内完成即可；修改站点配置、模板或样式时，打开整个项目文件夹。

## 本地网页编辑

在项目根目录运行 `.\preview.cmd`，打开 `http://localhost:1313/`，在同一页面预览和编辑。脚本自动启动 Hugo 和本地编辑服务，不用另开 `hugo server`；原来的 `preview-editor.cmd` 也启动同一个服务，也可使用 Python 3.10 及以上运行 `python editor/server.py`。仅监听本机，公开网站仍使用 GitHub Pages，线上构建不显示编辑入口。

打开本地网页即可新建、编辑和删除，无需密码或登录。编辑服务只监听 `127.0.0.1`，保留 Host、请求来源和随机请求令牌校验，避免其他网页擅自调用写入接口。正式构建不启用编辑入口，也不部署这些本地接口。

可修改文章标题和正文、上传或粘贴图片，点击“保存到本地”写回 Markdown。保存后等待 Hugo 更新，再显示原网站排版。含 Hugo shortcode 图表的页面暂不支持正文可视化保存。

新建或编辑文章时，在“封面图片”中选择本地 PNG、JPEG、WebP（最大 8 MB），先预览，点击保存后复制原始图片，正文不会自动插图。日记等 `index.md` 文章的封面放在同一文章目录，以 `feature-editor-…` 命名，并通过文章头的 `featureimage` 指定；普通单文件文章使用 `assets/editor-covers/`。封面显示在文章列表，保存封面时设置 `showHero: false`，正文顶部不额外展示大图。不选新图时保留原封面；“取消选择”只取消本次选择。原图片不压缩、不改字节，更换封面保留旧图；保存前取消不会把封面写入项目。

新建位置由当前页面决定，不再选择分类。例如在 `/reading/books/technology/` 点击“新建文章”，生成 `content/reading/books/technology/日期-标识/index.md`，直接放在当前分类目录，不额外套年/月目录。在某篇文章页新建，放在该文章所属目录；首页新建放在 `content/` 根目录。标签等没有对应内容文件夹的页面不提供新建入口。写好后保存才创建文件，取消不会产生空文章。

点击“新建分类”，填写分类名称，可选填写目录名与说明，保存后自动进入新分类。例如在 `/other/` 下以 `tools` 为目录名创建“工具”，会生成 `content/other/tools/_index.md`，并在已有父栏目页面追加入口，保留原有内容。目录名留空会自动生成；重名目录拒绝覆盖。支持继续在新分类里创建子分类和文章，所有修改仅保存在本地。

进入网页新建的分类后，顶部有“删除分类”。确认后仅删除空分类及父页面上的对应入口，返回父栏目（首页创建的分类返回首页）。分类里仍有文章、子分类或附件时拒绝删除；可清理没有文件的空目录。原有栏目和首页不提供删除入口。分类文件已被其他编辑器修改时，需要刷新后再试。

书籍目录下自动生成 `entry_type: book` 和稳定的 `book_id`，可以填写作者、阅读状态。金句目录下填写原文、作者、出处和类型，并检查日期与原文重复。阅读记录目录下填写已有书籍的 `book_id`、分钟数和页数。文章默认 `draft: false`，本地与线上使用同一公开内容规则。

“删除文章”确认后直接删除本地 Markdown，图片和附件保留，返回所属栏目。不设回收站；已提交过的文件可以通过 Git 恢复，未提交的新文件删除后无法通过 Git 找回。栏目 `_index.md` 不允许删除；文件被其他编辑器修改时拒绝覆盖或删除。原有历史回收站文件保留在 `.tools/` 中，新功能不再使用它们。

网页只读写本地内容，不运行 Git 同步。写作完成后，在终端统一检查改动并 commit、push。GitHub Actions 部署成功后，线上才会更新。

编辑器组件固定为 TOAST UI Editor 3.2.2，进入编辑时才从本地加载，关闭使用统计。保存前的文件备份在 `.tools/editor-backups/`；预览构建在 `.tools/editor-site/`，均不上传 GitHub。图片支持 PNG、JPEG、WebP（最大 8 MB），保留原始字节；取消编辑不会自动删除已上传图片。

## 写一篇新日记

在 `content/diary/年/月/` 中复制一篇现有日记并修改内容。文件名建议使用 `YYYY-MM-DD.md`。

本站内容默认公开，新建模板使用 `draft: false`，不区分草稿预览和正式预览。

图片放在 `static/images/年/月/`，文章内写：

```markdown
![图片说明](/images/2026/09/example.webp)
```

提交并推送到 `main` 分支后，GitHub Actions 会自动构建网站。

## 本地预览

项目已提供预览脚本，在项目目录运行：

当前本地 Hugo 为 `0.166.0`，GitHub Actions 也固定为该版本。后续升级时同步修改线上构建版本。

```powershell
.\preview.cmd
```

然后打开 `http://localhost:1313/`，既可预览，也可直接新建、编辑和删除内容。

也可以在任意编辑工作区中执行“终端 → 运行任务 → 预览网站”，或双击项目根目录的 `preview.cmd`。预览使用与线上发布相同的 `production` 环境和压缩设置，并关闭快速渲染以便完整更新页面。所有文章按公开内容管理，本地和线上使用同一套内容规则。同一时间只运行一个预览任务，启动前先结束旧任务；修改任务配置后，已运行的预览服务也需要重新启动。

本地显示当前磁盘上的文件，线上显示最近一次成功部署的版本。本地修改会触发预览更新，但只有提交并推送到 `main`，且 GitHub Actions 部署成功后，线上才会更新。保持两边的内容、数据、Hugo/主题版本及构建日期一致，才能获得一致的展示；本地地址、实时刷新和线上域名会有所不同。

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

书籍和记录创建时默认公开。填写完整书籍信息及阅读记录后，发布前运行 `python scripts/check_reading.py`，检查书籍编号、日期和重复记录；GitHub Actions 也会执行这一步。

## 每日金句

金句存放在 `content/quotes/年/月/YYYY-MM-DD.md`，每天一条。文章头填写 `quote`、`author`、`work`、`kind` 和 `date`；正文可以补充感想。首页显示当天的金句，如果当天尚未更新，就显示最近的一条。

```powershell
.\.tools\hugo\hugo.exe new content quotes/2026/10/2026-10-01.md --kind quote
python scripts/check_quotes.py
```

检查脚本会比较去掉空格、标点并统一大小写后的原文，也会检查日期重复。尚未填写原文的草稿会跳过；正式发布的金句必须填写原文和日期。推送后的 GitHub Actions 构建会运行同一检查；重复时构建会失败。金句可以是诗词、名言或电影台词，记得核对原文和出处。

## 首次发布

在 GitHub 仓库中进入 `Settings > Pages`，将 `Source` 设置为 `GitHub Actions`，然后推送 `main` 分支。
