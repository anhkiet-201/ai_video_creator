"""In-memory isolated logger for concurrent video render threads without writing to disk."""

from datetime import datetime
import threading
from typing import Callable, List, Optional


class TaskLogger:
    """Thread-isolated, in-memory logger collecting logs for a specific render plan.

    Avoids any disk I/O. Supports real-time streaming callback (e.g. for WebSocket/SSE).
    """

    def __init__(
        self,
        plan_id: str,
        on_log: Optional[Callable[[str, str, str], None]] = None,
    ):
        self.plan_id = plan_id
        self.on_log = on_log
        self._logs: List[str] = []
        self._lock = threading.Lock()

    def _log(self, level: str, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        thread_name = threading.current_thread().name
        formatted = f"[{timestamp}] [{level}] [Plan: {self.plan_id} | Thread: {thread_name}] {message}"

        with self._lock:
            self._logs.append(formatted)

        if self.on_log:
            try:
                self.on_log(self.plan_id, level, formatted)
            except Exception:
                pass

    def info(self, message: str, *args, **kwargs) -> None:
        self._log("INFO", message % args if args else str(message))

    def warning(self, message: str, *args, **kwargs) -> None:
        self._log("WARNING", message % args if args else str(message))

    def error(self, message: str, *args, **kwargs) -> None:
        self._log("ERROR", message % args if args else str(message))

    def debug(self, message: str, *args, **kwargs) -> None:
        self._log("DEBUG", message % args if args else str(message))

    def get_logs(self) -> List[str]:
        """Return a copy of all accumulated logs in memory."""
        with self._lock:
            return list(self._logs)

    def clear(self) -> None:
        """Clear the in-memory log buffer."""
        with self._lock:
            self._logs.clear()
