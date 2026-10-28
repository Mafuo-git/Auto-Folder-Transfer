from __future__ import annotations

import json
import os
import queue
import shutil
import threading
import time
import tkinter as tk
import uuid
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer


APP_NAME = "Assetto Corsa - transfert Motec"
CONFIG_PATH = (
    Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    / "AssettoCorsaAutoTransfer"
    / "config.json"
)


def target_path(source_file: Path, source_root: Path, destination_root: Path) -> Path:
    return destination_root / source_file.relative_to(source_root)


def move_to_available_path(temporary_file: Path, destination_file: Path) -> Path:
    extension = "".join(destination_file.suffixes)
    filename_stem = destination_file.name[: -len(extension)] if extension else destination_file.name
    index = 0

    while True:
        if index == 0:
            candidate = destination_file
        else:
            candidate = destination_file.with_name(
                f"{filename_stem} ({index}){extension}"
            )
        try:
            os.rename(temporary_file, candidate)
            return candidate
        except FileExistsError:
            index += 1


def validate_folders(source: Path, destination: Path) -> tuple[Path, Path]:
    source = source.expanduser().resolve()
    destination = destination.expanduser().resolve()
    if not source.is_dir():
        raise ValueError(f"Le dossier source n'existe pas ou n'est pas accessible :\n{source}")
    if source == destination:
        raise ValueError("Les dossiers source et destination doivent être différents.")
    try:
        destination.relative_to(source)
    except ValueError:
        pass
    else:
        raise ValueError("Le dossier destination ne peut pas être à l'intérieur du dossier source.")
    destination.mkdir(parents=True, exist_ok=True)
    if not destination.is_dir():
        raise ValueError(f"Le dossier destination n'est pas accessible :\n{destination}")
    return source, destination


