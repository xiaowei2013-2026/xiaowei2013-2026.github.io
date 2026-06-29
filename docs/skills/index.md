# 🛠️ 技能工具箱

常用工具、命令和配置模板速查。

## 开发工具

| 工具 | 用途 | 官网 |
|------|------|------|
| VS Code | 代码编辑器 | [code.visualstudio.com](https://code.visualstudio.com) |
| Warp | 现代化终端 | [warp.dev](https://warp.dev) |
| DevToys | 开发者工具箱 | [devtoys.app](https://devtoys.app) |

## Git 常用命令

```bash
# 克隆仓库
git clone <url>

# 创建并切换到新分支
git checkout -b feature/xxx

# 暂存并提交
git add .
git commit -m "feat: 添加新功能"

# 推送到远程
git push origin main

# 查看提交历史
git log --oneline --graph
```

## Docker 速查

```bash
# 列出运行中的容器
docker ps

# 构建镜像
docker build -t my-app .

# 运行容器
docker run -d -p 3000:3000 my-app

# 查看日志
docker logs -f <container-id>

# 清理资源
docker system prune -a
```

## 常用 npm 命令

```bash
# 初始化项目
npm init -y

# 安装依赖
npm install <package>

# 安装开发依赖
npm install -D <package>

# 运行脚本
npm run <script-name>
```

## 快捷链接

- [GitHub](https://github.com)
- [npm](https://npmjs.com)
- [MDN Web Docs](https://developer.mozilla.org)
- [Stack Overflow](https://stackoverflow.com)
