import os, select, signal, time, pytest
from IPython.terminal.interactiveshell import TerminalInteractiveShell
from traitlets.config import Config

from ipythonng import load_ipython_extension
from ipythonng.jobs import spawn_job, copy_job, finish_job
import ipythonng.jobs

def attach(job):
    "Run `job` against dummy in/out pipes, returning why it detached"
    rin,win = os.pipe(); rout,wout = os.pipe()
    try: return copy_job(job, in_fd=rin, out_fd=wout)
    finally:
        for fd in (rin,win,rout,wout): os.close(fd)

def kill(job):
    try: os.killpg(job.pgid, signal.SIGKILL)
    except ProcessLookupError: pass
    return finish_job(job)

def wait_gone(job, timeout=5):
    "Wait for `job` to finish: its status pipe hits EOF when the shepherd exits"
    return bool(select.select([job.status_r], [], [], timeout)[0])

def test_signal_suspends():
    job = spawn_job('sleep 5')
    os.killpg(job.pgid, signal.SIGTSTP)
    assert attach(job)=='stopped'
    kill(job)

def test_ctrl_z_suspends():
    "the ^Z byte typed at the terminal must suspend the job"
    job = spawn_job('sleep 5')
    os.write(job.master_fd, b'\x1a')
    assert attach(job)=='stopped'
    kill(job)

def test_suspend_resume_captures_all_output():
    job = spawn_job('echo before && kill -TSTP 0 && echo after')
    assert attach(job)=='stopped'
    assert b'before' in b''.join(job.captured)
    os.killpg(job.pgid, signal.SIGCONT)
    assert attach(job)=='eof'
    assert b'after' in b''.join(job.captured)
    assert finish_job(job)==0

def test_exit_codes():
    assert finish_job(spawn_job('exit 7'))==7
    job = spawn_job('sleep 5')
    time.sleep(0.2)
    os.killpg(job.pgid, signal.SIGTERM)
    assert finish_job(job)==-signal.SIGTERM

def test_stdin_reaches_job():
    rin,win = os.pipe(); rout,wout = os.pipe()
    job = spawn_job('read x && echo got:$x')
    os.write(win, b'hi\n')
    assert copy_job(job, in_fd=rin, out_fd=wout)=='eof'
    assert b'got:hi' in b''.join(job.captured)
    finish_job(job)
    for fd in (rin,win,rout,wout): os.close(fd)

@pytest.fixture
def shell(tmp_path):
    TerminalInteractiveShell.clear_instance()
    config = Config()
    config.TerminalInteractiveShell.simple_prompt = True
    config.HistoryManager.hist_file = str(tmp_path/'history.sqlite')
    shell = TerminalInteractiveShell.instance(config=config)
    load_ipython_extension(shell)
    try: yield shell
    finally:
        for j in list(shell._ipythonng_jobs.values()): kill(j)
        shell.history_manager.writeout_cache()
        shell.history_manager.end_session()
        shell._atexit_once = lambda: None
        TerminalInteractiveShell.clear_instance()

def test_suspended_job_returns_prompt(shell, capsys):
    shell.run_cell('!kill -TSTP 0', store_history=True)
    assert 'Stopped' in capsys.readouterr().out
    shell.run_cell('%jobs', store_history=True)
    assert 'kill -TSTP 0' in capsys.readouterr().out

def test_fg_resumes(shell):
    shell.run_cell('!kill -TSTP 0 && echo resumed', store_history=True)
    shell.run_cell('%fg', store_history=True)
    assert shell._ipythonng_jobs=={} and shell.user_ns['_exit_code']==0
    assert 'resumed' in shell.history_manager.output_hist_reprs.get(shell.execution_count-1, '')

def test_bg_runs_without_terminal(shell):
    shell.run_cell('!kill -TSTP 0 && echo done', store_history=True)
    job = next(iter(shell._ipythonng_jobs.values()))
    shell.run_cell('%bg', store_history=True)
    assert wait_gone(job)
    shell.run_cell('%fg', store_history=True)
    assert shell._ipythonng_jobs=={} and shell.user_ns['_exit_code']==0

def test_spawn_failure_raises_cleanly(monkeypatch):
    def boom(*a): raise OSError('shepherd broke')
    monkeypatch.setattr(ipythonng.jobs, '_shepherd', boom)
    with pytest.raises(OSError, match='failed to start job'): spawn_job('true')

def test_fg_rejects_bad_job(shell, capsys):
    shell.run_cell('%fg nope', store_history=True)
    assert 'no such job: nope' in capsys.readouterr().err

def test_jobs_notices_bg_exit(shell, capsys):
    shell.run_cell('!kill -TSTP 0', store_history=True)
    shell.run_cell('%bg', store_history=True)
    assert wait_gone(next(iter(shell._ipythonng_jobs.values())))
    capsys.readouterr()
    shell.run_cell('%jobs', store_history=True)
    assert 'done' in capsys.readouterr().out

def test_many_fg_commands(shell):
    for i in range(15):
        shell.run_cell(f'!echo hi{i}', store_history=True)
        assert shell.user_ns['_exit_code']==0
        assert f'hi{i}' in shell.history_manager.output_hist_reprs.get(shell.execution_count-1, '')
