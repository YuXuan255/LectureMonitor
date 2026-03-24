"""页面元素选择器与筛选配置。

说明：
1. 优先使用语义化定位（role/text）。
2. 这里保留少量可调整的 CSS 选择器，方便你手动调试。
"""

FILTER_CONFIG = [
    {"label": "活动大类", "option": "素质拓展认证"},
    {"label": "活动小类", "option": "形势与政策"},
    {"label": "小类子类", "option": "形势与政策讲座"},
    {"label": "活动状态", "option": "未开始"},
]

QUERY_BUTTON_TEXT = "查询"

# 长时间挂起后可能出现的网络异常提示弹窗
NETWORK_ISSUE_KEYWORDS = [
    "网络出错误了...刷新试试~~",
    "网络出错误了",
]
NETWORK_ISSUE_CONFIRM_TEXTS = [
    "确认",
    "确定",
]

# campus 页面当前结构（来自 target.html）
CAMPUS_FILTER_BLOCK_SELECTOR = "div.col-xs-6.col-sm-6.col-md-3"
CAMPUS_FILTER_LABEL_SELECTOR = "p.campus-search-p"
CAMPUS_FILTER_TOGGLE_SELECTORS = [
    "div.dropdown-box-md a.dropdown-toggle",
    "div.dropdown-box-md a.sl-header-dd",
]
CAMPUS_FILTER_OPTION_SELECTOR = "div.dropdown-box-md ul.dropdown-menu a"

# 常见 UI 库中的“筛选项容器”，用于在 label 附近查找下拉框触发器
FORM_ITEM_SELECTORS = [
    ".ant-form-item",
    ".el-form-item",
    ".ivu-form-item",
    ".form-item",
    ".search-item",
]

# 常见“下拉框触发器”选择器
DROPDOWN_TRIGGER_SELECTORS = [
    "[role='combobox']",
    ".ant-select-selector",
    ".el-select",
    ".el-input__inner",
    "input",
]

# 常见“下拉选项”选择器
DROPDOWN_OPTION_SELECTORS = [
    "[role='option']",
    ".ant-select-item-option",
    ".el-select-dropdown__item",
    ".ivu-select-item",
    "li",
]

# 结果列表行：按顺序尝试，命中第一个有内容的选择器
RESULT_ROW_SELECTORS = [
    ".serv-list .row.list-show",
    ".search-list .row.list-show",
    "table tbody tr",
    ".ant-table-tbody > tr",
    ".el-table__body-wrapper tbody tr",
    ".activity-item",
    ".ant-list-item",
    ".list-item",
    ".card-item",
]

TITLE_CANDIDATE_SELECTORS = [
    "a",
    "h2",
    "h3",
    "h4",
    ".title",
    ".activity-title",
    ".name",
]

STATUS_KEYWORDS = [
    "报名中",
    "报名已满员",
    "未开始",
    "进行中",
    "已结束",
    "已截止",
]
