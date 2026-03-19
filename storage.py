import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from models import Activity


class ActivityStorage:
    """负责读取/写入已见活动，并识别新活动。"""

    def __init__(self, file_path: str | Path = "data/seen_activities.json"):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def classify_and_update(self, activities: list[Activity]) -> tuple[list[Activity], list[Activity]]:
        """将本次活动分成普通活动与新活动，并更新本地 JSON 记录。"""
        records = self._load_records()
        ordinary_activities: list[Activity] = []
        new_activities: list[Activity] = []

        seen_at = datetime.now().isoformat(timespec="seconds")
        for activity in activities:
            key = activity.unique_key()
            existing = records.get(key)

            if existing is None:
                new_activities.append(activity)
            else:
                ordinary_activities.append(activity)

            records[key] = self._build_record(activity, existing, seen_at)

        self._save_records(records)
        logging.info(
            "历史记录已更新：%s（当前累计 %d 条）",
            self.file_path,
            len(records),
        )

        return ordinary_activities, new_activities

    def _load_records(self) -> dict[str, dict[str, Any]]:
        if not self.file_path.exists():
            return {}

        try:
            with self.file_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError:
            logging.warning("历史记录 JSON 格式损坏，将按空记录处理：%s", self.file_path)
            return {}
        except OSError as exc:
            logging.warning("读取历史记录失败，将按空记录处理：%s", exc)
            return {}

        if not isinstance(data, dict):
            logging.warning("历史记录格式不是对象，将按空记录处理：%s", self.file_path)
            return {}

        return data

    def _save_records(self, records: dict[str, dict[str, Any]]) -> None:
        with self.file_path.open("w", encoding="utf-8") as file:
            json.dump(records, file, ensure_ascii=False, indent=2)

    def _build_record(
        self,
        activity: Activity,
        existing: Optional[dict[str, Any]],
        seen_at: str,
    ) -> dict[str, Any]:
        first_seen_at = seen_at
        if isinstance(existing, dict) and existing.get("first_seen_at"):
            first_seen_at = str(existing["first_seen_at"])

        return {
            "title": activity.title,
            "status": activity.status,
            "time_text": activity.time_text,
            "detail_url": activity.detail_url,
            "first_seen_at": first_seen_at,
            "last_seen_at": seen_at,
        }
