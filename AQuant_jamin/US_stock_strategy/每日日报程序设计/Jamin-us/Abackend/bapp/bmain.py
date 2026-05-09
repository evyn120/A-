from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Dict

from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from routes.watchlist import router as watchlist_router
from routes.daily_report import router as daily_router

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
# ===================== 新增：原launcher.py的辅助函数 =====================
def _resource_root() -> Path:
    """PyInstaller 打包后资源解压目录；源码模式下就是项目根。"""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent.parent  # 调整路径：适配main.py的层级

def _writable_data_dir() -> Path:
    """用户自选股等可写数据放到 exe 同级 data/，源码模式下也一样。"""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent.parent.parent  # 调整路径：适配main.py的层级
    data_dir = base / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir

def _find_free_port(preferred: int = 8000, max_try: int = 20) -> int:
    """查找可用端口，默认从8000开始尝试"""
    for offset in range(max_try):
        port = preferred + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("没找到可用端口（8000~8020范围内）")

# ===================== 原有main.py的核心配置 =====================
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="福杰明美股决策看板",
    description="研究型美股核心股票看板，输出观望 / 试买 / 跟踪标签。",
    version="0.1.0",
)
app.include_router(watchlist_router)
app.include_router(daily_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ===================== 原有接口 =====================
@app.get("/healthz")
def healthz() -> Dict[str, str]:
    return {"status": "ok"}

@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")

# ===================== 新增：整合launcher的启动逻辑 =====================
def main() -> None:
    """整合后的启动入口：配置环境变量 + 查找端口 + 启动服务 + 打开浏览器"""
    # 1. 配置可写数据目录 & 环境变量
    data_dir = _writable_data_dir()
    os.environ.setdefault("USER_WATCHLIST_PATH", str(data_dir / "user_watchlist.json"))

    # 2. 配置资源根路径（适配PyInstaller打包）
    root = _resource_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    # 3. 查找可用端口 & 构建访问地址
    port = _find_free_port(8000)
    url = f"http://127.0.0.1:{port}"

    # 4. 控制台输出启动信息
    print("=" * 60)
    print(" 美股观察看板 · US Stock Watchdog")
    print("=" * 60)
    print(f" 本地地址: {url}")
    print(f" 自选股文件: {data_dir / 'user_watchlist.json'}")
    print(" 关闭本窗口即可停止服务")
    print("=" * 60)

    # 5. 延迟打开浏览器（避免服务未启动完成）
    def _open_browser_later() -> None:
        time.sleep(2.0)
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=_open_browser_later, daemon=True).start()

    # 6. 启动Uvicorn服务
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")

# ===================== 程序入口 =====================
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # noqa: BLE001
        print(f"\n启动失败: {exc}")
        input("\n按回车键退出...")