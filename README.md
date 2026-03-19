# RUC 形势与政策讲座监控脚本

一个本地运行的 Python 脚本，用于监控中国人民大学学务中心活动页中的“形势与政策讲座”相关活动，支持登录态复用、活动去重、邮件提醒与定时循环检测。

## 功能概览

- Playwright 持久化浏览器上下文，复用登录状态
- 自动筛选：
  - 活动大类：素质拓展认证
  - 活动小类：形势与政策
  - 小类子类：形势与政策讲座
  - 活动状态：未开始
- 解析活动列表（标题 / 状态 / 时间）
- 本地 JSON 历史记录与新活动识别
- 仅对“新活动”发送 SMTP 邮件通知
- 邮件中包含活动直达链接（可直接打开活动详情页）
- 固定时间窗口内自动循环检测
- 循环时复用同一个浏览器实例，避免每轮弹出新窗口
- 登录失效检测与登录失效提醒邮件

## 目录结构

```text
LectureMonitor/
├─ main.py
├─ monitor.py
├─ notifier.py
├─ storage.py
├─ models.py
├─ page_selectors.py
├─ requirements.txt
├─ config.example.json
├─ README.md
├─ .gitignore
├─ data/
│  └─ .gitkeep
└─ logs/
   └─ .gitkeep
```

运行后会自动生成：
- `data/seen_activities.json`
- `data/browser_profile/`
- `logs/monitor.log`

## 环境要求

- Python 3.11+
- Chromium（由 Playwright 安装）

## 快速开始

1. 创建并激活虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate
```
或使用`conda`等创建虚拟环境。

2. 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

3. 准备配置

```bash
cp config.example.json config.json
```

4. 运行

```bash
python main.py --config config.json
```

## 配置说明（config.json）

```json
{
  "url": "https://v.ruc.edu.cn/campus#/search",
  "check_interval_minutes": 10,
  "monitor_start_hour": 8,
  "monitor_end_hour": 22,
  "browser": {
    "headless": false,
    "slow_mo_ms": 100,
    "profile_dir": "data/browser_profile"
  },
  "timeouts": {
    "page_load_ms": 30000,
    "ui_wait_ms": 8000,
    "login_check_delay_ms": 3500,
    "login_recover_retry_count": 4,
    "login_recover_retry_wait_ms": 2000
  },
  "email": {
    "smtp_host": "smtp.example.com",
    "smtp_port": 465,
    "sender": "your_email@example.com",
    "password": "your_app_password",
    "receiver": "your_email@example.com",
    "use_ssl": true
  }
}
```

关键字段：
- `check_interval_minutes`：轮询间隔（分钟）
- `monitor_start_hour` / `monitor_end_hour`：监控时段（按小时）
- `timeouts.login_check_delay_ms`：登录检测前额外等待，避免误判
- `timeouts.login_recover_retry_count`：登录后自动回跳目标页重试次数
- `timeouts.login_recover_retry_wait_ms`：重试间隔

关于smtp服务器配置，可自行google您邮箱对应的配置，一个qq邮箱的示例为：

```json
"email": {
  "smtp_host": "smtp.qq.com",
  "smtp_port": 465,
  "sender": "your_email@qq.com",
  "password": "your_app_password",
  "receiver": "your_email@qq.com",
  "use_ssl": true
}
```

## 运行参数

- 默认循环监控：

```bash
python main.py --config config.json
```

- 仅执行一轮（调试）：

```bash
python main.py --config config.json --once
```

- 登录失效时不等待手动恢复（默认会等待）：

```bash
python main.py --config config.json --no-manual-login
```

## 登录与重定向说明

- 默认情况下，检测到登录失效后脚本会等待你手动登录。
- 登录后如果页面被重定向到大厅首页，请直接根据终端提示在终端中按下回车，脚本会自动多次跳回目标检索页并重试检测。

## 邮件通知规则

- 仅在检测到“新活动”时发送邮件。
- 同一进程内，登录失效提醒会做去重，避免反复轰炸。

## 常见问题

1. 筛选失败
- 检查 `page_selectors.py` 中的筛选项文本与页面实际文本是否一致。
- 用 `playwright codegen https://v.ruc.edu.cn/campus#/search` 辅助定位。

2. 登录后仍提示失效
- 适当增大：
  - `timeouts.login_check_delay_ms`
  - `timeouts.login_recover_retry_count`
  - `timeouts.login_recover_retry_wait_ms`

## 安全提示（重要）

- `config.json` 含邮箱敏感信息，不应提交到 GitHub（已在 `.gitignore` 忽略）。
- 邮箱 `password` 应使用授权码，不要使用登录密码。
- 如果敏感信息曾泄露，建议立即更换授权码。

## 行为边界

- 不自动输入用户名、密码、验证码
- 不做验证码识别/绕过
- 不自动报名
