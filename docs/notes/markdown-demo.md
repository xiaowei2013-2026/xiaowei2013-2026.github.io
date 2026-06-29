# Markdown 语法示例

本页面展示 VitePress 支持的各种 Markdown 语法。

[[toc]]

## 基础语法

### 标题

```md
# 一级标题
## 二级标题
### 三级标题
#### 四级标题
```

### 文本样式

- **粗体文字** — `**粗体文字**`
- *斜体文字* — `*斜体文字*`
- ~~删除线~~ — `~~删除线~~`
- `行内代码` — `` `行内代码` ``
- [链接](https://vitepress.dev) — `[链接](https://vitepress.dev)`

### 列表

**无序列表：**

- 第一项
- 第二项
  - 嵌套子项
  - 另一个子项
- 第三项

**有序列表：**

1. 第一步
2. 第二步
3. 第三步

### 引用

> 这是一段引用文字。
>
> 引用可以跨多行。
>
> > 也可以嵌套引用。

### 分割线

---

## 代码块

### 带语法高亮

```ts
// TypeScript 示例
interface User {
  name: string
  age: number
  skills: string[]
}

function greet(user: User): string {
  return `你好，${user.name}！`
}

console.log(greet({ name: '小明', age: 25, skills: ['Vue', 'React'] }))
```

```python
# Python 示例
def fibonacci(n: int) -> list[int]:
    """生成斐波那契数列"""
    result = [0, 1]
    for i in range(2, n):
        result.append(result[i-1] + result[i-2])
    return result

print(fibonacci(10))  # [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]
```

### 带行号

```ts:line-numbers
// 行号示例
const greeting = 'Hello, World!'
const count = 42
console.log(greeting)
console.log(`Count: ${count}`)
```

### 代码组（多语言切换）

::: code-group

```js [JavaScript]
const greeting = 'Hello, World!'
console.log(greeting)
```

```ts [TypeScript]
const greeting: string = 'Hello, World!'
console.log(greeting)
```

```py [Python]
greeting = 'Hello, World!'
print(greeting)
```

:::

### 高亮特定行

```ts{2,4-5}
function main() {
  const app = createApp()      // 高亮
  app.use(router)
  app.mount('#app')            // 高亮
}                              // 高亮
```

## 表格

| 框架 | 版本 | 类型 | 生态评级 |
|------|------|------|----------|
| Vue | 3.x | 渐进式框架 | ⭐⭐⭐⭐⭐ |
| React | 19.x | UI 库 | ⭐⭐⭐⭐⭐ |
| Svelte | 5.x | 编译器框架 | ⭐⭐⭐⭐ |
| Solid | 1.x | 响应式库 | ⭐⭐⭐⭐ |

## 提示框

::: tip 提示
这是一个 **提示** 框，用于分享有用的信息。
:::

::: info 信息
这是一个 **信息** 框，提供额外上下文。
:::

::: warning 警告
这是一个 **警告** 框，提醒用户注意潜在问题。
:::

::: danger 危险
这是一个 **危险** 框，警告用户不要执行某些操作。
:::

::: details 点击展开
这里是折叠的详细内容，点击标题可以展开/收起。

- 可以包含列表
- 代码块等任意内容

```js
console.log('折叠区域内的代码')
```
:::

## 图片

![VitePress Logo](https://vitepress.dev/vitepress-logo-mini.svg)

## Emoji 🎉

:smile: :heart: :rocket: :books: :bulb: :zap:

## 任务列表

- [x] 学习 VitePress 基础
- [x] 配置导航和侧边栏
- [ ] 部署到 GitHub Pages
- [ ] 自定义主题

## 脚注

VitePress 使用 Markdown-it 作为解析器[^1]，支持丰富的插件生态[^2]。

[^1]: Markdown-it 是一个快速、可扩展的 Markdown 解析器。
[^2]: 可以通过 config 中的 `markdown` 选项配置插件。

## 数学公式（需要插件）

$$
E = mc^2
$$

## Mermaid 图表（需要插件）

```
graph TD
    A[开始学习] --> B{选择方向}
    B -->|前端| C[HTML/CSS/JS]
    B -->|后端| D[Node.js/Python]
    C --> E[框架学习]
    D --> F[数据库]
    E --> G[项目实战]
    F --> G
```

## 总结

以上就是 VitePress 支持的常用 Markdown 语法。掌握这些，你就能写出漂亮的技术文档！
