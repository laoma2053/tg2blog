"""常量定义"""

# 资源分类
CATEGORY_MOVIE = "电影"
CATEGORY_TV = "剧集"
CATEGORY_ANIME = "动漫"
CATEGORY_VARIETY = "综艺"
CATEGORY_SOFTWARE = "软件"
CATEGORY_COURSE = "课程"
CATEGORY_OTHER = "其他"

CATEGORIES = [
    CATEGORY_MOVIE,
    CATEGORY_TV,
    CATEGORY_ANIME,
    CATEGORY_VARIETY,
    CATEGORY_SOFTWARE,
    CATEGORY_COURSE,
    CATEGORY_OTHER,
]

# 网盘类型
DRIVE_TYPE_ALIPAN = "alipan"
DRIVE_TYPE_QUARK = "quark"
DRIVE_TYPE_BAIDU = "baidu"
DRIVE_TYPE_UC = "uc"
DRIVE_TYPE_XUNLEI = "xunlei"

# 处理状态
STATUS_SKIP = "skip"
STATUS_MERGED = "merged"
STATUS_PUBLISHED = "published"
STATUS_ERROR = "error"

# 标题噪声词
NOISE_WORDS = [
    "4K", "1080P", "2160P", "高清", "超清", "国语", "中字", "双语",
    "完整版", "高码版", "夸克", "百度", "阿里", "网盘", "全集"
]
