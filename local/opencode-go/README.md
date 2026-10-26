# local/opencode-go —— 桌宠接入 opencode Go 的旁路工具包

这里放的是**不进入上游项目**的本地工具：一个把 `x-opencode-session` 请求头补上的本机中转代理，
以及配套的启动/自启/配置备份脚本和一份问题手册。

同一分支里还带了**上游补丁**（`pet/chat/providers.py` + `tests/test_opencode_go_headers.py`），
那是「彻底修法」，本工具包是「不改冻结版桌宠也能用」的旁路方案。

---

## 这个目录怎么用

整个目录**镜像**了本机的工作目录 `D:\aiwork\dsh-pet\`，所以：

```powershell
# 1) 把本目录内容拷到本机工作目录（或直接就地运行）
#    也可以整个仓库 clone 下来后，直接在这个目录里双击脚本

# 2) 启动代理（前台，有窗口能看日志）
启动代理.bat

# 3) 桌宠里填
#    API 地址 : http://127.0.0.1:8787/v1
#    模型     : deepseek-v4.1-flash
#    API Key  : opencode Go 的 Key
```

装开机自启：双击 `install_autostart.bat`（代理）、`开启配置自动备份.bat`（配置快照）。

---

## 目录结构

| 文件 | 说明 |
|---|---|
| `opencode_proxy.py` | 代理本体（纯标准库）：转发到 `https://opencode.ai/zen/go/v1`，补会话头、剥 model 前缀、SSE 流式透传 |
| `selftest_proxy.py` | 自检（9 项，不消耗 API 额度） |
| `启动代理.bat` / `proxy_silent.bat` / `proxy_silent.vbs` | 前台 / 静默 / 隐藏启动 |
| `install_autostart.bat` / `uninstall_autostart.bat` | 代理的开机自启装/卸 |
| `备份桌宠配置.bat` / `恢复桌宠配置.bat` / `开启配置自动备份.bat` | 桌宠配置快照与恢复 |
| `tools/pet_config_backup.py` | 快照/恢复实现（保留最近 20 份） |
| `tools/autostart.ps1`、`tools/autostart_backup.ps1` | 创建/删除启动文件夹快捷方式 |
| `dsh-pet接入opencode-go-问题手册.md` | **完整问题手册**：根因、方案、排障历程、检查清单 |
| `patches/providers.patch` | 上游补丁的 diff 副本（便于对照） |
| `patches/test_opencode_go_headers.py` | 上游单测副本 |

---

## 背景（一句话版）

opencode 的 **Go** 网关要求请求头带 `x-opencode-session`，缺失时**在鉴权之前**直接 400；
桌宠只发浏览器头 + Authorization，且没有自定义请求头入口 → 必然连不上。
本目录的代理在 `127.0.0.1:8787` 接住请求、补上头再转发，所以桌宠里把 API 地址指过来即可。

详细证据（Zen 不校验、Go 校验的实测对照）见 `dsh-pet接入opencode-go-问题手册.md` §1。

---

## 刻意不放进仓库的东西

- `gh` CLI 与 MinGit 等第三方二进制
- 代理日志 `opencode_proxy.log`、会话 ID `.opencode_session`
- 配置快照目录 `backups/`
- `__pycache__/`、补丁生成过程中的中间文件
- **任何 API Key**（桌宠的 Key 存在 Windows 凭据管理器，不在配置文件里，也不在本仓库里）
