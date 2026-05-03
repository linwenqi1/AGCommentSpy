# config.py

# ========== 设备配置 ==========
DEVICE_ID = "6CS9K25C03021298"

# ========== 屏幕尺寸 ==========
SCREEN_WIDTH = 1084
SCREEN_HEIGHT = 2412

# ========== XPath 常量 ==========
APP_TITLE = '//*[@id="descript_sub_box"]//Text[1]'
APP_SUBTITLE = '//*[@id="descript_sub_box"]/Button/Stack/Text'

# 评论相关
VIEW_ALL_COMMENTS = '//Button[@text="查看全部"]'
SORT_BY_LATEST = '//*[@id="AllRateCommentsSegmentButton"]/Stack[1]/Row[1]/Button[2]'
# Comment list
COMMENT_LIST_BASE = '//root[1]/SheetWrapper[1]/SheetPage[1]/Scroll[1]/Navigation[1]/NavBar[1]/NavBarContent[1]/NavDestination[1]/NavDestinationContent[1]/Column[1]/Stack[1]/Column[1]/List[1]'
COMMENT_ITEMS = f'{COMMENT_LIST_BASE}/ListItem'

# Inside each comment (use starts-with to handle dynamic index suffix)
COMMENT_USERNAME = './/*[@description="单指双击可跳转至个人中心"]//Text[1]'
COMMENT_RATING   = './/*[starts-with(@id,"CommentDetailStarsStack")]//Rating[1]'
COMMENT_TEXT     = './/*[starts-with(@id,"CommentDetailTextContainer")]//Text[1]'
COMMENT_META = './/*[starts-with(@id,"CommentDetailPostInfo") and not(contains(@id,"AndOperation"))]'