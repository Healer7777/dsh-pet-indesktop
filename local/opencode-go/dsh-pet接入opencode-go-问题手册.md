# dsh-pet 接入 opencode Go —— 问题手册

> 最后更新：2026-10-25　｜　适用：桌面版 dsh-pet-standalone (WebM Chat) 4.4.0 / Windows 10
> 所有脚本都在 `D:\aiwork\dsh-pet\`，桌宠配置在 `%APPDATA%\dsh-pet-standalone-webm-chat\`

---

## 0. 30 秒速查

| 症状 | 先看这里 |
|---|---|
| 桌宠对话报 **400 MissingSessionID** | API 地址填错（不是 `http://127.0.0.1:8787/v1`），见 §2 |
| 桌宠报 **10061 目标计算机积极拒绝** | 代理没启动，双击 `启动代理.bat`，见 §4 |
| 报 **401 Invalid credential** | 代理正常，是 Key 的问题，见 §3.4 |
| 想确认代理活着 | 浏览器打开 <http://127.0.0.1:8787/healthz>，返回 `{"ok": true...}` |
| 误点了「重置配置」 | 关掉桌宠 → 双击 `恢复桌宠配置.bat`，见 §5 |
| 想知道"回收内存"会不会杀进程 | 不会，见 §6 |

---

## 1. 背景与结论

**问题**：桌宠的 AI 设置里接 opencode Go（`https://opencode.ai/zen/go/v1` + Go 订阅 Key），
「测试连接」固定失败：

```
请求失败（HTTP 400）：Request is missing x-opencode-session and cannot be routed efficiently.
```

**根因**（实测，不是猜的）：

| 端点 | 不带 `x-opencode-session` | 带着它 |
|---|---|---|
| `/zen/v1/chat/completions`（Zen） | 401 Invalid credential | 401 Invalid credential |
| `/zen/go/v1/chat/completions`（Go） | **400 MissingSessionID** | 401 Invalid credential |

- Go 网关要求客户端自报**会话级稳定 ID**，缺失时**在鉴权之前**就 400；
- 桌宠的 `pet/chat/providers.py` 只发浏览器头（UA / Accept / Language / Cache-Control / Pragma）
  + `Authorization`，`ProviderConfig` 也没有"自定义请求头"字段 → 无论怎么填都过不去；
- 这也解释了上游 issue #122 为什么被以"browser headers 已覆盖"关闭：**Zen 不校验这个头，Go 才校验**，
  两者不是一回事。

**最终方案**：本机中转代理（不动桌宠、不重打包），详见 §2；彻底修法（改源码 / 上游 PR）见 §7。

---

## 2. 方案 A：本地中转代理（当前正在用）

### 2.1 工作原理

```
桌宠 ──HTTP──> 127.0.0.1:8787/v1 ──HTTPS──> https://opencode.ai/zen/go/v1
                     │
                     ├─ 注入 x-opencode-session（进程级稳定 UUID，存 .opencode_session）
                     ├─ 用自有 UA 覆盖浏览器 UA
                     ├─ 剥掉 model 的 "opencode-go/" 前缀
                     └─ SSE 流式逐块透传（不缓冲，逐字输出不受影响）
```

### 2.2 桌宠里必须这样填

| 字段 | 值 |
|---|---|
| API 地址 | `http://127.0.0.1:8787/v1` ← **关键，不能填 opencode.ai** |
| 模型 | `deepseek-v4.1-flash`（填 `opencode-go/deepseek-v4.1-flash` 也行，代理会剥前缀） |
| API Key | opencode Go 的 Key（原样转发，代理不落盘） |

### 2.3 文件与参数

| 项 | 值 |
|---|---|
| 代理本体 | `D:\aiwork\dsh-pet\opencode_proxy.py`（纯标准库，无需装包） |
| 端口 | 8787（只绑 127.0.0.1，局域网访问不到） |
| 健康检查 | `GET /healthz` |
| 日志 | `D:\aiwork\dsh-pet\opencode_proxy.log`（每次请求一行） |
| 会话 ID | `D:\aiwork\dsh-pet\.opencode_session`（首启生成，跨重启不变，利于服务端缓存） |
| 自检 | `python selftest_proxy.py`（9 项，不消耗额度） |

### 2.4 启动方式

| 场景 | 做法 |
|---|---|
| 开机自动（已装） | 启动文件夹里的 `opencode-proxy.lnk` → `pythonw.exe opencode_proxy.py`，无窗口 |
| 手动（有黑窗，看日志） | 双击 `启动代理.bat` |
| 手动（无窗口） | 双击 `proxy_silent.vbs` |
| 停止 | 任务管理器结束 `python.exe` / `pythonw.exe`；或关掉那个黑窗口 |

**单实例保护**：重复启动会探测 `/healthz`，发现是自己就打印"已在 8787 端口运行"后退出；
端口被别的程序占用时会明确报错退出（不会偷偷换端口，免得桌宠地址失效）。

### 2.5 故障对照

