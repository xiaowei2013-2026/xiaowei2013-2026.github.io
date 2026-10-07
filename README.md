# 威的成长记录

一个使用 Hugo 构建、通过 GitHub Pages 发布的个人成长网站，包括日记、英语学习、阅读和每日金句。

网站：<https://xiaowei2013-2026.github.io/>

## 编辑方式与分支

默认分支 `main` 在本地编辑 Markdown，运行 `.\preview.cmd` 后通过 `http://localhost:1313/` 预览，网页不提供编辑按钮。完成修改后统一 commit、push。

`web-editor` 分支保留网页编辑、新建和删除文章、分类管理、封面选择等功能，作为另一种编辑方式。需要使用时先停止预览，再运行 `git switch web-editor` 和 `.\preview.cmd`；返回 Markdown 编辑时停止预览，运行 `git switch main`。切换前请先提交当前修改。两个分支的后续内容改动需要通过 Git 合并，不会自动同步。GitHub Pages 仍只从 `main` 发布。

## 内容目录

- `content/diary/`：每日日记
- `content/english/recitation/`：主题 Markdown 和背诵记录 JSON 放在同一层，一个 Markdown 文档可以放多篇短文，每篇标注背诵日期
- `content/english/recitation/recitation-records.json`：手动填写日期和背诵文章名，供热力图读取
- `content/english/notes/`：英语笔记
- `content/english/exercises/`：英语题目、错题和解析
- `content/reading/分类/`：每本书或文章一个 Markdown，放内容、笔记和读后感；实际文件夹名见下文
- `content/reading/reading-records.json`：手动记录日期和读了哪些书／文章，供热力图读取
- `content/reading/other/`：其他类别的书籍、文章、清单等资料
- `content/quotes/`：每日金句归档
- `content/other/分类/`：其他兴趣的文档和图表，按分类组织，不按年份分组。分类说明和图表可写在 `_index.md` 中，具体文档放在该分类目录下。

工作区文件统一放在 `growth-workspace/` 中。平时双击对应的 `日记编辑.code-workspace`、`英语编辑.code-workspace`、`阅读编辑.code-workspace`、`金句编辑.code-workspace` 或 `其他编辑.code-workspace`，只显示对应内容。也可以在 VS Code 中选择“文件 → 从文件打开工作区”。这些工作区直接编辑项目原文件，后续内容修改在对应工作区内完成即可；修改站点配置、模板或样式时，打开整个项目文件夹。

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

然后打开 `http://localhost:1313/`。

也可以在任意编辑工作区中执行“终端 → 运行任务 → 预览网站”，或双击项目根目录的 `preview.cmd`。预览使用与线上发布相同的 `production` 环境和压缩设置，并关闭快速渲染以便完整更新页面。所有文章按公开内容管理，本地和线上使用同一套内容规则。同一时间只运行一个预览任务，启动前先结束旧任务；修改任务配置后，已运行的预览服务也需要重新启动。

本地显示当前磁盘上的文件，线上显示最近一次成功部署的版本。本地修改会触发预览更新，但只有提交并推送到 `main`，且 GitHub Actions 部署成功后，线上才会更新。保持两边的内容、数据、Hugo/主题版本及构建日期一致，才能获得一致的展示；本地地址、实时刷新和线上域名会有所不同。

## 英语笔记的图片

英语笔记保留原来的 Markdown 文件名，图片统一放在 `content/english/notes/图片和附件/`。图片按“整理日期＋序号”命名，例如 `20261006-001.png`；日期表示整理日期，不代表图片拍摄日期。同一天新增图片继续使用未占用的序号，文档引用写作 `![说明](图片和附件/20261006-001.png)`，无需为每篇笔记创建图片文件夹。

## 五笔笔记与图表

五笔分类首页只展示入口。学习笔记在 `content/other/typing/wubi-notes/index.md`，打字速度图表在 `content/other/typing/typing-speed/index.md`。这两页显示最后更新时间：已提交文件取该文件最近一次 Git 提交的时间，未提交过的新文件回退到文件修改时间；不用填写虚构的发布日期。已跟踪文件的更新时间在提交后更新，本地和线上采用同一规则。

图表记录直接编辑 `content/other/typing/typing-speed/type-records.json`，与图表 Markdown 放在同一目录。每条记录包含 `time`（北京时间 `YYYY-MM-DD HH:mm`）、`speed`（字/分钟）和 `content`（练习内容），保存后本地预览更新，提交并推送后线上更新。图表标题、说明在同目录的 `index.md` 中修改，配色和样式在 `assets/css/typing-chart.css`，绘图逻辑在 `assets/js/typing-chart.js`。

## 同步 Anki 热力图

```powershell
python scripts/sync_anki_stats.py
```

脚本默认统计“英语”及其子牌组，只导出日期、新学数量、复习数量和用时，不上传卡片内容或 Anki 数据库。

## 背诵材料与热力图

材料按主题直接放在 `content/english/recitation/`，例如 `关于梦想.md`，无需额外的 `materials` 或每日记录目录。同一文档内可以添加多篇短文，每篇使用 `## 短文名称`，下面写 `背诵日期：2026-10-06`，再写英文原文、翻译或笔记。无需每天新建一个 Markdown 记录。

