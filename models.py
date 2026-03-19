from dataclasses import dataclass


@dataclass
class Activity:
    """单条活动信息。"""

    title: str
    status: str
    time_text: str
    detail_url: str = ""

    def unique_key(self) -> str:
        """生成活动唯一键（阶段二用于历史记录去重）。"""
        safe_title = self.title.strip()
        safe_time = self.time_text.strip()
        return f"{safe_title}||{safe_time}"
