import logging
import re
from pathlib import Path
from typing import Any, Optional

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from models import Activity
import page_selectors as selectors


class LoginRequiredError(RuntimeError):
    """登录状态不可用，需要用户手动重新登录。"""


class LectureMonitor:
    """活动页面监控核心流程。"""

    def __init__(self, config: dict[str, Any]):
        self.url = config["url"]

        browser_config = config.get("browser", {})
        self.headless = bool(browser_config.get("headless", False))
        self.slow_mo_ms = int(browser_config.get("slow_mo_ms", 0))
        self.profile_dir = Path(browser_config.get("profile_dir", "data/browser_profile"))

        timeout_config = config.get("timeouts", {})
        self.page_load_ms = int(timeout_config.get("page_load_ms", 30000))
        self.ui_wait_ms = int(timeout_config.get("ui_wait_ms", 8000))
        # 登录检测前给页面一点渲染时间，避免过早判定登录失效
        self.login_check_delay_ms = int(timeout_config.get("login_check_delay_ms", 3500))
        # 手动登录后，自动回到目标页的重试参数
        self.login_recover_retry_count = int(timeout_config.get("login_recover_retry_count", 4))
        self.login_recover_retry_wait_ms = int(timeout_config.get("login_recover_retry_wait_ms", 2000))

        self.profile_dir.mkdir(parents=True, exist_ok=True)

    def run_once(self, allow_manual_login: bool = False) -> list[Activity]:
        """执行一次完整流程：进入页面、筛选、查询、解析结果。"""
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=self.headless,
                slow_mo=self.slow_mo_ms,
            )

            page = context.new_page()
            logging.info("打开页面: %s", self.url)
            page.goto(self.url, wait_until="domcontentloaded", timeout=self.page_load_ms)
            self._wait_before_login_check(page)

            self._ensure_login(page, allow_manual_login=allow_manual_login)
            self._apply_filters(page)
            self._click_query(page)

            activities = self._parse_activities(page)
            logging.info("本次解析到 %d 条活动", len(activities))

            context.close()
            return activities

    def _ensure_login(self, page: Page, allow_manual_login: bool) -> None:
        """检测登录状态；失效时抛出登录异常或进入手动恢复流程。"""
        if self._has_search_filters(page):
            logging.info("检测到筛选区域，登录状态可用。")
            return

        # 兼容前端异步渲染：首次未命中时再等一轮再判定
        logging.info("筛选区域首次未出现，等待页面继续渲染后重试。")
        self._wait_before_login_check(page)
        if self._has_search_filters(page):
            logging.info("重试后检测到筛选区域，登录状态可用。")
            return

        logging.warning("暂未检测到筛选区域，可能尚未登录或登录失效。")
        if not allow_manual_login:
            raise LoginRequiredError("未检测到筛选区域，当前登录状态可能失效。")

        input("请在打开的浏览器中手动登录，然后回到终端按回车继续... ")
        if self._recover_to_target_search_page(page):
            logging.info("手动登录后已成功回到目标检索页。")
            return

        self._print_login_debug_tips()
        raise LoginRequiredError("手动登录后仍未检测到筛选区域（已尝试自动跳回目标页）。")

    def _has_search_filters(self, page: Page) -> bool:
        """粗略判断：页面是否存在筛选标签文本。"""
        hit_count = 0
        for item in selectors.FILTER_CONFIG:
            label = item["label"]
            if page.get_by_text(label, exact=False).count() > 0:
                hit_count += 1

        return hit_count >= 2

    def _apply_filters(self, page: Page) -> None:
        """按规格依次设置四个筛选项。"""
        for item in selectors.FILTER_CONFIG:
            label = item["label"]
            option = item["option"]
            logging.info("设置筛选：%s -> %s", label, option)
            success = self._set_single_filter(page, label, option)
            if not success:
                self._print_filter_debug_tips(label, option)
                raise RuntimeError(f"筛选失败：{label} -> {option}")
            page.wait_for_timeout(250)

    def _set_single_filter(self, page: Page, label: str, option: str) -> bool:
        """设置单个筛选项，使用多种稳健定位策略。"""
        if self._set_filter_in_campus_block(page, label, option):
            return True

        if self._open_dropdown_by_role(page, label) and self._click_dropdown_option(page, option):
            return True

        if self._open_dropdown_near_label(page, label) and self._click_dropdown_option(page, option):
            return True

        if self._open_dropdown_by_label_text(page, label) and self._click_dropdown_option(page, option):
            return True

        return False

    def _set_filter_in_campus_block(self, page: Page, label: str, option: str) -> bool:
        """策略 0：按 target.html 的搜索区块结构定位并选择。"""
        label_match = page.locator(selectors.CAMPUS_FILTER_LABEL_SELECTOR, has_text=label)
        blocks = page.locator(selectors.CAMPUS_FILTER_BLOCK_SELECTOR).filter(has=label_match)
        if blocks.count() == 0:
            return False

        block = blocks.first
        toggle_selector = ", ".join(selectors.CAMPUS_FILTER_TOGGLE_SELECTORS)
        toggles = block.locator(toggle_selector)
        if toggles.count() == 0:
            return False

        try:
            toggles.first.click(timeout=self.ui_wait_ms)
        except PlaywrightTimeoutError:
            return False

        # 优先精确匹配，避免“形势与政策”误点“形势与政策讲座”
        exact_option = block.locator(selectors.CAMPUS_FILTER_OPTION_SELECTOR).filter(
            has_text=re.compile(rf"^\\s*{re.escape(option)}\\s*$")
        )
        if exact_option.count() > 0:
            try:
                exact_option.first.click(timeout=self.ui_wait_ms)
                return True
            except PlaywrightTimeoutError:
                return False

        fuzzy_option = block.locator(selectors.CAMPUS_FILTER_OPTION_SELECTOR).filter(has_text=option)
        if fuzzy_option.count() == 0:
            return False

        try:
            fuzzy_option.first.click(timeout=self.ui_wait_ms)
            return True
        except PlaywrightTimeoutError:
            return False

    def _open_dropdown_by_role(self, page: Page, label: str) -> bool:
        """策略 1：通过 ARIA role + 可访问名称定位下拉框。"""
        try:
            combobox = page.get_by_role("combobox", name=re.compile(label))
            if combobox.count() == 0:
                return False
            combobox.first.click(timeout=self.ui_wait_ms)
            return True
        except PlaywrightTimeoutError:
            return False

    def _open_dropdown_near_label(self, page: Page, label: str) -> bool:
        """策略 2：在常见表单项容器中，查找带指定 label 的下拉触发器。"""
        for form_selector in selectors.FORM_ITEM_SELECTORS:
            form_items = page.locator(form_selector).filter(has_text=label)
            if form_items.count() == 0:
                continue

            form_item = form_items.first
            for trigger_selector in selectors.DROPDOWN_TRIGGER_SELECTORS:
                trigger = form_item.locator(trigger_selector)
                if trigger.count() == 0:
                    continue

                try:
                    trigger.first.click(timeout=self.ui_wait_ms)
                    return True
                except PlaywrightTimeoutError:
                    continue

        return False

    def _open_dropdown_by_label_text(self, page: Page, label: str) -> bool:
        """策略 3：直接点击标签文本，适配部分自定义 UI。"""
        try:
            label_node = page.get_by_text(label, exact=False)
            if label_node.count() == 0:
                return False

            label_node.first.click(timeout=self.ui_wait_ms)
            return True
        except PlaywrightTimeoutError:
            return False

    def _click_dropdown_option(self, page: Page, option: str) -> bool:
        """在已展开的下拉中选择目标项。"""
        try:
            option_by_role = page.get_by_role("option", name=option)
            if option_by_role.count() > 0:
                option_by_role.first.click(timeout=self.ui_wait_ms)
                return True
        except PlaywrightTimeoutError:
            pass

        for option_selector in selectors.DROPDOWN_OPTION_SELECTORS:
            option_node = page.locator(option_selector).filter(has_text=option)
            if option_node.count() == 0:
                continue

            try:
                option_node.first.click(timeout=self.ui_wait_ms)
                return True
            except PlaywrightTimeoutError:
                continue

        try:
            text_node = page.get_by_text(option, exact=True)
            if text_node.count() > 0:
                text_node.first.click(timeout=self.ui_wait_ms)
                return True
        except PlaywrightTimeoutError:
            pass

        return False

    def _click_query(self, page: Page) -> None:
        """点击“查询”按钮。"""
        try:
            button = page.get_by_role("button", name=selectors.QUERY_BUTTON_TEXT)
            if button.count() > 0:
                button.first.click(timeout=self.ui_wait_ms)
                return
        except PlaywrightTimeoutError:
            pass

        text_button = page.get_by_text(selectors.QUERY_BUTTON_TEXT, exact=True)
        if text_button.count() == 0:
            raise RuntimeError("未找到“查询”按钮。")

        text_button.first.click(timeout=self.ui_wait_ms)

    def _parse_activities(self, page: Page) -> list[Activity]:
        """解析活动列表，提取标题、状态、时间。"""
        page.wait_for_timeout(1200)

        rows = self._find_result_rows(page)
        if rows is None:
            self._print_result_debug_tips()
            return []

        total = rows.count()
        activities: list[Activity] = []
        for idx in range(total):
            row = rows.nth(idx)
            activity = self._extract_activity(row)
            if activity is not None:
                activities.append(activity)

        return activities

    def _find_result_rows(self, page: Page) -> Optional[Locator]:
        """按顺序尝试多个结果行选择器。"""
        for row_selector in selectors.RESULT_ROW_SELECTORS:
            rows = page.locator(row_selector)
            if rows.count() > 0:
                logging.info("使用结果选择器: %s", row_selector)
                return rows

        return None

    def _extract_activity(self, row: Locator) -> Optional[Activity]:
        """从单行中提取活动字段。"""
        row_text = self._safe_inner_text(row)
        if not row_text:
            return None

        title = self._extract_title(row, row_text)
        if not title:
            return None

        status = self._extract_status(row_text)
        time_text = self._extract_time(row_text)
        return Activity(title=title, status=status, time_text=time_text)

    def _extract_title(self, row: Locator, row_text: str) -> str:
        """优先从常见标题节点提取；失败再从整行文本推断。"""
        for selector in selectors.TITLE_CANDIDATE_SELECTORS:
            title_node = row.locator(selector)
            if title_node.count() == 0:
                continue

            candidate = self._safe_inner_text(title_node.first)
            if candidate:
                return candidate

        lines = [line.strip() for line in row_text.splitlines() if line.strip()]
        for line in lines:
            if any(keyword in line for keyword in selectors.STATUS_KEYWORDS):
                continue
            if self._contains_date(line):
                continue
            return line

        return ""

    def _extract_status(self, row_text: str) -> str:
        """根据关键词提取状态文本。"""
        for keyword in selectors.STATUS_KEYWORDS:
            if keyword in row_text:
                return keyword
        return "未知"

    def _extract_time(self, row_text: str) -> str:
        """提取时间文本（兼容常见日期格式）。"""
        time_pattern = re.compile(
            r"(\d{4}[./-]\d{1,2}[./-]\d{1,2}(?:\s+\d{1,2}:\d{2})?"
            r"(?:\s*[~\-至到]\s*\d{4}[./-]\d{1,2}[./-]\d{1,2}(?:\s+\d{1,2}:\d{2})?)?)"
        )

        match = time_pattern.search(row_text)
        if match:
            return match.group(1)

        return "未识别"

    def _contains_date(self, text: str) -> bool:
        return bool(re.search(r"\d{4}[./-]\d{1,2}[./-]\d{1,2}", text))

    def _safe_inner_text(self, locator: Locator) -> str:
        """安全读取文本，避免因局部节点异常导致整体流程中断。"""
        try:
            return locator.inner_text(timeout=800).strip()
        except PlaywrightTimeoutError:
            return ""

    def _wait_before_login_check(self, page: Page) -> None:
        """登录检测前等待页面稳定，降低误判率。"""
        try:
            # 若页面很快稳定，这里会提前返回；否则最多等待 5 秒
            page.wait_for_load_state("networkidle", timeout=min(self.page_load_ms, 5000))
        except PlaywrightTimeoutError:
            # 某些页面网络请求常驻，networkidle 可能不会触发，忽略即可
            pass

        if self.login_check_delay_ms > 0:
            page.wait_for_timeout(self.login_check_delay_ms)

    def _recover_to_target_search_page(self, page: Page) -> bool:
        """登录后自动跳回目标页面并多次重试，处理被重定向到大厅首页的情况。"""
        for attempt in range(1, self.login_recover_retry_count + 1):
            logging.info(
                "登录恢复：尝试回到目标检索页（%d/%d）",
                attempt,
                self.login_recover_retry_count,
            )
            page.goto(self.url, wait_until="domcontentloaded", timeout=self.page_load_ms)
            self._wait_before_login_check(page)

            if self._has_search_filters(page):
                return True

            if self.login_recover_retry_wait_ms > 0:
                page.wait_for_timeout(self.login_recover_retry_wait_ms)

        return False

    def _print_login_debug_tips(self) -> None:
        logging.error("TODO: 登录后仍未识别筛选区。请检查页面是否停留在活动检索页。")
        logging.error("调试建议：确认 URL 是否为 /campus#/search，且页面已完全加载。")

    def _print_filter_debug_tips(self, label: str, option: str) -> None:
        logging.error("TODO: 无法定位筛选项 -> %s / %s", label, option)
        logging.error("调试建议：使用浏览器开发者工具检查该筛选框的标签文本和下拉 DOM 结构。")
        logging.error("调试建议：若页面使用了新组件，请在 page_selectors.py 中补充容器与选项选择器。")

    def _print_result_debug_tips(self) -> None:
        logging.warning("TODO: 查询后未匹配到结果行选择器。")
        logging.warning("调试建议：检查列表是 table 还是 card，并在 page_selectors.py 的 RESULT_ROW_SELECTORS 中补充。")
