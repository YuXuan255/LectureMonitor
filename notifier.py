import logging
import smtplib
from datetime import datetime
from email.message import EmailMessage
from typing import Any

from models import Activity


class EmailNotifier:
    """SMTP 邮件通知器（新活动提醒 + 登录失效提醒）。"""

    def __init__(self, email_config: dict[str, Any] | None):
        self.email_config = email_config or {}

    def notify_new_activities(self, activities: list[Activity]) -> bool:
        """仅在存在新活动时发送提醒邮件。"""
        if not activities:
            logging.info("本次无新活动，不发送邮件。")
            return True

        ok, missing_fields = self._validate_config()
        if not ok:
            logging.warning(
                "邮件配置不完整，已跳过发送。缺少字段: %s",
                ", ".join(missing_fields),
            )
            return False

        now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        subject = f"[LectureMonitor] 发现 {len(activities)} 个新活动"
        body_lines = [
            "检测到新的“形势与政策讲座”相关活动：",
            f"检测时间：{now_text}",
            "",
        ]

        for index, activity in enumerate(activities, start=1):
            body_lines.append(f"{index}. 标题：{activity.title}")
            body_lines.append(f"   状态：{activity.status}")
            body_lines.append(f"   时间：{activity.time_text}")
            if activity.detail_url:
                body_lines.append(f"   链接：{activity.detail_url}")
            else:
                body_lines.append("   链接：未解析到活动直达链接")
            body_lines.append("")

        success = self._send_email(subject, "\n".join(body_lines))
        if success:
            logging.info("新活动提醒邮件发送成功，共 %d 条。", len(activities))
        else:
            logging.error("新活动提醒邮件发送失败。")
        return success

    def notify_login_invalid(self, reason: str) -> bool:
        """登录失效提醒邮件。"""
        ok, missing_fields = self._validate_config()
        if not ok:
            logging.warning(
                "邮件配置不完整，无法发送登录失效提醒。缺少字段: %s",
                ", ".join(missing_fields),
            )
            return False

        now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        subject = "[LectureMonitor] 登录状态失效，请手动重新登录"
        body = (
            "监控脚本检测到登录状态失效。\n"
            f"检测时间：{now_text}\n"
            f"原因：{reason}\n\n"
            "请手动打开脚本进行一次登录恢复。"
        )
        success = self._send_email(subject, body)
        if success:
            logging.info("登录失效提醒邮件发送成功。")
        else:
            logging.error("登录失效提醒邮件发送失败。")
        return success

    def _validate_config(self) -> tuple[bool, list[str]]:
        required_fields = [
            "smtp_host",
            "smtp_port",
            "sender",
            "password",
            "receiver",
        ]

        missing_fields: list[str] = []
        for field in required_fields:
            value = self.email_config.get(field)
            if value is None or str(value).strip() == "":
                missing_fields.append(field)

        return len(missing_fields) == 0, missing_fields

    def _build_message(self, subject: str, body: str) -> EmailMessage:
        sender = str(self.email_config.get("sender"))
        receiver = str(self.email_config.get("receiver"))

        message = EmailMessage()
        message["From"] = sender
        message["To"] = receiver
        message["Subject"] = subject
        message.set_content(body)
        return message

    def _send_email(self, subject: str, body: str) -> bool:
        message = self._build_message(subject, body)

        smtp_host = str(self.email_config.get("smtp_host"))
        smtp_port = int(self.email_config.get("smtp_port", 465))
        sender = str(self.email_config.get("sender"))
        password = str(self.email_config.get("password"))
        use_ssl = bool(self.email_config.get("use_ssl", True))

        try:
            if use_ssl:
                with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=20) as smtp:
                    smtp.login(sender, password)
                    smtp.send_message(message)
            else:
                with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as smtp:
                    smtp.ehlo()
                    if bool(self.email_config.get("use_starttls", True)):
                        smtp.starttls()
                        smtp.ehlo()
                    smtp.login(sender, password)
                    smtp.send_message(message)
            return True

        except (smtplib.SMTPException, OSError, TimeoutError) as exc:
            logging.exception("邮件发送失败: %s", exc)
            return False
