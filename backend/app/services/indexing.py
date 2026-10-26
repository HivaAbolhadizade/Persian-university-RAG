from __future__ import annotations

import json
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from backend.app.config import Settings


class IndexRebuildManager:
    def __init__(
        self,
        settings: Settings,
        reload_callback: Callable[[], None],
    ) -> None:
        self.settings = settings
        self.reload_callback = reload_callback
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self.state = {
            "status": "idle",
            "started_at": None,
            "finished_at": None,
            "current_stage": None,
            "error": None,
            "log_path": None,
        }
        self.settings.backend_runtime_path.mkdir(parents=True, exist_ok=True)
        self.state_path = self.settings.backend_runtime_path / "index_rebuild_status.json"
        self._write_state()

    def _write_state(self) -> None:
        self.state_path.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def status(self) -> dict:
        with self._lock:
            return dict(self.state)

    def start(
        self,
        run_data_preparation: bool,
        run_retrieval: bool,
    ) -> bool:
        if not self.settings.enable_index_rebuild:
            raise PermissionError("Index rebuild is disabled by configuration.")

        with self._lock:
            if self._thread and self._thread.is_alive():
                return False
            self._thread = threading.Thread(
                target=self._run,
                args=(run_data_preparation, run_retrieval),
                daemon=True,
            )
            self._thread.start()
            return True

    def _run(self, run_data_preparation: bool, run_retrieval: bool) -> None:
        started = datetime.now(timezone.utc)
        log_path = (
            self.settings.backend_runtime_path
            / f"index_rebuild_{started.strftime('%Y%m%d_%H%M%S')}.log"
        )
        with self._lock:
            self.state.update(
                {
                    "status": "running",
                    "started_at": started.isoformat(),
                    "finished_at": None,
                    "current_stage": "starting",
                    "error": None,
                    "log_path": str(log_path),
                }
            )
            self._write_state()

        try:
            notebooks: list[tuple[str, Path]] = []
            if run_data_preparation:
                notebooks.append(
                    (
                        "data_preparation",
                        self.settings.university_rag_root
                        / self.settings.rebuild_notebook_01,
                    )
                )
            if run_retrieval:
                notebooks.append(
                    (
                        "retrieval",
                        self.settings.university_rag_root
                        / self.settings.rebuild_notebook_02,
                    )
                )
            if not notebooks:
                raise ValueError("No rebuild stage was selected.")

            with log_path.open("w", encoding="utf-8") as log:
                for stage, notebook in notebooks:
                    if not notebook.exists():
                        raise FileNotFoundError(f"Notebook not found: {notebook}")

                    with self._lock:
                        self.state["current_stage"] = stage
                        self._write_state()

                    command = [
                        sys.executable,
                        "-m",
                        "jupyter",
                        "nbconvert",
                        "--to",
                        "notebook",
                        "--execute",
                        "--inplace",
                        "--ExecutePreprocessor.timeout=-1",
                        str(notebook),
                    ]
                    subprocess.run(
                        command,
                        cwd=self.settings.university_rag_root,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        text=True,
                        check=True,
                    )

            with self._lock:
                self.state["current_stage"] = "reloading_backend"
                self._write_state()
            self.reload_callback()

            with self._lock:
                self.state.update(
                    {
                        "status": "completed",
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                        "current_stage": "completed",
                    }
                )
                self._write_state()
        except Exception as exc:
            with self._lock:
                self.state.update(
                    {
                        "status": "failed",
                        "finished_at": datetime.now(timezone.utc).isoformat(),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                self._write_state()
