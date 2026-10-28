import os, select, signal

from ipythonng.jobs import spawn_job, copy_job, finish_job
from helpers import run


def attach(job, data=b''):
    read, write = os.pipe()
    os.write(write, data)
    os.close(write)
    try:
        with open(os.devnull, 'wb') as out: return copy_job(job, in_fd=read, out_fd=out.fileno())
    finally: os.close(read)


def test_terminal_ctrl_z_resume_input_and_signal_exit():
    job = spawn_job('echo ready; read x; echo got:$x; kill -TSTP 0; exec sleep 30')
    finished = False
    try:
        assert select.select([job.master_fd], [], [], 5)[0]
        job.captured.append(os.read(job.master_fd, 1024))
        assert b'ready' in b''.join(job.captured)
        os.write(job.master_fd, b'\x1a')
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
    run(shell, '!echo before && kill -TSTP 0 && echo after')
    assert 'Stopped' in capsys.readouterr().out and shell.user_ns['_exit_code'] == 128+signal.SIGTSTP
    run(shell, '%jobs')
    assert 'stopped' in capsys.readouterr().out
    text = run(shell, '%fg')
    assert not shell._ipythonng_jobs and shell.user_ns['_exit_code'] == 0
    assert 'before' in text and 'after' in text
    run(shell, '!kill -TSTP 0 && echo done')
    job = next(iter(shell._ipythonng_jobs.values()))
    run(shell, '%bg 1')
    assert select.select([job.status_r], [], [], 5)[0]
    capsys.readouterr()
    run(shell, '%jobs')
    assert 'done' in capsys.readouterr().out
    text = run(shell, '%fg 1')
    assert not shell._ipythonng_jobs and shell.user_ns['_exit_code'] == 0
    assert 'done' in text
    run(shell, '!exit 7')
    assert shell.user_ns['_exit_code'] == 7
    text = run(shell, '!echo recovered')
    assert shell.user_ns['_exit_code'] == 0 and not shell._ipythonng_jobs
    assert 'recovered' in text
