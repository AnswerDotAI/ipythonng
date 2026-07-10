import pytest
from IPython.terminal.interactiveshell import TerminalInteractiveShell
from traitlets.config import Config

import ipythonng.extension  # applies the check_complete patch


@pytest.fixture
def shell(tmp_path):
    TerminalInteractiveShell.clear_instance()
    config = Config()
    config.TerminalInteractiveShell.simple_prompt = True
    config.HistoryManager.hist_file = str(tmp_path / "history.sqlite")
    sh = TerminalInteractiveShell.instance(config=config)
    try: yield sh
    finally:
        sh.history_manager.end_session()
        sh._atexit_once = lambda: None
        TerminalInteractiveShell.clear_instance()


def test_alias_command_completes(shell):
    "A filename the tokenizer chokes on must not trigger the continuation prompt"
    shell.alias_manager.define_alias('git', 'git')
    assert shell.check_complete('git diff nbs/01_drafting.ipynb') == ('complete', '')

def test_magic_command_completes(shell):
    assert shell.check_complete('cd nbs/01_drafting')[0] == 'complete'

def test_assignment_beats_command(shell):
    "`ls = (1,` is Python assignment: continuation prompt must survive"
    assert shell.check_complete('ls = (1,')[0] == 'incomplete'

def test_shadowed_name_stays_python(shell):
    shell.alias_manager.define_alias('git', 'git')
    shell.user_ns['git'] = 1
    assert shell.check_complete('git diff nbs/01_drafting.ipynb')[0] == 'incomplete'

def test_python_judgment_unchanged(shell):
    assert shell.check_complete('def f(x):')[0] == 'incomplete'
    assert shell.check_complete('x = [1,')[0] == 'incomplete'
    assert shell.check_complete('ls\nx = (')[0] == 'incomplete'  # multiline: no short-circuit
