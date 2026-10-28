"""Serialize online detection and document inference without stopping either service."""
from contextlib import contextmanager
import os
from pathlib import Path

@contextmanager
def document_slot(runtime,neural=False):
    from campus_workbench.training import compute_slot
    with compute_slot(runtime,False):
        if neural:
            import psutil
            legacy=('construct_correspondence.py','run_campus_stage.py','train_text_models.py','train_retrieval.py','train_correspondence.py')
            for process in psutil.process_iter(['pid','cmdline']):
                try:
                    if process.pid!=os.getpid() and any(Path(arg).name in legacy for arg in (process.info['cmdline'] or [])):
                        raise BlockingIOError('既有GPU任务运行中')
                except (psutil.AccessDenied,psutil.NoSuchProcess):
                    continue
        yield
