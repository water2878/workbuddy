"""
Claw 工具服务配置
Python 只是 AI 的手脚，不做决策。
"""
import os
import sys
import json
from pathlib import Path
from datetime import datetime

# ═══════════════════════════════════════════════════════
# 项目路径
# ═══════════════════════════════════════════════════════
_THIS_DIR = Path(__file__).parent.resolve()      # core/
BASE_DIR = _THIS_DIR.parent                       # 项目根目录

# 将子目录加入 sys.path
for _subdir in ["core", "sender", "contract"]:
    _p = str(BASE_DIR / _subdir)
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ═══════════════════════════════════════════════════════
# 环境初始化
# ═══════════════════════════════════════════════════════
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

if sys.platform == "win32":
    os.system("")
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ═══════════════════════════════════════════════════════
# 外部服务配置
# ═══════════════════════════════════════════════════════
# WeFlow（微信数据库读取 + SSE推送）
WEFLOW_BASE = os.environ.get("WEFLOW_BASE", "http://127.0.0.1:5031")
WEFLOW_TOKEN = os.environ.get("WEFLOW_TOKEN", "")

# 工具 API 服务
API_HOST = os.environ.get("API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("API_PORT", "5032"))

# 云端合同服务器
CLOUD_SERVER = os.environ.get("CLOUD_SERVER", "")
CLOUD_TOKEN = os.environ.get("CLOUD_TOKEN", "")
SALES_ID = os.environ.get("SALES_ID", "")

# 云端产品图片存储配置
CLOUD_IMAGES_ENABLED = os.environ.get("CLOUD_IMAGES_ENABLED", "false").lower() == "true"
CLOUD_IMAGES_SERVER = os.environ.get("CLOUD_IMAGES_SERVER", CLOUD_SERVER)  # 默认使用合同服务器

# 合同审批通知联系人（微信昵称）
APPROVAL_CONTACT = os.environ.get("APPROVAL_CONTACT", "")

# 资料员联系人（产品缺少图片时通知）
MATERIALS_CONTACT = os.environ.get("MATERIALS_CONTACT", "")

# 客户无忧 API 配置
KEHU51_API_URL = os.environ.get("KEHU51_API_URL", "https://openapi.kehu51.com/v1/openapi/551906/01G04l4572C9bc1")

# ═══════════════════════════════════════════════════════
# 目录常量
# ═══════════════════════════════════════════════════════
PRODUCT_IMAGES_DIR = str(BASE_DIR / "assets" / "images")
KNOWLEDGE_BASE_DIR = str(BASE_DIR / "assets" / "products")
DATA_DIR = str(BASE_DIR / "data")
CACHE_DIR = str(BASE_DIR / "data" / "cache")
CONTRACTS_DIR = str(BASE_DIR / "data" / "contracts")
CUSTOMERS_DIR = str(BASE_DIR / "data" / "customers")
LOG_DIR = str(BASE_DIR / "logs")  # 独立日志目录

# 确保关键目录存在
for _d in [DATA_DIR, CACHE_DIR, CONTRACTS_DIR, CUSTOMERS_DIR,
           str(BASE_DIR / "data" / "contracts" / "images"), LOG_DIR,
           PRODUCT_IMAGES_DIR, KNOWLEDGE_BASE_DIR]:
    os.makedirs(_d, exist_ok=True)

# ═══════════════════════════════════════════════════════
# 动态配置（可运行时修改）
# ═══════════════════════════════════════════════════════

# 型号别名映射文件
MODEL_ALIAS_FILE = str(BASE_DIR / "data" / "model_aliases.json")


def load_model_aliases() -> dict:
    """加载型号别名映射"""
    try:
        if os.path.exists(MODEL_ALIAS_FILE):
            with open(MODEL_ALIAS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log(f"[配置] 加载型号别名失败: {e}")
    return {}


def save_model_aliases(aliases: dict):
    """保存型号别名映射"""
    try:
        with open(MODEL_ALIAS_FILE, "w", encoding="utf-8") as f:
            json.dump(aliases, f, ensure_ascii=False, indent=2)
        log(f"[配置] 已保存 {len(aliases)} 个型号别名")
    except Exception as e:
        log(f"[配置] 保存型号别名失败: {e}")


# ═══════════════════════════════════════════════════════
# MIME 映射
# ═══════════════════════════════════════════════════════
MIME_MAP = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
}

# ═══════════════════════════════════════════════════════
# 日志（独立文件夹）
# ═══════════════════════════════════════════════════════
LOG_FILE = str(BASE_DIR / "logs" / f"claw_{datetime.now().strftime('%Y%m%d')}.log")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
_log_fp = open(LOG_FILE, "a", encoding="utf-8")


def log(text: str, tag: str = "INFO"):
    """统一输出: 控制台 + 日志文件"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{tag}] {text}"

    # 写入日志文件（优先保证文件记录）
    try:
        _log_fp.write(line + "\n")
        _log_fp.flush()
    except Exception as e:
        # 文件写入失败时尝试用 stderr
        import sys
        sys.stderr.write(f"[LOG FILE ERROR] {e}\n")

    # 输出到控制台（带错误处理和编码修复）
    try:
        print(line, flush=True)
    except (OSError, AttributeError) as e:
        # 控制台输出失败，尝试用 stderr 或忽略
        try:
            import sys
            # 尝试用 utf-8 编码输出
            encoded = line.encode('utf-8', errors='replace').decode('utf-8')
            sys.stderr.write(encoded + "\n")
            sys.stderr.flush()
        except:
            pass
    except UnicodeEncodeError:
        # 编码错误时尝试用替代字符
        try:
            import sys
            safe_line = line.encode('utf-8', errors='replace').decode('utf-8')
            print(safe_line, flush=True)
        except:
            pass


# ═══════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════
def load_json(path: str, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else []


def save_json(path: str, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