class TransferHandler(FileSystemEventHandler):
    def __init__(self, enqueue_file) -> None:
        self.enqueue_file = enqueue_file

    def on_created(self, event: FileSystemEvent) -> None:
        self._handle(event)

    def on_modified(self, event: FileSystemEvent) -> None:
        self._handle(event)

    def on_moved(self, event: FileSystemEvent) -> None:
        self.enqueue_file(Path(event.dest_path))

    def _handle(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.enqueue_file(Path(event.src_path))


class TransferService:
    def __init__(self, notify) -> None:
        self.notify = notify
        self.source: Path | None = None
        self.destination: Path | None = None
        self.observer: Observer | None = None
        self.work_queue: queue.Queue[Path | None] = queue.Queue()
        self.pending: set[Path] = set()
        self.pending_lock = threading.Lock()
        self.worker: threading.Thread | None = None

    def start(self, source: Path, destination: Path) -> None:
        if self.observer is not None:
            return
        self.source, self.destination = validate_folders(source, destination)
        self.worker = threading.Thread(target=self._work, daemon=True)
        self.worker.start()
        observer = Observer()
        try:
            observer.schedule(TransferHandler(self._enqueue), str(self.source), recursive=True)
            observer.start()
        except (OSError, RuntimeError):
            self.work_queue.put(None)
            self.worker.join(timeout=2)
            self.worker = None
            self.source = None
            self.destination = None
            raise
        self.observer = observer
        self.notify("status", f"Surveillance active : {self.source}")

    def stop(self) -> None:
        observer = self.observer
        self.observer = None
        if observer is not None:
            observer.stop()
            observer.join(timeout=5)
        if self.worker is not None:
            self.work_queue.put(None)
            self.worker.join(timeout=5)
            self.worker = None
        with self.pending_lock:
            self.pending.clear()
        self.source = None
        self.destination = None
        self.notify("status", "Transfert automatique désactivé.")

    def _enqueue(self, path: Path) -> None:
        if self.source is None:
            return
        try:
            relative = path.resolve().relative_to(self.source)
        except (OSError, ValueError):
            return
        if not relative.parts:
            return
        with self.pending_lock:
            if path in self.pending:
                return
            self.pending.add(path)
        self.work_queue.put(path)

    def _work(self) -> None:
        while True:
            path = self.work_queue.get()
            if path is None:
                return
            try:
                self._transfer(path)
            except (OSError, RuntimeError, ValueError) as error:
                self.notify("error", f"Échec du transfert de {path.name} : {error}")
            finally:
                with self.pending_lock:
                    self.pending.discard(path)

    def _transfer(self, source_file: Path) -> None:
        source_root = self.source
        destination_root = self.destination
        if source_root is None or destination_root is None:
            return
        try:
            relative = source_file.resolve().relative_to(source_root)
        except (OSError, ValueError):
            return
        if not source_file.is_file():
            return

        deadline = time.monotonic() + 120
        destination_file = destination_root / relative
        destination_file.parent.mkdir(parents=True, exist_ok=True)
        temporary_file = destination_file.with_name(
            f".{destination_file.name}.{uuid.uuid4().hex}.part"
        )
        try:
            while time.monotonic() < deadline:
                stable_state: tuple[int, int] | None = None
                stable_checks = 0
                while time.monotonic() < deadline:
                    try:
                        stat = source_file.stat()
                    except FileNotFoundError:
                        return
                    current_state = (stat.st_size, stat.st_mtime_ns)
                    if current_state == stable_state:
                        stable_checks += 1
                        if stable_checks >= 2:
                            break
                    else:
                        stable_state = current_state
                        stable_checks = 0
                    time.sleep(0.5)
                else:
                    break

                source_changed = False
                for attempt in range(3):
                    try:
                        shutil.copy2(source_file, temporary_file)
                        current_stat = source_file.stat()
                        if (current_stat.st_size, current_stat.st_mtime_ns) != stable_state:
                            temporary_file.unlink(missing_ok=True)
                            source_changed = True
                            break
                        actual_destination = move_to_available_path(
                            temporary_file, destination_file
                        )
                        copied_message = f"Copié : {relative}"
                        if actual_destination != destination_file:
                            copied_message = (
                                f"Copié sous un nouveau nom : {relative} -> "
                                f"{actual_destination.relative_to(destination_root)}"
                            )
                        self.notify("copied", copied_message)
                        return
                    except OSError:
                        temporary_file.unlink(missing_ok=True)
                        if attempt == 2:
                            raise
                        time.sleep(1)
                if not source_changed:
                    return
            raise OSError("le fichier est resté en cours d'écriture pendant plus de 120 secondes.")
        finally:
            temporary_file.unlink(missing_ok=True)


class TransferApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.service = TransferService(self._notify)
        self.root.title(APP_NAME)
        self.root.resizable(False, False)
        self.source_var = tk.StringVar()
        self.destination_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Transfert automatique désactivé.")
        self._load_config()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.root.after(150, self._process_events)

    def _build_ui(self) -> None:
        frame = ttk.Frame(self.root, padding=14)
        frame.grid(sticky="nsew")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Dossier source :").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(frame, textvariable=self.source_var, width=52).grid(
            row=0, column=1, sticky="ew", padx=(8, 6), pady=5
        )
        ttk.Button(frame, text="Parcourir...", command=self._choose_source).grid(
            row=0, column=2, pady=5
        )

        ttk.Label(frame, text="Dossier destination :").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(frame, textvariable=self.destination_var, width=52).grid(
            row=1, column=1, sticky="ew", padx=(8, 6), pady=5
        )
        ttk.Button(frame, text="Parcourir...", command=self._choose_destination).grid(
            row=1, column=2, pady=5
        )

        self.indicator = tk.Label(
            frame, text="●", fg="#888888", font=("Segoe UI", 13)
        )
        self.indicator.grid(row=2, column=0, sticky="w", pady=(12, 4))
        ttk.Label(frame, textvariable=self.status_var).grid(
            row=2, column=1, columnspan=2, sticky="w", pady=(12, 4)
        )

        self.toggle_button = ttk.Button(
            frame, text="Activer le transfert", command=self._toggle
        )
        self.toggle_button.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(7, 10))

        self.log = tk.Listbox(frame, width=87, height=7)
        self.log.grid(row=4, column=0, columnspan=3, sticky="ew")

    def _choose_source(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.source_var.get() or None)
        if selected:
            self.source_var.set(selected)

    def _choose_destination(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.destination_var.get() or None)
        if selected:
            self.destination_var.set(selected)

    def _toggle(self) -> None:
        if self.service.observer is not None:
            self.service.stop()
            self.indicator.config(fg="#888888")
            self.toggle_button.config(text="Activer le transfert")
            return
        if not self.source_var.get().strip() or not self.destination_var.get().strip():
            messagebox.showerror(
                "Dossiers manquants",
                "Sélectionnez un dossier source et un dossier destination.",
                parent=self.root,
            )
            return
        try:
            self._save_config()
            self.service.start(Path(self.source_var.get()), Path(self.destination_var.get()))
        except (OSError, RuntimeError, ValueError) as error:
            messagebox.showerror("Impossible d'activer le transfert", str(error), parent=self.root)
            return
        self.indicator.config(fg="#218838")
        self.toggle_button.config(text="Désactiver le transfert")

    def _notify(self, kind: str, message: str) -> None:
        self.events.put((kind, message))

    def _process_events(self) -> None:
        while True:
            try:
                kind, message = self.events.get_nowait()
            except queue.Empty:
                break
            self.status_var.set(message)
            if kind == "error":
                self.indicator.config(fg="#c82333")
            elif kind == "status" and self.service.observer is None:
                self.indicator.config(fg="#888888")
            elif self.service.observer is not None:
                self.indicator.config(fg="#218838")
            if kind in {"copied", "error"}:
                self.log.insert(0, message)
                if self.log.size() > 7:
                    self.log.delete(7, tk.END)
        self.root.after(150, self._process_events)

    def _load_config(self) -> None:
        try:
            config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if not isinstance(config, dict):
                raise ValueError("Le fichier de configuration doit contenir un objet JSON.")
            source = config.get("source", "")
            destination = config.get("destination", "")
            if not isinstance(source, str) or not isinstance(destination, str):
                raise ValueError("Les chemins enregistrés doivent être des chaînes de caractères.")
            self.source_var.set(source)
            self.destination_var.set(destination)
        except FileNotFoundError:
            pass
        except (OSError, json.JSONDecodeError, ValueError) as error:
            messagebox.showwarning(
                "Configuration non chargée",
                f"Les chemins enregistrés n'ont pas pu être lus : {error}",
                parent=self.root,
            )

    def _save_config(self) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary_config = CONFIG_PATH.with_suffix(".tmp")
        temporary_config.write_text(
            json.dumps(
                {
                    "source": self.source_var.get().strip(),
                    "destination": self.destination_var.get().strip(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        os.replace(temporary_config, CONFIG_PATH)

    def _close(self) -> None:
        self.service.stop()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    TransferApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
