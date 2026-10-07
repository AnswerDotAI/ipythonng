import os, select, signal, pytest

from ipythonng.jobs import spawn_job, copy_job, finish_job


def attach(job, data=b''):
    read, write = os.pipe()
    os.write(write, data)
    os.close(write)
    try:
        with open(os.devnull, 'wb') as out: return copy_job(job, in_fd=read, out_fd=out.fileno())
    finally: os.close(read)


@pytest.mark.parametrize('suspend', ['signal', 'ctrl-z'])
def test_terminal_suspend_resume_input_and_signal_exit(suspend):
    job = spawn_job('echo ready; read x; echo got:$x; kill -TSTP 0; exec sleep 30')
    finished = False
    try:
        assert select.select([job.master_fd], [], [], 5)[0]
        job.captured.append(os.read(job.master_fd, 1024))
        assert b'ready' in b''.join(job.captured)
        if suspend == 'signal': os.killpg(job.pgid, signal.SIGTSTP)
        else: os.write(job.master_fd, b'\x1a')
        assert attach(job) == 'stopped' and job.status() == 'stopped'
        os.killpg(job.pgid, signal.SIGCONT)
        assert attach(job, b'hi\n') == 'stopped'
        assert b'got:hi' in b''.join(job.captured)
        os.killpg(job.pgid, signal.SIGCONT)
        os.killpg(job.pgid, signal.SIGTERM)
        assert select.select([job.status_r], [], [], 5)[0]
        finished = True
    finally:
        if not finished:
            try: os.killpg(job.pgid, signal.SIGKILL)
            except ProcessLookupError: pass
        code = finish_job(job)
    assert code == -signal.SIGTERM


def test_shell_jobs_foreground_background_completion_and_recovery(shell, capsys):
    shell.run_cell('!echo before && kill -TSTP 0 && echo after', store_history=True)
    assert 'Stopped' in capsys.readouterr().out and shell.user_ns['_exit_code'] == 128+signal.SIGTSTP
    shell.run_cell('%jobs', store_history=True)
    assert 'stopped' in capsys.readouterr().out
    shell.run_cell('%fg', store_history=True)
    assert not shell._ipythonng_jobs and shell.user_ns['_exit_code'] == 0
    text = shell.history_manager.output_hist_reprs[shell.execution_count-1]
    assert 'before' in text and 'after' in text
    shell.run_cell('!kill -TSTP 0 && echo done', store_history=True)
    job = next(iter(shell._ipythonng_jobs.values()))
    shell.run_cell('%bg 1', store_history=True)
    assert select.select([job.status_r], [], [], 5)[0]
    capsys.readouterr()
    shell.run_cell('%jobs', store_history=True)
    assert 'done' in capsys.readouterr().out
    shell.run_cell('%fg 1', store_history=True)
    assert not shell._ipythonng_jobs and shell.user_ns['_exit_code'] == 0
    assert 'done' in shell.history_manager.output_hist_reprs[shell.execution_count-1]
    shell.run_cell('%fg nope', store_history=True)
    assert 'no such job: nope' in capsys.readouterr().err
    shell.run_cell('!exit 7', store_history=True)
    assert shell.user_ns['_exit_code'] == 7
    shell.run_cell('!echo recovered', store_history=True)
    assert shell.user_ns['_exit_code'] == 0 and not shell._ipythonng_jobs
    assert 'recovered' in shell.history_manager.output_hist_reprs[shell.execution_count-1]