| 现象 | 原因 | 处理 |
|---|---|---|
| 400 MissingSessionID | 请求没走代理（地址还是 opencode.ai） | 改成 `http://127.0.0.1:8787/v1` |
| 10061 连接被拒 | 代理没跑 | 双击 `启动代理.bat` |
| 401 Invalid credential | 代理正常，Key 无效/过期/不是 Go 订阅 | 换 Key |
| 502 本地代理连不上 opencode | 本机网络或梯子挡了 opencode.ai | 检查代理软件 |
| 提示端口被占用 | 8787 被别的程序占了 | 释放端口，或 `--port` 换端口并同步改桌宠地址 |

---

## 3. 排障历程（按时间顺序，都是真实踩过的坑）

### 3.1 一次"没送到"的授权

用 GitHub 设备码给 gh CLI 授权，拿到的是 `ghu_` 前缀令牌（GitHub App 用户令牌），
只有只读权限：`POST /repos/.../issues` → **403 Resource not accessible by integration**。
→ 建 issue / 开 PR 需要 PAT（`public_repo` 或细粒度 Issues: Read and write），设备流给不了。

### 3.2 代理进程"自己消失"

现象：昨天能用，今天报 10061，日志里没有任何崩溃记录。
原因：我用 `Start-Process` 拉起的进程挂在 DSH 的受限沙箱下，**shell/会话回收时子进程被一起收走**。
→ 稳定做法只有两个：① 开机自启（Windows 拉起，不受影响）；② 用户自己双击启动。
不要指望"我在会话里帮你起的进程"能长期活着。

### 3.3 重启后好了，重置配置后又 400

现象：重启 → 正常；点了「重置配置」→ 又 400。
原因：重置把 provider 配置清空，API 地址回到 `https://opencode.ai/zen/go/v1`（绕过代理），
**API Key 输入框也变空**（重置生成了新的 provider id，钥匙串里旧条目对不上）。
→ 重新填三样：地址 `http://127.0.0.1:8787/v1`、模型 `deepseek-v4.1-flash`、Key。

### 3.4 关于 Key 的存放

- API Key **不在** `config.json` 里，存在 Windows 凭据管理器（条目名 `provider/api-2`）；
- 配置文件里只有 `api_key_ref`（指向哪条凭据）；
- 所以换 provider id / 重置配置后必须重填；备份配置也**不包含** Key 本身。

---

## 4. 开机自启是怎么装的

| 启动项 | 目标 | 作用 |
|---|---|---|
| `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\opencode-proxy.lnk` | `pythonw.exe opencode_proxy.py --port 8787` | 登录即起代理，无窗口 |
| `…\Startup\pet-config-backup.lnk` | `pythonw.exe tools\pet_config_backup.py --quiet` | 登录即给桌宠配置拍快照 |

安装脚本：`install_autostart.bat`（代理）、`开启配置自动备份.bat`（配置快照）。
卸载：`uninstall_autostart.bat` / 直接删对应 `.lnk`。

> 注意：这两条快捷方式指向 `D:\aiwork\dsh-pet\` 里的脚本。**别移动/删除这个目录**；
> 挪了位置就重跑一次安装脚本。快捷方式里的 Python 是 DSH 自带的
> `%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\pythonw.exe`，
> 如果哪天 DSH 被卸载，重跑安装脚本（会找系统 pythonw 或退回 wscript 方式）。

---

## 5. 配置备份 / 恢复（防「重置配置」）

### 5.1 备份了什么

`%APPDATA%\dsh-pet-standalone-webm-chat\` 下的 4 个文件：

```
config.json                      ← 全部设置（含 AI provider 配置）
config-slot-0.json / -1.json     ← 多开实例的槽位配置
.config-reset-generations.json   ← 重置代次
```

**不含**：`sessions/`（聊天记录）、`characters/`（角色包）、API Key。

每份快照目录里附 `说明.txt`，记录当时的 provider / 地址 / 模型，方便辨认。

### 5.2 怎么用

| 动作 | 操作 |
|---|---|
| 手动备份 | 双击 `备份桌宠配置.bat` |
| 自动备份 | 已装：每次登录自动一份，保留最近 20 份 |
| 查看快照 | `python tools\pet_config_backup.py --list` |
| 恢复 | **先托盘退出桌宠** → 双击 `恢复桌宠配置.bat` → 选序号 → 输 `yes` |

存放位置：`D:\aiwork\dsh-pet\backups\backup-YYYYmmdd-HHMMSS\`

**恢复前必须先关桌宠**，否则运行中的进程会把旧配置再写回去，覆盖你的恢复。
恢复后若提示认证失败，把 API Key 重新粘一次即可。

---

## 6. 桌宠的「回收内存」是干什么的（已核源码）

源码：`pet/memory_trim.py`（572 行，Windows 专用）。

- **不杀进程**：整个文件没有 `TerminateProcess`，只调用 `EmptyWorkingSet()`，
  把各进程"暂时没用的物理页"交还系统；进程照常运行，下次访问那些页时付一次缺页。
- **六条保护**（优先级从高到低）：自己 → 前台窗口 → 自己的子进程（ffmpeg 解码）→
  系统关键进程（smss/csrss/wininit/services/lsass/winlogon/dwm/fontdrvhost/MsMpEng/NisSrv 等，
  外加 pid≤4）→ 读不出名字的（按关键处理）→ 工作集 < 阈值（默认 50 MB）。
- 权限不足的进程静默跳过并计数；句柄在 `finally` 里关闭；整轮跑在后台 daemon 线程，
  菜单点完立刻返回，不会冻结界面。
- 配置项：`mem_min_size_mb`（默认 50）、`mem_skip_foreground`（默认开）。
- 建议：别当日常习惯用，玩大型游戏前点一下即可；阈值调大（如 200 MB）更保守。

---

## 7. 彻底修法：给上游提修复

### 7.1 补丁本身

只改 `pet/chat/providers.py`，**+23 行**：

```python
_OPENCODE_SESSION_ID = uuid.uuid4().hex