热力图只读取 `content/english/recitation/recitation-records.json` 中的背诵记录，不自动扫描文档里的日期。手动维护，日期使用 `YYYY-MM-DD`，每个日期对应当天背诵的文章名列表。同一天多篇文章写在同一个列表中，复习时也可以在新的日期下再次填写同一篇文章名；顺序不影响显示。

```json
{
  "2026-10-06": ["梦想的力量"],
  "2026-10-07": ["梦想的力量", "另一篇短文"]
}
```

上面第二天是格式示例，不是实际记录。每个日期只写一次，列表里每篇文章只写一次。保存有效 JSON 后本地预览更新；修改 Markdown 中的日期不会自动修改 JSON，需要分别维护。鼠标悬停显示当天的文章名，点击跳转到背诵材料目录。Anki 和日记仍使用各自原有的数据来源，阅读 JSON 的用法见下文。

## 阅读与热力图

阅读下面直接放分类：`literature/`（文学）、`humanities/`（人文社科）、`technology/`（技术与科学）和 `other/`（其他）。没有额外的分类书架或阅读时间线目录。书籍、文章与笔记直接保存在对应分类中，原有内容保留；旧书架分类网址会跳转到新分类。

先在合适的分类下创建书籍页，例如：

```powershell
.\.tools\hugo\hugo.exe new content reading/literature/小王子.md --kind reading-book
```

把 `title` 改成真实书名，作者等信息按需要填写，正文持续补充笔记。也可以直接复制已有 Markdown 来写文章，不需要 `book_id`。分类卡片不按年份分组，显示最后修改日期。

每日阅读只维护 `content/reading/reading-records.json`，格式与背诵记录一样，只写日期和读了哪些书／文章，无需填写分钟数、页数，也无需新建每日 Markdown。例如：

```json
{
  "2026-10-06": ["小王子", "40 条生活建议摘录"],
  "2026-10-07": ["小王子"]
}
```

上面是格式示例，实际文件初始为 `{}`，不包含虚构的阅读记录。同一天读多个内容，放在同一个列表里；继续读同一本书时，在新日期下再次填写书名。日期顺序不影响显示，每个日期及当天的名称不重复填写。没有本站笔记页的书名也可以记录。

热力图中，当天有阅读记录就点亮，悬停显示当天书名／文章名，不再计算阅读分钟数和页数。点击会打开名称与文档 `title` 对应的阅读页面，找不到对应页面时打开阅读首页。综合热力图仍按日记 30%、英语 50%、阅读 20% 计算。

书籍模板保留可选的 `{{< reading-history >}}`，会从 JSON 中读取与页面 `title` 相同的名称，按日期从新到旧列出读过它的日子。重命名页面标题时，同步修改 JSON 中对应名称。此列表就在书籍正文里，无需单独的时间线页面。

保存 JSON 后本地预览更新，commit、push 后线上更新。发布前运行 `python scripts/check_reading.py`，检查 JSON 格式、有效日期、空名称及重复记录；GitHub Actions 也会执行这一步。

阅读和背诵的 JSON 由 `hugo.yaml` 中的数据挂载配置加载，仍直接编辑原来的文件。修改 JSON 会触发热力图和书籍阅读日期的重新渲染，无需修改 Markdown 或每次重启预览。若首次更改挂载配置后旧进程没有自动重载，停止预览后重新运行 `.\preview.cmd` 即可。

## 体重记录

在“其他 → 健康 → 体重记录”查看变化曲线。直接编辑 `content/other/health/weight-records.json`，每条只需 `time`（时间）和 `weight`（体重，单位为公斤），例如：

```json
[
  { "time": "2026-10-07", "weight": 65.25 },
  { "time": "2026-10-08 07:30", "weight": 65 }
]
```

以上只是格式示例。时间可精确到日期或分钟，体重按公斤填写数字，支持小数。页面自动乘以 2，曲线、数据点详情和表格统一显示斤，例如 65.25 公斤显示为 130.5 斤。记录顺序可随意调整，图表自动按时间排序。保存后本地预览更新，提交并推送后线上更新。曲线纵轴根据数据调整范围，不一定从 0 开始。

## 每日金句

金句存放在 `content/quotes/年/月/YYYY-MM-DD.md`，每天一条。文章头填写 `quote`、`author`、`work`、`kind` 和 `date`；正文可以补充感想。首页显示当天的金句，如果当天尚未更新，就显示最近的一条。

```powershell
.\.tools\hugo\hugo.exe new content quotes/2026/10/2026-10-01.md --kind quote
python scripts/check_quotes.py
```

检查脚本会比较去掉空格、标点并统一大小写后的原文，也会检查日期重复。尚未填写原文的草稿会跳过；正式发布的金句必须填写原文和日期。推送后的 GitHub Actions 构建会运行同一检查；重复时构建会失败。金句可以是诗词、名言或电影台词，记得核对原文和出处。

## 首次发布

在 GitHub 仓库中进入 `Settings > Pages`，将 `Source` 设置为 `GitHub Actions`，然后推送 `main` 分支。
