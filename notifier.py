import logging
import smtplib
from datetime import datetime
from email.message import EmailMessage
from typing import Any

from models import Activity


class EmailNotifier:
    """SMTP 邮件通知器（新活动提醒 + 登录失效提醒）。"""

    def __init__(self, email_config: dict[str, Any] | None, main_user: Any = None):
        self.email_config = email_config or {}
        self.main_user_receivers = self._normalize_receivers(main_user)

    def notify_new_activities(self, activities: list[Activity]) -> bool:
        """仅在存在新活动时发送提醒邮件。"""
        if not activities:
            logging.info("本次无新活动，不发送邮件。")
            return True

        receivers = self._get_receivers()
        ok, missing_fields = self._validate_config(receivers, receivers_field_name="email.receivers")
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

        success = self._send_email(subject, "\n".join(body_lines), receivers)
        if success:
            logging.info("新活动提醒邮件发送成功，共 %d 条。", len(activities))
        else:
            logging.error("新活动提醒邮件发送失败。")
        return success

    def notify_login_invalid(self, reason: str) -> bool:
        """登录失效提醒邮件。"""
        ok, missing_fields = self._validate_config(
            self.main_user_receivers,
            receivers_field_name="main_user",
        )
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
        success = self._send_email(subject, body, self.main_user_receivers)
        if success:
            logging.info("登录失效提醒邮件发送成功。")
        else:
            logging.error("登录失效提醒邮件发送失败。")
        return success

    def _validate_config(
        self,
        receivers: list[str],
        receivers_field_name: str,
    ) -> tuple[bool, list[str]]:
        required_fields = [
            "smtp_host",
            "smtp_port",
            "sender",
            "password",
        ]

        missing_fields: list[str] = []
        for field in required_fields:
            value = self.email_config.get(field)
            if value is None or str(value).strip() == "":
                missing_fields.append(field)

        if not receivers:
            missing_fields.append(receivers_field_name)

        return len(missing_fields) == 0, missing_fields

    def _build_message(self, subject: str, body: str, receivers: list[str]) -> EmailMessage:
        sender = str(self.email_config.get("sender"))

        message = EmailMessage()
        message["From"] = sender
        message["To"] = ", ".join(receivers)
        message["Subject"] = subject
        message.set_content(body)
        return message

    def _get_receivers(self) -> list[str]:
        """读取常规通知收件人（email.receivers）。"""
        return self._normalize_receivers(self.email_config.get("receivers"))

    def _normalize_receivers(self, raw_receivers: Any) -> list[str]:
        """解析并去重收件人列表。"""
        candidates: list[str] = []

        if isinstance(raw_receivers, list):
            for item in raw_receivers:
                text = str(item).strip()
                if text:
                    candidates.append(text)
        elif isinstance(raw_receivers, str):
            for part in raw_receivers.replace(";", ",").split(","):
                text = part.strip()
                if text:
                    candidates.append(text)

        # 去重并保持顺序
        deduped: list[str] = []
        seen: set[str] = set()
        for email in candidates:
            key = email.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(email)
        return deduped

    def _send_email(self, subject: str, body: str, receivers: list[str]) -> bool:
        message = self._build_message(subject, body, receivers)

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
