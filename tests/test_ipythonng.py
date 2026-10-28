import base64, io, os, pytest
from fastcore.xtras import modified_env
from ipythonng.cli import parse_flags
from kittytgp.core import PLACEHOLDER
from helpers import output, render, run

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAIAAAADCAQAAABi6S9dAAAADElEQVR42mNkYPhfDwADhgGAff/3fwAAAABJRU5ErkJggg==')


def test_command_python_and_async_magic_input(shell, tmp_path):
    with modified_env('IPYTHONNG_FLAGS'):
        assert parse_flags(['-rp', '5', '-c', 'print(3)']) == (['-r', '-p', '5'], ['-c', 'print(3)'])
        assert parse_flags(['-m', 'foo']) == ([], ['-m', 'foo'])
    target = tmp_path/'nbs/01_drafting'
    target.mkdir(parents=True)
    shell.run_line_magic('cd', str(tmp_path))
    shell.alias_manager.define_alias('say', 'echo')
    assert shell.check_complete('say nbs/01_drafting.ipynb') == ('complete', '')
    assert 'nbs/01_drafting.ipynb' in run(shell, 'say nbs/01_drafting.ipynb')
    assert shell.check_complete('cd nbs/01_drafting')[0] == 'complete'
    run(shell, 'cd nbs/01_drafting')
    assert os.getcwd() == str(target)
    assert shell.check_complete('ls = (1,')[0] == 'incomplete'
    run(shell, 'ls = (1,\n2)')
    assert shell.user_ns['ls'] == (1, 2)
    shell.user_ns['say'] = 1
    assert shell.check_complete('say nbs/01_drafting.ipynb')[0] == 'invalid'
    for code in ('def f(x):', 'x = [1,', 'ls\nx = ('): assert shell.check_complete(code)[0] == 'incomplete'
    async def magic(line, cell): return f'{line}:{cell.strip()}'
    shell.register_magic_function(magic, magic_kind='cell', magic_name='story')
    for code in ('%%story first\nhello\n', "await get_ipython().run_cell_magic('story', 'first', 'hello')"):
        result = shell.run_cell(code, store_history=True)
        assert result.error_in_exec is None and result.result == 'first:hello'
        assert 'first:hello' in output(shell)


def test_rich_and_pty_history_survives_errors_and_a_new_session(shell):
    shell.user_ns['png'] = PNG
    with modified_env('TMUX'):
        assert run(shell, '''from IPython.display import Markdown, Image, display
image = Image(data=png, format='png')
class RawPng:
    def _repr_png_(self): return png
print('alpha')
display(Markdown('# Heading'))
display(image)
print('omega')
42''') == 'alpha\n# Heading\n[image/png]\nomega\n42'
        rendered = shell._ipythonng_stream.getvalue()
        assert PLACEHOLDER in rendered and '\x1b_G' in rendered and '\x1bPtmux;' not in rendered
        for expression in ('image', 'RawPng()'):
            rendered = render(shell, expression)
            assert rendered.startswith('\n') and PLACEHOLDER in rendered and '[image/png]' not in rendered
            assert output(shell) == '[image/png]'
    with modified_env(TMUX='/tmp/tmux'):
        assert '\x1bPtmux;' in render(shell, 'display(image)')
        assert '[image/png]' in output(shell)
    shell._ipythonng_stream = io.StringIO()
    assert render(shell, 'display(image)') == '[image/png]\n'
    assert output(shell) == '[image/png]'
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


def test_plotting_switches_from_existing_agg_figures_to_inline(shell):
    pytest.importorskip('matplotlib')
    run(shell, "import matplotlib; matplotlib.use('agg')\nimport matplotlib.pyplot as plt\nplt.plot([1, 2, 3])")
    assert shell.user_ns['plt'].get_fignums()
    for _ in range(2):
        shell.run_line_magic('matplotlib', 'inline')
        assert not shell.user_ns['plt'].get_fignums()
        rendered = render(shell, 'plt.plot([4, 5, 6])')
        assert PLACEHOLDER in rendered and '\x1b_G' in rendered and '[image/png]' in output(shell)
        assert any(o.output_type == 'display_data' for o in shell.history_manager.outputs[shell.execution_count-1])
