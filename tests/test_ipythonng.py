from __future__ import annotations

import base64
import io

import kittytgp.core as kittycore
import pytest
from IPython.terminal.interactiveshell import TerminalInteractiveShell
from kittytgp import build_render_bytes
from kittytgp.core import PLACEHOLDER
from traitlets.config import Config

from ipythonng import load_ipython_extension

PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAIAAAADCAQAAABi6S9dAAAADElEQVR42mNkYPhfDwADhgGAff/3fwAAAABJRU5ErkJggg=="
PNG_BYTES = base64.b64decode(PNG_B64)


class FakeTerminal(io.StringIO):
    def isatty(self): return True


class GeometryProbe:
    def fileno(self): return 1


@pytest.fixture
def shell(tmp_path):
    TerminalInteractiveShell.clear_instance()
    config = Config()
    config.TerminalInteractiveShell.simple_prompt = True
    config.HistoryManager.hist_file = str(tmp_path / "history.sqlite")
    shell = TerminalInteractiveShell.instance(config=config)
    shell.execution_count = 1
    shell.history_manager.outputs.clear()
    shell.history_manager.output_hist_reprs.clear()
    shell.history_manager.exceptions.clear()
    shell._ipythonng_stream = FakeTerminal()
    load_ipython_extension(shell)
    try: yield shell
    finally:
        shell.history_manager.writeout_cache()
        shell.history_manager.end_session()
        shell._atexit_once = lambda: None
        TerminalInteractiveShell.clear_instance()


def test_history_flattens_streams_markdown_images_and_results(shell):
    shell.run_cell(
        """
from IPython.display import Markdown, Image, display
import base64
print("alpha")
display(Markdown("# Heading"))
display(Image(data=base64.b64decode(%r), format="png"))
print("omega")
42
"""
        % PNG_B64,
        store_history=True,
    )

    (_, _, (_, output)) = list(shell.history_manager.get_range(output=True))[-1]
    assert output == "alpha\n# Heading\n[image/png]\nomega\n42"


def test_output_history_persists_flattened_output_across_sessions(shell):
    shell.history_manager.db_log_output = True
    result = shell.run_cell(
        """
from IPython.display import Markdown, display
print("alpha")
display(Markdown("## Saved"))
""",
        store_history=True,
    )

    shell.history_manager.writeout_cache()
    shell.history_manager.reset()

    execution_count = result.execution_count
    entries = list(shell.history_manager.get_range(-1, execution_count, execution_count + 1, output=True))
    assert entries[0][2][1] == "alpha\n## Saved"


def test_tracebacks_are_included_in_flattened_output(shell):
    shell.history_manager.db_log_output = True
    shell.run_cell("1/0", store_history=True)

    (_, _, (_, output)) = list(shell.history_manager.get_range(output=True))[-1]
    assert "ZeroDivisionError" in output
    assert "division by zero" in output


def test_kitty_rendering_matches_kittytgp_outside_tmux(shell, monkeypatch):
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setattr(kittycore.secrets, "randbelow", lambda _: 0x123456 - 1)

    shell.run_cell(
        """
from IPython.display import Image, display
import base64
display(Image(data=base64.b64decode(%r), format="png"))
"""
        % PNG_B64,
        store_history=True,
    )

    rendered = shell._ipythonng_stream.getvalue()
    expected = build_render_bytes(PNG_BYTES, out=GeometryProbe(), cell_width_px=8, cell_height_px=16).decode("utf-8")
    assert rendered == expected
    assert PLACEHOLDER in rendered
    assert "\x1bPtmux;" not in rendered
    assert "[image/png]" not in rendered


def test_execute_result_images_start_on_new_line(shell, monkeypatch):
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setattr(kittycore.secrets, "randbelow", lambda _: 0x222222 - 1)

    shell.run_cell(
        """
from IPython.display import Image
import base64
Image(data=base64.b64decode(%r), format="png")
"""
        % PNG_B64,
        store_history=True,
    )

    rendered = shell._ipythonng_stream.getvalue()
    expected = build_render_bytes(PNG_BYTES, out=GeometryProbe(), cell_width_px=8, cell_height_px=16).decode("utf-8")
    assert rendered == "\n" + expected


def test_kitty_rendering_matches_kittytgp_inside_tmux(shell, monkeypatch):
    monkeypatch.setenv("TMUX", "/tmp/tmux")
    monkeypatch.setattr(kittycore.secrets, "randbelow", lambda _: 0x654321 - 1)

    shell.run_cell(
        """
from IPython.display import Image, display
import base64
display(Image(data=base64.b64decode(%r), format="png"))
"""
        % PNG_B64,
        store_history=True,
    )

    rendered = shell._ipythonng_stream.getvalue()
    expected = build_render_bytes(PNG_BYTES, out=GeometryProbe(), cell_width_px=8, cell_height_px=16).decode("utf-8")
    assert rendered == expected
    assert PLACEHOLDER in rendered
    assert "\x1bPtmux;" in rendered
    assert "[image/png]" not in rendered


def test_matplotlib_inline_plots_render_via_image_png(shell, monkeypatch, tmp_path):
    pytest.importorskip("matplotlib")
    mplconfig = tmp_path / "mplconfig"
    mplconfig.mkdir()
    monkeypatch.setenv("MPLCONFIGDIR", str(mplconfig))
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setattr(kittycore.secrets, "randbelow", lambda _: 0x333333 - 1)

    shell.run_line_magic("matplotlib", "inline")
    shell.run_cell("import matplotlib.pyplot as plt\nplt.plot([1, 2, 3])", store_history=True)

    rendered = shell._ipythonng_stream.getvalue()
    (_, _, (_, output)) = list(shell.history_manager.get_range(output=True))[-1]
    assert PLACEHOLDER in rendered
    assert "\x1b_G" in rendered
    assert "matplotlib.lines.Line2D" in output
    assert "[image/png]" in output


def test_matplotlib_inline_magic_suppresses_no_event_loop_message(shell, monkeypatch, tmp_path, capsys):
    pytest.importorskip("matplotlib")
    mplconfig = tmp_path / "mplconfig"
    mplconfig.mkdir()
    monkeypatch.setenv("MPLCONFIGDIR", str(mplconfig))

    capsys.readouterr()
    shell.run_line_magic("matplotlib", "inline")
    captured = capsys.readouterr()
    assert "No event loop hook running." not in captured.out


def test_matplotlib_inline_after_prior_plot_renders_future_plots(shell, monkeypatch, tmp_path, capsys):
    pytest.importorskip("matplotlib")
    mplconfig = tmp_path / "mplconfig"
    mplconfig.mkdir()
    monkeypatch.setenv("MPLCONFIGDIR", str(mplconfig))
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setattr(kittycore.secrets, "randbelow", lambda _: 0x444444 - 1)

    shell.run_cell("import matplotlib\nmatplotlib.use('agg')\nimport matplotlib.pyplot as plt\nplt.plot([1, 2, 3])", store_history=True)
    shell._ipythonng_stream.seek(0)
    shell._ipythonng_stream.truncate(0)

    capsys.readouterr()
    shell.run_line_magic("matplotlib", "inline")
    captured = capsys.readouterr()
    assert "No event loop hook running." not in captured.out

    shell.run_cell("plt.plot([4, 5, 6])", store_history=True)

    rendered = shell._ipythonng_stream.getvalue()
    output_types = [o.output_type for o in shell.history_manager.outputs.get(shell.execution_count - 1, [])]
    assert PLACEHOLDER in rendered
    assert "\x1b_G" in rendered
    assert "display_data" in output_types
