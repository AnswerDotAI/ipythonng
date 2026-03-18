from __future__ import annotations

import base64
import io
import sys
from contextlib import redirect_stdout
from types import MethodType
from typing import Any

from kittytgp import build_render_bytes
from rich.console import Console
from rich.markdown import Markdown as RichMarkdown

_DEFAULT_CELL_SIZE = (8, 16)


def _register_mime_renderer(shell, mime, handler):
    active_types = shell.display_formatter.active_types
    if mime not in active_types: active_types.append(mime)
    formatter = shell.display_formatter.formatters.get(mime)
    if formatter is not None: formatter.enabled = True
    shell.mime_renderers[mime] = handler


def _is_tty(stream) -> bool:
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty())


def _is_inline_backend(backend: str | None) -> bool:
    if not backend: return False
    return backend.lower() in {"inline", "module://matplotlib_inline.backend_inline"}


class _RenderTarget:
    def __init__(self, stream): self.stream = stream

    def fileno(self) -> int:
        for candidate in (getattr(self.stream, "buffer", None), self.stream, getattr(sys.__stdout__, "buffer", None), sys.__stdout__):
            fileno = getattr(candidate, "fileno", None)
            if fileno is None: continue
            try: return fileno()
            except Exception: continue
        return 1


class IPythonNGExtension:
    def __init__(self, shell):
        self.shell = shell
        self.history_manager = shell.history_manager
        self._original_store_output = self.history_manager.store_output
        self._pending_store_output = set()
        self._registered_events = []
        self._rendered_mimes = {}
        self._handler_by_mime = {}
        self._added_active_types = set()
        self._original_enable_matplotlib = None

    def load(self):
        self._install_renderers()
        self._install_history_patch()
        self._install_matplotlib_patch()

    def unload(self):
        for event, callback in self._registered_events: self.shell.events.unregister(event, callback)
        self._registered_events.clear()

        self.history_manager.store_output = self._original_store_output
        self._pending_store_output.clear()
        if self._original_enable_matplotlib is not None: self.shell.enable_matplotlib = self._original_enable_matplotlib

        for mime, original in self._rendered_mimes.items():
            current = self.shell.mime_renderers.get(mime)
            if current is self._handler_by_mime.get(mime):
                if original is None: self.shell.mime_renderers.pop(mime, None)
                else: self.shell.mime_renderers[mime] = original

        for mime in self._added_active_types:
            if mime in self.shell.display_formatter.active_types: self.shell.display_formatter.active_types.remove(mime)

    def _install_renderers(self):
        self._add_renderer("text/markdown", self._handle_text_markdown)
        self._add_renderer("image/png", self._handle_image_png)

    def _add_renderer(self, mime: str, handler):
        self._rendered_mimes[mime] = self.shell.mime_renderers.get(mime)
        self._handler_by_mime[mime] = handler
        if mime not in self.shell.display_formatter.active_types: self._added_active_types.add(mime)
        _register_mime_renderer(self.shell, mime, handler)

    def _install_history_patch(self):
        self.history_manager.store_output = MethodType(self._deferred_store_output, self.history_manager)
        self.shell.events.register("post_run_cell", self._finalize_history)
        self._registered_events.append(("post_run_cell", self._finalize_history))

    def _install_matplotlib_patch(self):
        self._original_enable_matplotlib = self.shell.enable_matplotlib
        self.shell.enable_matplotlib = MethodType(lambda shell, gui=None: self._enable_matplotlib(shell, gui), self.shell)

    def _deferred_store_output(self, history_manager, line_num: int) -> None:
        if history_manager.db_log_output: self._pending_store_output.add(line_num)

    def _output_stream(self): return getattr(self.shell, "_ipythonng_stream", sys.__stdout__)

    def _write(self, text: str):
        stream = self._output_stream()
        stream.write(text)
        flush = getattr(stream, "flush", None)
        if flush is not None: flush()

    def _render_markdown(self, markdown_text: str):
        stream = self._output_stream()
        console = Console(file=stream, force_terminal=_is_tty(stream), highlight=False, soft_wrap=True)
        console.print(RichMarkdown(markdown_text))

    def _current_matplotlib_backend(self) -> str | None:
        try: import matplotlib
        except Exception: return None
        try: return matplotlib.get_backend()
        except Exception: return None

    def _close_matplotlib_figures(self):
        try: from matplotlib import pyplot as plt
        except Exception: return
        try: plt.close("all")
        except Exception: return

    def _ensure_inline_figure_formats(self, shell):
        try:
            from IPython.core.pylabtools import select_figure_formats
            from matplotlib.figure import Figure
            from matplotlib_inline.config import InlineBackend
        except Exception: return
        png_formatter = shell.display_formatter.formatters["image/png"]
        if Figure in png_formatter.type_printers: return
        cfg = InlineBackend.instance(parent=shell)
        select_figure_formats(shell, cfg.figure_formats, **cfg.print_figure_kwargs)

    def _enable_matplotlib(self, shell, gui=None):
        previous_backend = self._current_matplotlib_backend()
        stdout = io.StringIO()
        with redirect_stdout(stdout): result = self._original_enable_matplotlib(gui)
        gui_name, backend = result
        output = stdout.getvalue()
        if _is_inline_backend(backend):
            self._ensure_inline_figure_formats(shell)
            output = "".join(line for line in output.splitlines(keepends=True) if line.strip() != "No event loop hook running.")
            if not _is_inline_backend(previous_backend): self._close_matplotlib_figures()
        if output: sys.stdout.write(output)
        return gui_name, backend

    def _needs_execute_result_newline(self) -> bool:
        displayhook = getattr(self.shell, "displayhook", None)
        return bool(displayhook and displayhook.is_active and not displayhook.prompt_end_newline)

    def _render_png(self, png_b64: str, metadata: dict[str, Any] | None):
        stream = self._output_stream()
        if not _is_tty(stream):
            self._write("[image/png]\n")
            return

        target = _RenderTarget(stream)
        try:
            png_bytes = base64.b64decode(png_b64)
            payload = build_render_bytes(png_bytes, out=target)
        except RuntimeError:
            try:
                payload = build_render_bytes(png_bytes, out=target, cell_width_px=_DEFAULT_CELL_SIZE[0], cell_height_px=_DEFAULT_CELL_SIZE[1])
            except Exception:
                self._write("[image/png]\n")
                return
        except Exception:
            self._write("[image/png]\n")
            return

        if self._needs_execute_result_newline(): self._write("\n")
        self._write(payload.decode("utf-8"))

    def _handle_text_markdown(self, markdown_text: str, metadata=None): self._render_markdown(markdown_text)

    def _handle_image_png(self, png_b64: str, metadata=None): self._render_png(png_b64, metadata)

    def _render_history_output(self, output) -> str:
        if output.output_type in {"out_stream", "err_stream"}: return "".join(output.bundle.get("stream", []))

        bundle = output.bundle
        if "text/markdown" in bundle: return bundle["text/markdown"]
        if "image/png" in bundle: return "[image/png]"
        if "text/plain" in bundle: return bundle["text/plain"]
        return ""

    def _flatten_output(self, execution_count: int) -> str | None:
        pieces = []
        for output in self.history_manager.outputs.get(execution_count, []):
            text = self._render_history_output(output)
            if not text: continue
            if pieces and not pieces[-1].endswith("\n") and not text.startswith("\n"): pieces.append("\n")
            pieces.append(text)

        exception = self.history_manager.exceptions.get(execution_count)
        if exception:
            traceback_text = "".join(exception.get("traceback", []))
            if traceback_text:
                if pieces and not pieces[-1].endswith("\n") and not traceback_text.startswith("\n"): pieces.append("\n")
                pieces.append(traceback_text)

        if not pieces: return None
        return "".join(pieces)

    def _finalize_history(self, result):
        execution_count = getattr(result, "execution_count", None)
        if execution_count is None: return

        flat_output = self._flatten_output(execution_count)
        if flat_output is None: self.history_manager.output_hist_reprs.pop(execution_count, None)
        else: self.history_manager.output_hist_reprs[execution_count] = flat_output

        should_store = self.history_manager.db_log_output and flat_output is not None and (
            execution_count in self._pending_store_output or execution_count in self.history_manager.exceptions)
        self._pending_store_output.discard(execution_count)
        if should_store: self._original_store_output(execution_count)


def load_ipython_extension(shell):
    if getattr(shell, "_ipythonng_extension", None) is not None: return
    extension = IPythonNGExtension(shell)
    extension.load()
    shell._ipythonng_extension = extension


def unload_ipython_extension(shell):
    extension = getattr(shell, "_ipythonng_extension", None)
    if extension is None: return
    extension.unload()
    del shell._ipythonng_extension
