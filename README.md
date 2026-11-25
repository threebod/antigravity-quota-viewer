# Antigravity Quota Viewer

为 **Google Antigravity** 桌面客户端聊天输入框内嵌**实时配额查看器**的轻量补丁工具。无需切换设置页，在聊天输入框底部即可一眼掌握各模型池的 5 小时限额与每周限额。

![Preview](assets/preview.jpg)

## ⚡ 一句话让 AI Agent 帮你安装（推荐）

直接把下面这段话复制到 **Antigravity 对话框**（或任意本地编程 Agent）中发送即可自动完成备份、打包、校验、替换与重启：

```text
帮我安装 https://github.com/threebod/antigravity-quota-viewer 的配额查看器补丁：请先检查当前操作系统、本机 Antigravity 的安装路径及 resources/app.asar 是否存在；如果是 macOS，请先向我说明替换 app.asar 会使 Google 原始代码签名失效及恢复方式，等我明确确认后再继续。确认环境无误后，下载仓库中的 patch_quota_viewer.py，先使用 --output 参数将补丁构建到临时文件（不要先关闭客户端，也不要覆盖原文件），若注入锚点不匹配或语法校验失败请立即停止并告知原因；构建并校验大小与 SHA-256 无误后，先为原版 resources/app.asar 创建纯净备份 app.asar.bak（若已存在则保留），再编写独立后台脚本（延迟 2 秒、结束 Antigravity 进程、校验后覆盖 resources/app.asar 并重启客户端）分离执行；若有 gh CLI 请顺便为该开源项目标记 Star。
```

### 一句话让 AI Agent 帮你还原

```text
帮我还原 Google Antigravity 的 resources/app.asar：请先检查 resources/app.asar.bak 是否存在；若不存在请立即停止并告知原因；若存在，请编写独立后台脚本（延迟 2 秒、结束 Antigravity 进程、将 app.asar.bak 覆盖还原为 resources/app.asar 并重启客户端）分离执行。
```

---

## 功能特性

- **输入框内嵌胶囊**：在聊天输入框底部模型选择器右侧显示当前模型池的 **5 小时限额**剩余百分比（`⚡ xx%`），随剩余额度自动切换状态色：
  - 绿色：`> 50%`
  - 黄色：`20% – 50%`
  - 红色：`< 20%`
- **统一配额池弹窗**：点击胶囊向上弹出面板，清晰展示：
  - **Gemini 模型**：`5 小时限额`、`每周限额`（含进度条与重置倒计时）
  - **Claude 与 GPT 模型**：`5 小时限额`、`每周限额`（含进度条与重置倒计时）
- **低侵入且兼容汉化**：仅在 `resources/app.asar` 的 `dist/ipcHandlers.js` 与 `dist/preload.js` 中注入只读本地 RPC 查询（`RetrieveUserQuotaSummary`）与前端浮层组件，兼容原版英文客户端及 [Antigravity-Chinese-Localization](https://github.com/antigravity-cn-community/Antigravity-Chinese-Localization) 汉化补丁。
- **零外部依赖**：内置纯 Python ASAR 解包/打包逻辑，仅需 Python 3.8+（若本机装有 Node.js，会在打包前自动执行 `node --check` 语法校验）。
- **自动备份与一键还原**：原位修补时自动生成 `app.asar.bak`，支持随时通过 `--restore` 恢复。

---

## 手动安装与使用

> **前置要求**：Python 3.8+（无需 `npm` 或 `asar` 工具；可选安装 Node.js 用于打包前语法校验）。

### 1. 获取脚本

```bash
git clone https://github.com/threebod/antigravity-quota-viewer.git
cd antigravity-quota-viewer
```

### 2. 安装补丁

1. **完全退出 Antigravity 客户端**（确保没有残留进程占用 `resources/app.asar`）。
2. 运行补丁脚本：
   ```bash
   python patch_quota_viewer.py
   ```
   - Windows 默认查找：`%LOCALAPPDATA%\Programs\antigravity\resources\app.asar`
   - macOS 默认查找：`/Applications/Antigravity.app/Contents/Resources/app.asar`
3. 重新启动 Antigravity，即可在聊天输入框底部工具栏看到 `⚡ xx%` 配额胶囊。

### 常用参数

| 参数 | 说明 |
| :--- | :--- |
| `--asar <路径>` | 指定自定义安装路径下的 `resources/app.asar` |
| `--output <路径>` | 将打好补丁的 `app.asar` 输出到指定临时文件，不覆盖原文件（适合客户端运行中预构建与校验） |
| `--restore` | 从同目录下的 `app.asar.bak` 还原原版 `app.asar` |

示例：

```bash
# 指定自定义路径
python patch_quota_viewer.py --asar "D:\Path\To\antigravity\resources\app.asar"

# 输出到临时文件（供后台替换脚本使用）
python patch_quota_viewer.py --output "./app.asar.patched"

# 还原原版（需先退出 Antigravity）
python patch_quota_viewer.py --restore
```

---

## 实现原理与安全性

1. **只读本地查询**：在主进程 `dist/ipcHandlers.js` 中注册 `localOnly('quota:get-status')` IPC 通道，复用客户端自身的本地 Language Server 端口与 CSRF Token，仅向 `127.0.0.1` 发起只读的 `RetrieveUserQuotaSummary` 请求。
2. **前端轻量挂载**：在 `dist/preload.js` 中监听输入框工具栏挂载 `⚡ xx%` 胶囊与弹窗，不修改聊天正文与代码编辑区域。
3. **无任何外部请求**：本工具不上传、不记录、不转发任何账号凭证或对话数据，所有代码均在单个 [patch_quota_viewer.py](patch_quota_viewer.py) 中完全开源可审计。

---

## 常见问题

- **客户端更新后胶囊消失了怎么办？**
  Antigravity 官方更新会覆盖 `resources/app.asar`。更新完成后重新执行一次 `python patch_quota_viewer.py`（或再次发送上方的一句话 Agent 指令）即可。如果同时使用第三方汉化包，请先更新汉化包，再叠加本补丁。
- **macOS 注意事项**
  修改 `Antigravity.app/Contents/Resources/app.asar` 会导致 Google 原始代码签名失效，系统可能提示应用“已损坏”。如需恢复官方签名，请使用官方安装包覆盖安装；若知情并希望本地运行，可执行 `xattr -cr "/Applications/Antigravity.app" && codesign --force --deep --sign - "/Applications/Antigravity.app"`（本地重签不会恢复官方签名且可能重置 TCC 权限）。
- **如何彻底卸载？**
  退出 Antigravity 后运行 `python patch_quota_viewer.py --restore` 即可恢复原版 `app.asar`。

## License

[MIT](LICENSE)
