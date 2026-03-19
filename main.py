import argparse
import json
import logging
import time
from datetime import datetime
from pathlib import Path

from models import Activity
from monitor import LectureMonitor, LoginRequiredError
from notifier import EmailNotifier
from storage import ActivityStorage


def setup_logging() -> None:
    """初始化日志：同时输出到终端和文件。"""
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "monitor.log", encoding="utf-8"),
        ],
    )


def load_config(config_path: Path) -> dict:
    """读取 JSON 配置文件。"""
    if not config_path.exists():
        raise FileNotFoundError(
            f"未找到配置文件: {config_path}。请先基于 config.example.json 创建 config.json"
        )

    with config_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RUC 讲座监控（第四阶段：循环调度与健壮性）")
    parser.add_argument(
        "--config",
        default="config.json",
        help="配置文件路径，默认: config.json",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="仅执行一轮（调试用）",
    )
    parser.add_argument(
        "--no-manual-login",
        action="store_true",
        help="登录失效时不等待手动登录恢复，直接进入下一轮（默认会等待）",
    )
    return parser.parse_args()


def print_activity_group(group_name: str, activities: list[Activity]) -> None:
    """按分组打印活动信息。"""
    print(f"\n--- {group_name}（{len(activities)}）---")
    if not activities:
        print("无")
        return

    for index, activity in enumerate(activities, start=1):
        print(f"{index}. 标题: {activity.title}")
        print(f"   状态: {activity.status}")
        print(f"   时间: {activity.time_text}")
        if activity.detail_url:
            print(f"   链接: {activity.detail_url}")


def get_runtime_config(config: dict) -> tuple[int, int, int]:
    """读取第四阶段运行配置。"""
    check_interval_minutes = int(config.get("check_interval_minutes", 10))
    monitor_start_hour = int(config.get("monitor_start_hour", 8))
    monitor_end_hour = int(config.get("monitor_end_hour", 22))

    if check_interval_minutes <= 0:
        raise ValueError("check_interval_minutes 必须大于 0")
    if not (0 <= monitor_start_hour <= 23 and 0 <= monitor_end_hour <= 23):
        raise ValueError("monitor_start_hour 和 monitor_end_hour 必须在 0~23 之间")

    return check_interval_minutes, monitor_start_hour, monitor_end_hour


def is_within_monitor_window(now: datetime, start_hour: int, end_hour: int) -> bool:
    """判断当前时间是否在监控时间窗口内。"""
    current_hour = now.hour

    if start_hour == end_hour:
        return True

    if start_hour < end_hour:
        return start_hour <= current_hour < end_hour

    # 允许跨天窗口，例如 22:00 到次日 08:00
    return current_hour >= start_hour or current_hour < end_hour


def run_single_cycle(
    monitor: LectureMonitor,
    storage: ActivityStorage,
    notifier: EmailNotifier,
    allow_manual_login: bool,
    login_alert_sent: bool,
) -> bool:
    """执行一轮检测，返回更新后的登录失效提醒状态。"""
    logging.info("开始新一轮检查。")

    try:
        activities = monitor.run_once(allow_manual_login=allow_manual_login)

    except LoginRequiredError as exc:
        logging.warning("检测到登录失效: %s", exc)
        if not login_alert_sent:
            notifier.notify_login_invalid(str(exc))
            return True

        logging.info("登录失效提醒邮件已发送过，本轮不重复发送。")
        return True

    except Exception as exc:
        logging.exception("本轮检查发生异常: %s", exc)
        return login_alert_sent

    ordinary_activities, new_activities = storage.classify_and_update(activities)

    print("\n===== 本次活动检测结果 =====")
    if not activities:
        print("未解析到活动（可能是筛选结果为空，或选择器需要调试）。")
    else:
        print_activity_group("新活动", new_activities)
        print_activity_group("普通活动", ordinary_activities)

    if new_activities:
        notifier.notify_new_activities(new_activities)
    else:
        logging.info("本次没有新活动，不触发邮件通知。")

    return False


def main() -> None:
    args = parse_args()
    setup_logging()
    monitor: LectureMonitor | None = None

    try:
        config = load_config(Path(args.config))
        check_interval_minutes, monitor_start_hour, monitor_end_hour = get_runtime_config(config)

        monitor = LectureMonitor(config)
        storage = ActivityStorage()
        notifier = EmailNotifier(config.get("email"))

        logging.info("脚本启动。")
        logging.info(
            "监控配置：间隔=%d 分钟，时间窗口=%02d:00-%02d:00",
            check_interval_minutes,
            monitor_start_hour,
            monitor_end_hour,
        )

        login_alert_sent = False
        while True:
            now = datetime.now()
            in_window = is_within_monitor_window(now, monitor_start_hour, monitor_end_hour)
            logging.info("当前时间：%s，是否处于监控时段：%s", now.strftime("%Y-%m-%d %H:%M:%S"), in_window)

            if in_window:
                login_alert_sent = run_single_cycle(
                    monitor=monitor,
                    storage=storage,
                    notifier=notifier,
                    allow_manual_login=not args.no_manual_login,
                    login_alert_sent=login_alert_sent,
                )
            else:
                logging.info("当前不在监控时段，跳过本轮查询。")

            if args.once:
                logging.info("--once 模式已完成，脚本结束。")
                break

            logging.info("休眠 %d 分钟后进行下一轮。", check_interval_minutes)
            time.sleep(check_interval_minutes * 60)

    except KeyboardInterrupt:
        logging.info("收到中断信号，脚本结束。")
    except Exception as exc:
        logging.exception("运行失败: %s", exc)
        raise
    finally:
        if monitor is not None:
            monitor.close()


if __name__ == "__main__":
    main()
