# GrokRegister

[中文](#中文说明) | [English](#english)

---

## 中文说明

### 项目简介

GrokRegister 是一个基于 Python 的自动化项目，用于组织 x.ai 注册流程中的多个环节。仓库当前包含临时邮箱创建、邮箱验证码处理、Cloudflare Turnstile 求解、本地结果保存，以及本地启动脚本等模块。

整个项目主要由两条运行链路组成：

- `grok.py`：主注册流程入口
- `api_solver.py`：本地 Turnstile 求解服务

### 功能特性

- 多线程主流程执行
- TempMail.lol 临时邮箱创建与轮询
- 邮箱验证码请求与校验
- 两种 Turnstile 处理模式
  - YesCaptcha API
  - 本地浏览器求解服务
- 自动读取环境变量或 Windows 系统代理
- 提供 PowerShell / Batch 启动脚本
- 带有基础测试用例

### 仓库结构

```text
.
|-- grok.py                     # 主注册流程
|-- api_solver.py               # 本地 Turnstile 求解服务
|-- browser_configs.py          # 浏览器配置与 UA 辅助
|-- db_results.py               # 本地内存结果存储
|-- g/
|   |-- __init__.py
|   |-- email_service.py        # TempMail.lol 封装
|   `-- turnstile_service.py    # YesCaptcha / 本地 solver 封装
|-- tests/
|   |-- test_email_service.py
|   |-- test_grok_setup.py
|   `-- test_start_script.py
|-- start_project.ps1           # PowerShell 启动脚本
|-- start_project.bat           # Batch 启动脚本
|-- requirements.txt
`-- .env.example
```

### 环境要求

- Python 3.10 及以上
- Windows PowerShell，用于仓库自带启动脚本
- 可选：Playwright Chromium，本地 solver 模式需要
- 可选：YesCaptcha API Key

### 安装步骤

#### 1. 创建虚拟环境

```bash
python -m venv .venv
```

#### 2. 激活虚拟环境

PowerShell：

```powershell
.venv\Scripts\Activate.ps1
```

CMD：

```cmd
.venv\Scripts\activate.bat
```

#### 3. 安装依赖

```bash
pip install -r requirements.txt
```

#### 4. 安装 Chromium

如果你计划使用本地浏览器 solver，需要先安装：

```bash
python -m playwright install chromium
```

### 配置说明

从 `.env.example` 复制一份到 `.env`：

```bash
copy .env.example .env
```

示例配置：

```env
# YesCaptcha API key
YESCAPTCHA_KEY="your_key_here"

# TempMail.lol API key
TEMPMAIL_LOL_API_KEY="your_key_here"

# Optional proxy examples
# HTTP_PROXY="http://127.0.0.1:7892"
# HTTPS_PROXY="http://127.0.0.1:7892"
```

配置规则：

- 如果设置了 `YESCAPTCHA_KEY`，项目会优先使用 YesCaptcha。
- 如果没有设置 `YESCAPTCHA_KEY`，则默认走本地 `http://127.0.0.1:5072` solver。
- `HTTP_PROXY` / `HTTPS_PROXY` 优先级高于 Windows 系统代理。
- 如果环境变量和系统代理都没有，才会回退到 `grok.py` 里的默认代理配置。

### 使用方式

#### 模式 1：只运行主流程

```bash
python grok.py
```

主流程会：

1. 初始化运行目录
2. 解析代理配置
3. 拉取注册页面
4. 提取动态参数，例如 Action ID
5. 读取线程数
6. 启动工作线程

#### 模式 2：本地 solver + 主流程

先启动本地 solver：

```bash
python api_solver.py --browser_type chromium --thread 2 --debug
```

再在另一个终端运行主流程：

```bash
python grok.py
```

#### 模式 3：使用启动脚本

PowerShell：

```powershell
.\start_project.ps1
```

常用参数：

```powershell
.\start_project.ps1 -Thread 2
.\start_project.ps1 -NoSolverDebug
.\start_project.ps1 -OnlySolver
.\start_project.ps1 -OnlyMain
```

Batch：

```cmd
start_project.bat
```

### 运行流程

项目整体流程大致如下：

1. 请求 x.ai 注册页面
2. 提取动态参数
   - Turnstile site key
   - next-router-state-tree
   - Next.js 静态资源中的 action ID
3. 创建临时邮箱
4. 请求邮箱验证码
5. 轮询邮箱直到收到验证码
6. 校验邮箱验证码
7. 获取 Turnstile token
8. 提交最终注册请求
9. 从 cookie 中提取 `sso` 并写入本地结果文件

### 输出文件

成功结果会写入 `keys/` 目录：

- `keys/grok.txt`：每行一个 `sso`
- `keys/accounts.txt`：格式为 `email:password:sso`

如果目录不存在，程序会自动创建。

### 测试

运行测试：

```bash
pytest tests
```

当前测试覆盖：

- 运行目录创建
- 线程数解析
- 代理解析
- 预检请求参数
- TempMail 服务封装
- 启动脚本结构

### 常见问题

#### 1. Action ID 找不到

如果程序提示找不到 Action ID，通常表示目标站点前端资源结构发生了变化。

#### 2. 邮箱验证码一直收不到

常见原因：

- TempMail 服务不稳定
- API Key 配置错误
- 上游请求限流
- 代理不稳定

#### 3. Turnstile 一直失败

建议检查：

- `YESCAPTCHA_KEY` 是否有效
- 本地 solver 是否已启动
- Chromium 是否已安装
- 浏览器是否能正常访问目标站点

#### 4. 网络或 GitHub 环境问题

如果当前机器处于受限网络环境，代理、HTTPS 传输和外部服务连通性都可能影响项目行为。

### 开发说明

- `db_results.py` 当前只做内存存储，不带持久化。
- 重启 `api_solver.py` 会清空未完成任务结果。
- 当前仓库没有打包、数据库或部署配置。
- 测试以基础配置校验为主，不是完整端到端测试。

### 安全提示

- 不要把 `.env` 提交到版本库。
- `keys/` 下的结果文件应视为敏感信息。
- 不要在日志、截图或公开 issue 中暴露 token、密钥或结果文件内容。

### 许可证

当前仓库还没有附带 License 文件。如果你计划公开分发或允许他人复用，建议补充许可证。

---

## English

### Overview

GrokRegister is a Python-based automation project that organizes multiple parts of the x.ai sign-up flow. The repository currently includes temporary inbox creation, email verification handling, Cloudflare Turnstile solving, local result persistence, and convenience launch scripts.

The project is centered around two runtime paths:

- `grok.py`: main registration workflow
- `api_solver.py`: local Turnstile-solving service

### Features

- Multi-threaded main runner
- TempMail.lol inbox creation and polling
- Email verification request and validation flow
- Two Turnstile solving modes
  - YesCaptcha API
  - Local browser-based solver
- Automatic proxy detection from environment variables or Windows settings
- PowerShell and Batch launch scripts
- Basic test coverage

### Repository Structure

```text
.
|-- grok.py                     # Main registration runner
|-- api_solver.py               # Local Turnstile solver API service
|-- browser_configs.py          # Browser configuration helpers
|-- db_results.py               # In-memory result store
|-- g/
|   |-- __init__.py
|   |-- email_service.py        # TempMail.lol wrapper
|   `-- turnstile_service.py    # YesCaptcha / local solver wrapper
|-- tests/
|   |-- test_email_service.py
|   |-- test_grok_setup.py
|   `-- test_start_script.py
|-- start_project.ps1           # PowerShell launcher
|-- start_project.bat           # Batch launcher
|-- requirements.txt
`-- .env.example
```

### Requirements

- Python 3.10+
- Windows PowerShell for the included launch scripts
- Optional: Playwright Chromium for local solver mode
- Optional: YesCaptcha API key

### Installation

#### 1. Create a virtual environment

```bash
python -m venv .venv
```

#### 2. Activate it

PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Command Prompt:

```cmd
.venv\Scripts\activate.bat
```

#### 3. Install dependencies

```bash
pip install -r requirements.txt
```

#### 4. Install Chromium

Required only if you want to run the local browser solver:

```bash
python -m playwright install chromium
```

### Configuration

Create `.env` from `.env.example`:

```bash
copy .env.example .env
```

Example:

```env
# YesCaptcha API key
YESCAPTCHA_KEY="your_key_here"

# TempMail.lol API key
TEMPMAIL_LOL_API_KEY="your_key_here"

# Optional proxy examples
# HTTP_PROXY="http://127.0.0.1:7892"
# HTTPS_PROXY="http://127.0.0.1:7892"
```

Configuration rules:

- If `YESCAPTCHA_KEY` is set, the project uses YesCaptcha first.
- If `YESCAPTCHA_KEY` is not set, the project expects a local solver at `http://127.0.0.1:5072`.
- `HTTP_PROXY` and `HTTPS_PROXY` take priority over Windows proxy settings.
- If neither environment variables nor Windows proxy settings are available, the default proxy configuration inside `grok.py` is used.

### Usage

#### Mode 1: Main Runner Only

```bash
python grok.py
```

The main workflow will:

1. initialize runtime directories
2. resolve proxy settings
3. fetch the sign-up page
4. extract dynamic values such as the action ID
5. ask for thread count
6. start worker threads

#### Mode 2: Local Solver + Main Runner

Start the local solver first:

```bash
python api_solver.py --browser_type chromium --thread 2 --debug
```

Then run the main workflow in another terminal:

```bash
python grok.py
```

#### Mode 3: Launch Script

PowerShell:

```powershell
.\start_project.ps1
```

Common options:

```powershell
.\start_project.ps1 -Thread 2
.\start_project.ps1 -NoSolverDebug
.\start_project.ps1 -OnlySolver
.\start_project.ps1 -OnlyMain
```

Batch:

```cmd
start_project.bat
```

### Runtime Flow

The high-level workflow is:

1. request the x.ai sign-up page
2. extract dynamic values
   - Turnstile site key
   - next-router-state-tree
   - action ID from Next.js static assets
3. create a temporary inbox
4. request an email verification code
5. poll the inbox until the code arrives
6. verify the email code
7. obtain a Turnstile token
8. submit the final sign-up request
9. extract the `sso` cookie and write local output

### Output Files

Successful results are written into `keys/`:

- `keys/grok.txt`: one `sso` per line
- `keys/accounts.txt`: `email:password:sso`

The directory is created automatically if it does not exist.

### Testing

Run tests with:

```bash
pytest tests
```

Current tests cover:

- runtime directory creation
- thread parsing
- proxy parsing
- preflight request setup
- TempMail service wrappers
- launch script structure

### Troubleshooting

#### 1. Action ID cannot be found

If the script cannot find the action ID, the target site's frontend assets or structure likely changed.

#### 2. Verification email never arrives

Common causes:

- TempMail instability
- invalid API key
- upstream throttling
- unstable proxy

#### 3. Turnstile solving keeps failing

Check whether:

- `YESCAPTCHA_KEY` is valid
- the local solver is running
- Chromium is installed
- the browser can access the target site

#### 4. Network or GitHub environment issues

If the machine runs under restricted networking conditions, proxy settings, HTTPS transport, and external service connectivity can all affect behavior.

### Development Notes

- `db_results.py` currently stores results in memory only.
- Restarting `api_solver.py` clears pending task results.
- The repository does not currently include packaging, a database backend, or deployment configuration.
- The current tests focus on setup-level validation rather than full end-to-end execution.

### Security Notes

- Keep `.env` out of version control.
- Treat files under `keys/` as sensitive local output.
- Do not expose API keys, tokens, or saved outputs in logs, screenshots, or public issues.

### License

No license file is currently included. Add one if you plan to distribute or reuse the repository publicly.
