"""看門程式：讓蒐集程式持續執行（掛掉就重啟），回補程式定期接著做。

由 scripts/register_task.ps1 註冊的工作排程在登入時用 pythonw 啟動，不會開視窗。
手動執行：pythonw -m rugguard.supervisor
"""
import os
import socket
import subprocess
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# pythonw 啟動時 sys.executable 是 pythonw.exe；子程式用同目錄的 python.exe 才有 stdout
PYTHON = os.path.join(os.path.dirname(sys.executable), "python.exe")
LOCK_PORT = 47821
COLLECTOR_RESTART_SECONDS = 30
BACKFILL_RETRY_SECONDS = 600
BACKFILL_RERUN_SECONDS = 6 * 3600


def log(msg: str) -> None:
    with open(os.path.join(ROOT, "supervisor.log"), "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")


def launch(module: str, name: str) -> subprocess.Popen:
    out = open(os.path.join(ROOT, f"{name}.log"), "a", encoding="utf-8")
    err = open(os.path.join(ROOT, f"{name}.err.log"), "a", encoding="utf-8")
    proc = subprocess.Popen([PYTHON, "-u", "-X", "utf8", "-m", module], cwd=ROOT, stdout=out, stderr=err,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    log(f"started {module} pid={proc.pid}")
    return proc


def next_backfill_delay(exit_code: int) -> int:
    # 失敗（多半是 RPC 限流）10 分鐘後重試；成功則 6 小時後再跑一次補漏
    return BACKFILL_RETRY_SECONDS if exit_code else BACKFILL_RERUN_SECONDS


def main() -> None:
    lock = socket.socket()
    try:
        lock.bind(("127.0.0.1", LOCK_PORT))  # 同時只允許一個看門程式
    except OSError:
        log("another supervisor is running, exit")
        return

    collector = launch("rugguard.main", "collector")
    backfill, backfill_at = launch("rugguard.backfill", "backfill"), None
    while True:
        time.sleep(10)
        if collector.poll() is not None:
            log(f"collector exited code={collector.returncode}, restart in {COLLECTOR_RESTART_SECONDS}s")
            time.sleep(COLLECTOR_RESTART_SECONDS)
            collector = launch("rugguard.main", "collector")
        if backfill is not None and backfill.poll() is not None:
            delay = next_backfill_delay(backfill.returncode)
            log(f"backfill exited code={backfill.returncode}, next run in {delay}s")
            backfill, backfill_at = None, time.time() + delay
        if backfill is None and time.time() >= backfill_at:
            backfill = launch("rugguard.backfill", "backfill")


if __name__ == "__main__":
    main()
