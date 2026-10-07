import base64, io, os, pytest
from kittytgp.core import PLACEHOLDER

from ipythonng.cli import parse_flags

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAIAAAADCAQAAABi6S9dAAAADElEQVR42mNkYPhfDwADhgGAff/3fwAAAABJRU5ErkJggg==')


def output(shell): return shell.history_manager.output_hist_reprs.get(shell.execution_count-1, '')


def run(shell, code):
    result = shell.run_cell(code, store_history=True)
    assert result.error_before_exec is None and result.error_in_exec is None
    return output(shell)


def render(shell, code):
    shell._ipythonng_stream.seek(0)
    shell._ipythonng_stream.truncate(0)
    run(shell, code)
    return shell._ipythonng_stream.getvalue()


def test_rich_and_pty_history_survives_errors_and_a_new_session(shell):
    shell.user_ns['png'] = PNG
    assert run(shell, '''from IPython.display import Markdown, Image, display
print('alpha')
display(Markdown('# Heading'))
display(Image(data=png, format='png'))
print('omega')
42''') == 'alpha\n# Heading\n[image/png]\nomega\n42'
    text = run(shell, r'''print('printed'); get_ipython().system("printf '\033[31mred\033[0m text\nline2\n'")''')
    assert text.splitlines() == ['printed', 'red text', 'line2'] and '\x1b[' not in text
    streams = shell.history_manager.outputs[shell.execution_count-1]
    assert any('line2' in ''.join(o.bundle.get('stream', [])) for o in streams if o.output_type == 'out_stream')
    assert run(shell, r"!printf '\033[?1049hhidden\033[?1049l'") == ''
    assert run(shell, 'pass') == ''
    result = shell.run_cell('1/0', store_history=True)
    assert isinstance(result.error_in_exec, ZeroDivisionError) and 'division by zero' in output(shell)
    result = shell.run_cell("class Message:\n    def __str__(self): return 'bad syntax'\nraise SyntaxError(Message())", store_history=True)
    assert isinstance(result.error_in_exec, SyntaxError) and 'bad syntax' in output(shell)
    assert run(shell, "print('recovered')") == 'recovered\n'
    saved = [(n, value) for _, n, (_, value) in shell.history_manager.get_range(output=True)]
    shell.history_manager.writeout_cache()
    shell.reset()
    assert [(n, value) for _, n, (_, value) in shell.history_manager.get_range(-1, output=True)] == saved
    assert run(shell, 'pass') == ''


def test_image_display_result_tmux_and_redirected_output(shell, monkeypatch):
    monkeypatch.delenv('TMUX', raising=False)
    shell.user_ns['png'] = PNG
    run(shell, '''from IPython.display import Image, display
image = Image(data=png, format='png')
class RawPng:
    def _repr_png_(self): return png''')
    rendered = render(shell, 'display(image)')
    assert PLACEHOLDER in rendered and '\x1b_G' in rendered and '\x1bPtmux;' not in rendered
    for expression in ('image', 'RawPng()'):
        rendered = render(shell, expression)
        assert rendered.startswith('\n') and PLACEHOLDER in rendered and '[image/png]' not in rendered
        assert output(shell) == '[image/png]'
    monkeypatch.setenv('TMUX', '/tmp/tmux')
    assert '\x1bPtmux;' in render(shell, 'display(image)')
    shell._ipythonng_stream = io.StringIO()
    assert render(shell, 'display(image)') == '[image/png]\n'
    assert output(shell) == '[image/png]'


def test_plotting_switches_from_existing_agg_figures_to_inline(shell, monkeypatch, tmp_path, capsys):
    pytest.importorskip('matplotlib')
    monkeypatch.setenv('MPLCONFIGDIR', str(tmp_path/'mplconfig'))
    monkeypatch.delenv('TMUX', raising=False)
    run(shell, "import matplotlib; matplotlib.use('agg')\nimport matplotlib.pyplot as plt\nplt.plot([1, 2, 3])")
    assert shell.user_ns['plt'].get_fignums()
    for values in ('[4, 5, 6]', '[7, 8, 9]'):
        capsys.readouterr()
        shell.run_line_magic('matplotlib', 'inline')
        assert 'No event loop hook running.' not in capsys.readouterr().out
        assert not shell.user_ns['plt'].get_fignums()
        rendered = render(shell, f'plt.plot({values})')
        assert PLACEHOLDER in rendered and '\x1b_G' in rendered
        assert 'matplotlib.lines.Line2D' in output(shell) and '[image/png]' in output(shell)
        assert 'display_data' in [o.output_type for o in shell.history_manager.outputs[shell.execution_count-1]]


def test_launcher_flags_preserve_ipython_arguments_and_reset_environment(monkeypatch):
    monkeypatch.delenv('IPYTHONNG_FLAGS', raising=False)
    assert parse_flags(['-rp', '5', '-c', 'print(3)']) == (['-r', '-p', '5'], ['-c', 'print(3)'])
    assert os.environ['IPYTHONNG_FLAGS'] == '-r -p 5'
    assert parse_flags(['-m', 'foo']) == ([], ['-m', 'foo'])
    assert 'IPYTHONNG_FLAGS' not in os.environ