def _opencode_headers(base_url):          # 只对 opencode.ai 生效
    return {'x-opencode-session': _OPENCODE_SESSION_ID} if 'opencode.ai' in str(base_url or '').lower() else {}

def _normalize_model_id(base_url, model):  # opencode-go/x -> x
    ...
```

接入点三处：`test_connection()`、`OpenAICompatibleProvider._open()`、请求体 model。

产物：

| 文件 | 说明 |
|---|---|
| `b-patch/providers.patch` | 统一 diff（`git apply`） |
| `b-patch/providers_patched.py` | 打完补丁的完整文件（网页版替换用） |
| `b-patch/tests/test_opencode_go_headers.py` | 新增 7 条单测 |
| `b-patch/PR.md` / `PR-body.md` / `commit.txt` | PR 标题、正文、提交信息 |
| `b-patch/ISSUE.md` / `ISSUE-body.md` | issue 标题、正文（含 #122 差异说明） |

验证：对着 `main @ 34d810b1` 跑通 7/7（本机用等价断言执行器 `b-patch/run_tests.py`，
因为沙箱装不了 pytest）；实机补头后连续 4 次请求 200、流式正常。

### 7.2 提 PR / issue 的现状

- 上游 **#122** 是 Zen 免费模型的旧需求，已关闭；我们的 issue 正文里用 zen/go 对照表说明
  "这不是重复提需求"，并建议在其下留一条交叉引用评论；
- issue 已由用户提交（编号待补）；
- 提交需要**写权限**：gh 设备码令牌不够（见 §3.1），得用 PAT。

### 7.3 如果要重打包安装版（不推荐）

装的是 Inno onedir 冻结版，业务代码在 exe 内嵌的 PYZ 里（`_internal\pet\chat` 只有 qss），
改 `.py` 不生效。完整路径：clone → `pip install -r requirements.txt` → `build_onedir.ps1` →
`ISCC.exe packaging\dsh-pet.iss` → 覆盖安装（约半天）。而且桌宠会在线更新，改了也会被覆盖。

---

## 8. 文件清单

```
D:\aiwork\dsh-pet\
├── opencode_proxy.py            代理本体
├── 启动代理.bat                  前台启动（看日志）
├── proxy_silent.bat / .vbs       静默启动（自启兜底）
├── install_autostart.bat         装开机自启
├── uninstall_autostart.bat       卸载开机自启
├── selftest_proxy.py             代理自检（9 项）
├── 备份桌宠配置.bat              手动备份
├── 恢复桌宠配置.bat              交互式恢复
├── 开启配置自动备份.bat          装"登录自动备份"
├── opencode_proxy.log            代理日志
├── .opencode_session             稳定会话 ID
├── backups\                      配置快照（保留 20 份）
├── tools\
│   ├── autostart.ps1             代理自启快捷方式
│   ├── autostart_backup.ps1      配置备份自启快捷方式
│   ├── pet_config_backup.py      快照/恢复实现
│   ├── gh_device_login.py        设备码授权（只读令牌，仅供参考）
│   ├── submit_issue.py           用 PAT 提交 issue 的工具
│   └── bin\gh.exe                GitHub CLI 2.103.2（免安装版）
└── b-patch\                      上游 issue/PR 材料（见 §7.1）
```

---

## 9. 下次开工的检查清单

1. 浏览器开 <http://127.0.0.1:8787/healthz> → 有 `{"ok": true}` 就跳过第 2 步；
2. 没有就双击 `启动代理.bat`（或 `proxy_silent.vbs`）；
3. 桌宠 AI 设置确认：地址 `http://127.0.0.1:8787/v1`、模型 `deepseek-v4.1-flash`、Key 非空；
4. 点「测试连接」→ 应显示 `连接成功（HTTP 200）`；
5. 改动过配置且验证可用后，双击 `备份桌宠配置.bat` 存一份。

---

## 10. 未完成 / 可选事项

- [ ] 上游 issue 跟进：等作者回复（A 自动补头 / B 通用 `extra_headers` / C 不做），收到回复后按方向出 PR；
- [ ] 可选：代理 watchdog（每 60 秒探活，挂了自动拉起）——目前没装，靠开机自启 + 手动双击；
- [ ] 可选：把 API Key 记到密码管理器（唯一无法自动备份的东西）。
