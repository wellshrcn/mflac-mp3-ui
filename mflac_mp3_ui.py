import json
import os
import shutil
import subprocess
import sys
import threading
import tempfile
import importlib
import urllib.request
import zipfile
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    import windnd  # type: ignore
except Exception:
    windnd = None


class MflacMp3App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("MFLAC -> MP3 一键转换")
        self.root.geometry("900x620")
        self.frozen = bool(getattr(sys, "frozen", False))
        self.runtime_dir = Path.home() / ".mflac_mp3_ui"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.runtime_dir / "ui_config.json"
        self._config = self.load_config()

        self.worker_thread = None
        self.drop_hooked = False
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        row1 = ttk.Frame(container)
        row1.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(row1, text="源目录（包含 .mflac）:").pack(side=tk.LEFT)
        self.src_var = tk.StringVar(value=self._config.get("src_dir", ""))
        ttk.Entry(row1, textvariable=self.src_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        ttk.Button(row1, text="选择目录", command=self.pick_source_dir).pack(side=tk.LEFT)

        row2 = ttk.Frame(container)
        row2.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(row2, text="输出目录（MP3）:").pack(side=tk.LEFT)
        self.out_var = tk.StringVar(value=self._config.get("out_dir", ""))
        ttk.Entry(row2, textvariable=self.out_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        ttk.Button(row2, text="选择目录", command=self.pick_output_dir).pack(side=tk.LEFT)

        row3 = ttk.Frame(container)
        row3.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(row3, text="中间解密目录（FLAC）:").pack(side=tk.LEFT)
        self.dec_var = tk.StringVar(value=self._config.get("dec_dir", ""))
        ttk.Entry(row3, textvariable=self.dec_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        ttk.Button(row3, text="选择目录", command=self.pick_decoded_dir).pack(side=tk.LEFT)

        drop_row = ttk.LabelFrame(container, text="单文件拖拽自动转换（拖入 .mflac -> 自动输出到桌面）", padding=8)
        drop_row.pack(fill=tk.X, pady=(0, 8))
        self.drop_hint_var = tk.StringVar(value="把单个 .mflac 文件拖到这里")
        self.drop_label = ttk.Label(drop_row, textvariable=self.drop_hint_var)
        self.drop_label.pack(fill=tk.X)
        self.enable_dragdrop()

        row4 = ttk.Frame(container)
        row4.pack(fill=tk.X, pady=(0, 10))
        self.cleanup_var = tk.BooleanVar(value=self._config.get("cleanup", False))
        self.skip_existing_var = tk.BooleanVar(value=self._config.get("skip_existing", True))
        ttk.Checkbutton(row4, text="完成后删除中间 FLAC", variable=self.cleanup_var).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Checkbutton(row4, text="跳过已存在的 MP3", variable=self.skip_existing_var).pack(side=tk.LEFT)

        tool_row = ttk.Frame(container)
        tool_row.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(tool_row, text="qmdec:").pack(side=tk.LEFT)
        self.qmdec_path_var = tk.StringVar(value=self._config.get("qmdec_path") or self.find_qmdec() or "")
        ttk.Entry(tool_row, textvariable=self.qmdec_path_var, width=36).pack(side=tk.LEFT, padx=(6, 8))
        ttk.Label(tool_row, text="qmc-decoder:").pack(side=tk.LEFT)
        self.qmc_decoder_path_var = tk.StringVar(value=self._config.get("qmc_decoder_path") or self.find_qmc_decoder() or "")
        ttk.Entry(tool_row, textvariable=self.qmc_decoder_path_var, width=36).pack(side=tk.LEFT, padx=(6, 8))
        ttk.Label(tool_row, text="ffmpeg:").pack(side=tk.LEFT)
        self.ffmpeg_path_var = tk.StringVar(value=self._config.get("ffmpeg_path") or self.find_ffmpeg() or "")
        ttk.Entry(tool_row, textvariable=self.ffmpeg_path_var, width=36).pack(side=tk.LEFT, padx=(6, 0))

        btn_row = ttk.Frame(container)
        btn_row.pack(fill=tk.X, pady=(0, 10))
        self.start_btn = ttk.Button(btn_row, text="开始转换", command=self.start_pipeline)
        self.start_btn.pack(side=tk.LEFT)
        ttk.Button(btn_row, text="清空日志", command=self.clear_log).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_row, text="自动安装依赖", command=self.install_tools_async).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="仅测试工具路径", command=self.test_tools).pack(side=tk.LEFT)

        self.progress_var = tk.IntVar(value=0)
        self.progress = ttk.Progressbar(container, mode="determinate", variable=self.progress_var)
        self.progress.pack(fill=tk.X, pady=(0, 10))

        log_frame = ttk.Frame(container)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(log_frame, wrap="word")
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=scroll.set)

    def default_paths(self) -> dict:
        home = Path.home()
        desktop = home / "Desktop"
        music = home / "Music"
        src_candidates = [
            music / "VipSongsDownload",
            music / "QQ音乐",
            home / "Documents" / "Tencent Files" / "QQMusic",
            music,
            desktop,
            home / "Downloads",
        ]
        src_dir = next((p for p in src_candidates if p.exists()), desktop)
        return {
            "src_dir": str(src_dir),
            "out_dir": str(desktop),
            "dec_dir": str(self.runtime_dir / "decoded"),
            "cleanup": False,
            "skip_existing": True,
            "qmdec_path": "",
            "qmc_decoder_path": "",
            "ffmpeg_path": "",
        }

    def load_config(self) -> dict:
        defaults = self.default_paths()
        if not self.config_path.exists():
            return defaults
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return defaults
        except (OSError, json.JSONDecodeError):
            return defaults
        merged = {**defaults, **data}
        for key in ("src_dir", "out_dir", "dec_dir"):
            if not merged.get(key):
                merged[key] = defaults[key]
        return merged

    def save_config(self) -> None:
        data = {
            "src_dir": self.src_var.get().strip(),
            "out_dir": self.out_var.get().strip(),
            "dec_dir": self.dec_var.get().strip(),
            "cleanup": bool(self.cleanup_var.get()),
            "skip_existing": bool(self.skip_existing_var.get()),
            "qmdec_path": self.qmdec_path_var.get().strip(),
            "qmc_decoder_path": self.qmc_decoder_path_var.get().strip(),
            "ffmpeg_path": self.ffmpeg_path_var.get().strip(),
        }
        try:
            self.config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self._config = data
        except OSError as exc:
            self.log(f"保存配置失败: {exc}")

    def on_close(self) -> None:
        self.save_config()
        self.root.destroy()

    def pick_source_dir(self) -> None:
        selected = filedialog.askdirectory(
            title="选择包含 mflac 的目录",
            initialdir=self.src_var.get().strip() or str(Path.home()),
        )
        if selected:
            self.src_var.set(selected)
            self.save_config()

    def pick_output_dir(self) -> None:
        selected = filedialog.askdirectory(
            title="选择 MP3 输出目录",
            initialdir=self.out_var.get().strip() or str(Path.home() / "Desktop"),
        )
        if selected:
            self.out_var.set(selected)
            self.save_config()

    def pick_decoded_dir(self) -> None:
        selected = filedialog.askdirectory(
            title="选择中间 FLAC 输出目录",
            initialdir=self.dec_var.get().strip() or str(self.runtime_dir),
        )
        if selected:
            self.dec_var.set(selected)
            self.save_config()

    def clear_log(self) -> None:
        self.log_text.delete("1.0", tk.END)

    def log(self, msg: str) -> None:
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def set_running(self, running: bool) -> None:
        state = tk.DISABLED if running else tk.NORMAL
        self.start_btn.configure(state=state)

    def is_windows_python_stub(self, path: str) -> bool:
        normalized = str(Path(path)).replace("/", "\\").lower()
        return "\\windowsapps\\" in normalized

    def verify_python(self, path: str) -> bool:
        if not path or not Path(path).exists():
            return False
        if self.is_windows_python_stub(path):
            return False
        try:
            result = subprocess.run(
                [path, "-c", "import sys; print(sys.version_info[0])"],
                capture_output=True,
                text=True,
                timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return result.returncode == 0 and result.stdout.strip().isdigit()
        except (OSError, subprocess.TimeoutExpired):
            return False

    def find_python(self) -> str | None:
        candidates: list[str] = []
        py_root = Path.home() / "AppData/Local/Programs/Python"
        if py_root.exists():
            for py_exe in sorted(py_root.glob("Python*/python.exe"), reverse=True):
                candidates.append(str(py_exe))
        env_py = os.environ.get("PYTHON_PATH", "").strip()
        if env_py:
            candidates.append(env_py)
        for name in ("python", "python3"):
            found = shutil.which(name)
            if found:
                candidates.append(found)
        if not self.frozen:
            candidates.insert(0, sys.executable)
        seen: set[str] = set()
        for c in candidates:
            key = str(Path(c).resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            if self.verify_python(c):
                return c
        return None

    def find_qmdec(self) -> str | None:
        py_scripts_qmdec = str((Path(sys.executable).parent / "Scripts" / "qmdec.exe").resolve())
        candidates = [
            os.environ.get("QMDEC_PATH", ""),
            shutil.which("qmdec") or "",
            py_scripts_qmdec,
            str(self.runtime_dir / "tools" / "qmdec.exe"),
        ]
        py_root = Path.home() / "AppData/Local/Programs/Python"
        if py_root.exists():
            for qmdec_exe in sorted(py_root.glob("Python*/Scripts/qmdec.exe"), reverse=True):
                candidates.append(str(qmdec_exe))
        for c in candidates:
            if c and Path(c).exists():
                return c
        return None

    def find_qmc_decoder(self) -> str | None:
        candidates = [
            os.environ.get("QMC_DECODER_PATH", ""),
            shutil.which("qmc-decoder") or "",
            str(self.runtime_dir / "tools" / "qmc-decoder" / "qmc-decoder.exe"),
            r"D:\f4\tools\qmc-decoder\qmc-decoder.exe",
        ]
        for c in candidates:
            if c and Path(c).exists():
                return c
        return None

    def find_ffmpeg(self) -> str | None:
        candidates = [
            os.environ.get("FFMPEG_PATH", ""),
            shutil.which("ffmpeg") or "",
            str(Path.home() / "AppData/Local/Microsoft/WinGet/Links/ffmpeg.exe"),
            str(self.runtime_dir / "tools" / "ffmpeg.exe"),
        ]
        winget_dir = Path.home() / "AppData/Local/Microsoft/WinGet/Packages"
        if winget_dir.exists():
            for exe in winget_dir.glob("Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/**/bin/ffmpeg.exe"):
                candidates.append(str(exe))
        for c in candidates:
            if c and Path(c).exists():
                return c
        return None

    def test_tools(self) -> None:
        qmdec = self.qmdec_path_var.get().strip()
        qmc_decoder = self.qmc_decoder_path_var.get().strip()
        ffmpeg = self.ffmpeg_path_var.get().strip()
        ok = True

        if (not qmdec or not Path(qmdec).exists()) and (not qmc_decoder or not Path(qmc_decoder).exists()):
            self.log("qmdec 与 qmc-decoder 都不可用，至少需要一个解密工具。")
            ok = False
        else:
            if qmdec and Path(qmdec).exists():
                code = subprocess.run([qmdec, "--help"], capture_output=True, text=True).returncode
                self.log("qmdec 可用。" if code == 0 else "qmdec 运行失败。")
                ok = ok and code == 0
            if qmc_decoder and Path(qmc_decoder).exists():
                code = subprocess.run([qmc_decoder, "--version"], capture_output=True, text=True).returncode
                self.log("qmc-decoder 可用。" if code == 0 else "qmc-decoder 运行失败。")
                ok = ok and code == 0

        if not ffmpeg or not Path(ffmpeg).exists():
            self.log("ffmpeg 路径无效，请修正。")
            ok = False
        else:
            code = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True).returncode
            self.log("ffmpeg 可用。" if code == 0 else "ffmpeg 运行失败。")
            ok = ok and code == 0

        if ok:
            messagebox.showinfo("检查完成", "工具路径正常。")
        else:
            messagebox.showwarning("检查失败", "请先修正工具路径。")

    def start_pipeline(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("提示", "任务正在运行中。")
            return
        self.save_config()
        self.worker_thread = threading.Thread(target=self.run_pipeline, daemon=True)
        self.worker_thread.start()

    def start_single_file_pipeline(self, file_path: Path) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("提示", "任务正在运行中。")
            return
        self.worker_thread = threading.Thread(target=self.run_single_file_pipeline, args=(file_path,), daemon=True)
        self.worker_thread.start()

    def install_tools_async(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("提示", "任务正在运行中。")
            return
        self.worker_thread = threading.Thread(target=self.install_tools_flow, daemon=True)
        self.worker_thread.start()

    def run_pipeline(self) -> None:
        self.set_running(True)
        try:
            src_dir = Path(self.src_var.get().strip())
            out_dir = Path(self.out_var.get().strip())
            dec_dir = Path(self.dec_var.get().strip())

            if not src_dir.exists():
                raise RuntimeError(f"源目录不存在: {src_dir}")

            qmdec, qmc_decoder, ffmpeg = self.ensure_tools_installed()

            out_dir.mkdir(parents=True, exist_ok=True)
            dec_dir.mkdir(parents=True, exist_ok=True)

            mflac_files = list(src_dir.rglob("*.mflac"))
            if not mflac_files:
                raise RuntimeError("未找到 .mflac 文件。")

            self.log(f"找到 {len(mflac_files)} 个 mflac 文件。")
            self.log("步骤 1/3: 解密 mflac -> flac...")
            self.decrypt_batch(mflac_files, src_dir, dec_dir, qmdec, qmc_decoder)

            flac_files = list(dec_dir.rglob("*.flac"))
            if not flac_files:
                raise RuntimeError("解密后没有找到 FLAC 文件。")

            self.log(f"步骤 2/3: 转码 flac -> mp3（共 {len(flac_files)} 个）...")
            self.progress.configure(maximum=len(flac_files))
            self.progress_var.set(0)

            converted = 0
            skipped = 0
            for idx, flac_path in enumerate(flac_files, start=1):
                rel = flac_path.relative_to(dec_dir)
                mp3_path = (out_dir / rel).with_suffix(".mp3")
                mp3_path.parent.mkdir(parents=True, exist_ok=True)

                if self.skip_existing_var.get() and mp3_path.exists():
                    skipped += 1
                    self.log(f"[{idx}/{len(flac_files)}] 跳过已存在: {mp3_path.name}")
                    self.progress_var.set(idx)
                    continue

                cmd = [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(flac_path),
                    "-vn",
                    "-codec:a",
                    "libmp3lame",
                    "-q:a",
                    "2",
                    "-map_metadata",
                    "0",
                    "-id3v2_version",
                    "3",
                    str(mp3_path),
                ]
                self.run_command(cmd, cwd=src_dir, quiet=True)
                converted += 1
                self.log(f"[{idx}/{len(flac_files)}] 已生成: {mp3_path.name}")
                self.progress_var.set(idx)

            if self.cleanup_var.get():
                for flac_path in flac_files:
                    try:
                        flac_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                self.log("已清理中间 FLAC 文件。")

            self.log(f"完成：转换 {converted} 个，跳过 {skipped} 个。")
            messagebox.showinfo("完成", f"处理完成。\n转换: {converted}\n跳过: {skipped}\n输出目录: {out_dir}")
        except Exception as exc:
            self.log(f"错误: {exc}")
            messagebox.showerror("失败", str(exc))
        finally:
            self.set_running(False)

    def run_single_file_pipeline(self, mflac_path: Path) -> None:
        self.set_running(True)
        try:
            if not mflac_path.exists() or mflac_path.suffix.lower() != ".mflac":
                raise RuntimeError(f"无效的 mflac 文件: {mflac_path}")

            qmdec, qmc_decoder, ffmpeg = self.ensure_tools_installed()
            desktop_dir = Path.home() / "Desktop"
            desktop_dir.mkdir(parents=True, exist_ok=True)

            single_dec_dir = Path(tempfile.gettempdir()) / "mflac_mp3_ui_single_decoded"
            single_dec_dir.mkdir(parents=True, exist_ok=True)

            self.progress.configure(maximum=1)
            self.progress_var.set(0)

            self.log(f"单文件模式: {mflac_path}")
            self.log("步骤 1/3: 解密 mflac -> flac...")
            flac_file = self.decrypt_single(mflac_path, single_dec_dir, qmdec, qmc_decoder)

            mp3_out = desktop_dir / f"{mflac_path.stem}.mp3"
            self.log("步骤 2/3: 转码 flac -> mp3 到桌面...")
            cmd = [
                ffmpeg,
                "-y",
                "-i",
                str(flac_file),
                "-vn",
                "-codec:a",
                "libmp3lame",
                "-q:a",
                "2",
                "-map_metadata",
                "0",
                "-id3v2_version",
                "3",
                str(mp3_out),
            ]
            self.run_command(cmd, cwd=mflac_path.parent, quiet=True)
            self.progress_var.set(1)

            self.log(f"单文件转换完成: {mp3_out}")
            messagebox.showinfo("完成", f"已转换到桌面:\n{mp3_out}")
        except Exception as exc:
            self.log(f"错误: {exc}")
            messagebox.showerror("失败", str(exc))
        finally:
            self.set_running(False)

    def install_tools_flow(self) -> None:
        self.set_running(True)
        try:
            qmdec, qmc_decoder, ffmpeg = self.ensure_tools_installed()
            self.ensure_dragdrop_runtime()
            py = self.find_python()
            if py:
                self.log(f"python: {py}")
            self.log(f"qmdec: {qmdec}")
            self.log(f"qmc-decoder: {qmc_decoder}")
            self.log(f"ffmpeg: {ffmpeg}")
            self.enable_dragdrop()
            messagebox.showinfo("完成", "依赖安装/检测完成。")
        except Exception as exc:
            self.log(f"错误: {exc}")
            messagebox.showerror("失败", str(exc))
        finally:
            self.set_running(False)

    def ensure_tools_installed(self) -> tuple[str, str, str]:
        qmdec = self.qmdec_path_var.get().strip()
        qmc_decoder = self.qmc_decoder_path_var.get().strip()
        ffmpeg = self.ffmpeg_path_var.get().strip()

        if not qmdec or not Path(qmdec).exists():
            self.log("未找到 qmdec，开始自动安装...")
            if not self.find_python():
                self.log("本机无可用 Python（已忽略 Windows 商店占位符），先通过 winget 安装...")
                self.install_python()
            self.install_qmdec()
            qmdec = self.find_qmdec() or ""

        if not qmc_decoder or not Path(qmc_decoder).exists():
            self.log("未找到 qmc-decoder，开始自动下载（备用解密器）...")
            self.install_qmc_decoder()
            qmc_decoder = self.find_qmc_decoder() or ""

        if not qmdec and not qmc_decoder:
            raise RuntimeError("未找到可用解密器（qmdec 或 qmc-decoder）。")

        if not ffmpeg or not Path(ffmpeg).exists():
            self.log("未找到 ffmpeg，开始自动安装...")
            self.install_ffmpeg()
            ffmpeg = self.find_ffmpeg() or ""

        if qmdec and not Path(qmdec).exists():
            qmdec = ""
        if qmc_decoder and not Path(qmc_decoder).exists():
            qmc_decoder = ""

        if not qmdec and not qmc_decoder:
            raise RuntimeError("自动安装后仍未找到解密器（qmdec 或 qmc-decoder）。")
        if not ffmpeg or not Path(ffmpeg).exists():
            raise RuntimeError("自动安装后仍未找到 ffmpeg，请确认 winget 可用并重试。")

        self.qmdec_path_var.set(qmdec)
        self.qmc_decoder_path_var.set(qmc_decoder)
        self.ffmpeg_path_var.set(ffmpeg)
        self.save_config()
        return qmdec, qmc_decoder, ffmpeg

    def get_python_for_pip(self) -> str:
        if not self.frozen:
            return sys.executable
        py = self.find_python()
        if not py:
            py = self.install_python()
        if not self.verify_python(py):
            raise RuntimeError(f"Python 不可用: {py}")
        return py

    def install_python(self) -> str:
        winget = shutil.which("winget")
        if not winget:
            raise RuntimeError("未检测到 winget，无法自动安装 Python。")
        self.log("正在通过 winget 安装 Python 3.11（请稍候）...")
        cmd = [
            winget,
            "install",
            "--id",
            "Python.Python.3.11",
            "-e",
            "--accept-source-agreements",
            "--accept-package-agreements",
        ]
        self.run_command(cmd, cwd=Path.cwd())
        py = self.find_python()
        if not py:
            raise RuntimeError(
                "Python 安装完成但未检测到可执行文件。\n"
                "请关闭本软件后重新打开，再点“自动安装依赖”。"
            )
        self.log(f"Python 已就绪: {py}")
        return py

    def install_git(self) -> bool:
        if shutil.which("git"):
            return True
        winget = shutil.which("winget")
        if not winget:
            return False
        self.log("正在通过 winget 安装 Git（备用方案）...")
        try:
            self.run_command(
                [
                    winget,
                    "install",
                    "--id",
                    "Git.Git",
                    "-e",
                    "--accept-source-agreements",
                    "--accept-package-agreements",
                ],
                cwd=Path.cwd(),
            )
        except Exception as exc:
            self.log(f"Git 安装失败: {exc}")
            return False
        git_paths = [
            shutil.which("git") or "",
            r"C:\Program Files\Git\cmd\git.exe",
            r"C:\Program Files\Git\bin\git.exe",
        ]
        return any(p and Path(p).exists() for p in git_paths)

    def install_qmdec(self) -> None:
        python_exe = self.get_python_for_pip()
        self.log(f"使用 Python 安装 qmdec: {python_exe}")
        pip_base = [python_exe, "-m", "pip", "install", "--upgrade", "--no-warn-script-location"]
        qmdec_zip_url = "https://github.com/Sophomoresty/qmdec/archive/refs/heads/main.zip"
        last_error: Exception | None = None

        try:
            self.run_command([python_exe, "-m", "pip", "install", "--upgrade", "pip"], cwd=Path.cwd(), quiet=True)
        except Exception:
            pass

        # 方案 1：pip 直接从 GitHub zip 安装（不需要 git）
        try:
            self.log("从 GitHub 压缩包安装 qmdec（无需 git）...")
            self.run_command([*pip_base, qmdec_zip_url], cwd=Path.cwd())
            if self.find_qmdec():
                self.log(f"qmdec 安装成功: {self.find_qmdec()}")
                return
        except Exception as exc:
            last_error = exc
            self.log(f"zip 直装失败，尝试本地下载: {exc}")

        # 方案 2：手动下载 zip 后本地 pip install
        try:
            tools_dir = self.runtime_dir / "tools"
            tools_dir.mkdir(parents=True, exist_ok=True)
            zip_path = tools_dir / "qmdec-main.zip"
            extract_root = tools_dir / "qmdec-src"
            self.log(f"下载 qmdec 源码包...")
            urllib.request.urlretrieve(qmdec_zip_url, zip_path)
            if extract_root.exists():
                shutil.rmtree(extract_root, ignore_errors=True)
            extract_root.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_root)
            src_dirs = list(extract_root.glob("qmdec-*"))
            if not src_dirs:
                raise RuntimeError("解压后未找到 qmdec 源码目录")
            self.log(f"本地安装 qmdec: {src_dirs[0]}")
            self.run_command([*pip_base, str(src_dirs[0])], cwd=Path.cwd())
            if self.find_qmdec():
                self.log(f"qmdec 安装成功: {self.find_qmdec()}")
                return
        except Exception as exc:
            last_error = exc
            self.log(f"本地下载安装失败: {exc}")

        # 方案 3：安装 Git 后再用 git+ 地址
        if self.install_git():
            try:
                self.log("使用 git 方式安装 qmdec...")
                self.run_command(
                    [*pip_base, "git+https://github.com/Sophomoresty/qmdec.git"],
                    cwd=Path.cwd(),
                )
                if self.find_qmdec():
                    self.log(f"qmdec 安装成功: {self.find_qmdec()}")
                    return
            except Exception as exc:
                last_error = exc

        raise RuntimeError(f"qmdec 安装失败: {last_error}")

    def install_ffmpeg(self) -> None:
        winget = shutil.which("winget")
        if not winget:
            raise RuntimeError("未检测到 winget，无法自动安装 ffmpeg。")
        cmd = [
            winget,
            "install",
            "--id",
            "Gyan.FFmpeg",
            "-e",
            "--accept-source-agreements",
            "--accept-package-agreements",
        ]
        self.run_command(cmd, cwd=Path.cwd())

    def install_qmc_decoder(self) -> None:
        tools_dir = self.runtime_dir / "tools"
        target_dir = tools_dir / "qmc-decoder"
        tools_dir.mkdir(parents=True, exist_ok=True)
        zip_path = tools_dir / "qmc-decoder-windows-x86_64.zip"
        url = "https://github.com/ownlight6/qmc-decoder/releases/download/v1.2.0/qmc-decoder-windows-x86_64.zip"
        self.log(f"下载 qmc-decoder: {url}")
        urllib.request.urlretrieve(url, zip_path)
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(target_dir)
        self.log(f"qmc-decoder 已解压到: {target_dir}")

    def decrypt_single(self, mflac_path: Path, out_dir: Path, qmdec: str, qmc_decoder: str) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        target_flac = out_dir / f"{mflac_path.stem}.flac"

        if qmdec and Path(qmdec).exists():
            try:
                self.log("优先使用 qmdec 解密...")
                self.run_command([qmdec, "auth"], cwd=mflac_path.parent, quiet=True)
                self.run_command([qmdec, "decrypt", str(mflac_path), "-o", str(out_dir)], cwd=mflac_path.parent)
                if target_flac.exists():
                    return target_flac
            except Exception as exc:
                self.log(f"qmdec 解密失败，切换 qmc-decoder: {exc}")

        if qmc_decoder and Path(qmc_decoder).exists():
            self.log("使用 qmc-decoder 解密...")
            self.run_command([qmc_decoder, "--fetch-ekey", str(mflac_path), str(target_flac)], cwd=mflac_path.parent)
            if target_flac.exists():
                return target_flac

        raise RuntimeError(f"解密失败: {mflac_path.name}")

    def decrypt_batch(self, mflac_files: list[Path], src_dir: Path, dec_dir: Path, qmdec: str, qmc_decoder: str) -> None:
        dec_dir.mkdir(parents=True, exist_ok=True)
        used_qmdec = False

        if qmdec and Path(qmdec).exists():
            try:
                self.log("优先使用 qmdec 批量解密...")
                self.run_command([qmdec, "auth"], cwd=src_dir, quiet=True)
                self.run_command([qmdec, "decrypt", str(src_dir), "-o", str(dec_dir)], cwd=src_dir)
                if list(dec_dir.rglob("*.flac")):
                    used_qmdec = True
            except Exception as exc:
                self.log(f"qmdec 批量解密失败，将回退 qmc-decoder: {exc}")

        if used_qmdec:
            return

        if not qmc_decoder or not Path(qmc_decoder).exists():
            raise RuntimeError("没有可用的 qmc-decoder，且 qmdec 批量解密失败。")

        self.log("使用 qmc-decoder 逐个解密...")
        for idx, mflac in enumerate(mflac_files, start=1):
            rel = mflac.relative_to(src_dir)
            out_flac = (dec_dir / rel).with_suffix(".flac")
            out_flac.parent.mkdir(parents=True, exist_ok=True)
            self.log(f"[{idx}/{len(mflac_files)}] 解密: {mflac.name}")
            self.run_command([qmc_decoder, "--fetch-ekey", str(mflac), str(out_flac)], cwd=src_dir, quiet=True)

    def ensure_dragdrop_runtime(self) -> None:
        global windnd
        if windnd is not None:
            return
        if self.frozen:
            self.log("拖拽库未打包进 exe，拖拽功能不可用（不影响目录批量转换）。")
            return
        self.log("未检测到 windnd，开始自动安装（用于文件拖拽）...")
        python_exe = self.get_python_for_pip()
        self.run_command([python_exe, "-m", "pip", "install", "--upgrade", "windnd"], cwd=Path.cwd())
        windnd = importlib.import_module("windnd")

    def enable_dragdrop(self) -> None:
        global windnd
        if self.drop_hooked:
            return
        if windnd is None:
            self.drop_hint_var.set("拖拽功能未就绪：请点“自动安装依赖”启用")
            return
        windnd.hook_dropfiles(self.drop_label, func=self.on_drop_files)
        self.drop_hooked = True
        self.drop_hint_var.set("拖入单个 .mflac 后将自动转换到桌面")

    def decode_drop_item(self, item: bytes | str) -> str:
        if isinstance(item, str):
            return item
        for enc in ("utf-8", "mbcs", "gbk"):
            try:
                return item.decode(enc)
            except UnicodeDecodeError:
                continue
        return item.decode("utf-8", errors="ignore")

    def on_drop_files(self, files: list[bytes]) -> None:
        paths = [Path(self.decode_drop_item(x)) for x in files]
        mflac_files = [p for p in paths if p.is_file() and p.suffix.lower() == ".mflac"]
        if not mflac_files:
            self.log("拖拽失败：未检测到 .mflac 文件。")
            return
        if len(mflac_files) > 1:
            self.log("检测到多个文件，单文件拖拽模式仅处理第一个。批量请使用目录模式。")
        target = mflac_files[0]
        self.log(f"收到拖拽文件: {target}")
        self.start_single_file_pipeline(target)

    def run_command(self, cmd: list[str], cwd: Path, quiet: bool = False) -> None:
        self.log(" ".join(f'"{x}"' if " " in x else x for x in cmd))
        process = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        output_lines = []
        assert process.stdout is not None
        for line in process.stdout:
            line = line.rstrip("\n")
            output_lines.append(line)
            if not quiet:
                self.log(line)
        code = process.wait()
        if code != 0:
            tail = "\n".join(output_lines[-10:])
            raise RuntimeError(f"命令失败(退出码 {code})\n{tail}")

        # qmdec 通常会在最后输出 JSON，做一次校验提示
        if "qmdec" in Path(cmd[0]).name.lower() and output_lines:
            for raw in reversed(output_lines):
                raw = raw.strip()
                if raw.startswith("{") and raw.endswith("}"):
                    try:
                        data = json.loads(raw)
                        if isinstance(data, dict) and data.get("ok") is False:
                            raise RuntimeError(f"qmdec 返回失败: {raw}")
                    except json.JSONDecodeError:
                        pass
                    break


def main() -> None:
    root = tk.Tk()
    style = ttk.Style(root)
    try:
        style.theme_use("vista")
    except tk.TclError:
        pass
    app = MflacMp3App(root)
    app.log("提示：首次运行前请确认 QQ 音乐已登录，且本软件与 QQ 音乐都以管理员模式运行。")
    app.log("提示：exe 首次使用请先点“自动安装依赖”（会自动安装 Python + qmdec + ffmpeg）。")
    root.mainloop()


if __name__ == "__main__":
    main()
