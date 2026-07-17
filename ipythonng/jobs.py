"Job control for PTY commands, via a shepherd process that relays suspends and carries the exit status"
import os, pty, select, signal
from fastcore.basics import store_attr

__all__ = ['Job', 'spawn_job', 'copy_job', 'finish_job']

class Job:
    "A PTY command: `pid` is its shepherd, `pgid` the command's own process group"
    def __init__(self, cmd, pid, pgid, master_fd, status_r):
        store_attr()
        self.captured,self.state = [],'running'
    def __repr__(self): return f'Job({self.cmd!r}, pgid={self.pgid}, {self.state})'
    def status(self):
        "Refresh and return `state`, noticing a background job that has stopped or exited"
        while self.state=='running' and select.select([self.status_r], [], [], 0)[0]:
            msg = _read_line(self.status_r)
            if msg.startswith('stopped'): self.state = 'stopped'
            elif not msg: self.state = 'done'
        return self.state

def _read_line(fd):
    buf = b''
    while not buf.endswith(b'\n'):
        b = os.read(fd, 1)
        if not b: break
        buf += b
    return buf.decode()

def _writen(fd, data):
    while data: data = data[os.write(fd, data):]

def _shepherd(cmd, sh, status_w):
    "Run `cmd` in its own pgrp (keeps it suspendable) and relay its stops -- runs inside the pty session"
    cmd_pid = os.fork()
    if cmd_pid==0:
        os.setpgid(0, 0)
        signal.signal(signal.SIGTTOU, signal.SIG_IGN)
        os.tcsetpgrp(0, os.getpgrp())
        # reset childs disposition
        for s in (signal.SIGINT,signal.SIGQUIT,signal.SIGTSTP,signal.SIGTTIN,signal.SIGTTOU,signal.SIGPIPE): signal.signal(s, signal.SIG_DFL)
        os.execlp(sh, 'sh', '-c', cmd)
    try: os.setpgid(cmd_pid, cmd_pid)
    except OSError: pass
    os.tcsetpgrp(0, cmd_pid)
    os.write(status_w, f'pgid {cmd_pid}\n'.encode())
    while True:
        _, st = os.waitpid(cmd_pid, os.WUNTRACED)
        if os.WIFSTOPPED(st): os.write(status_w, b'stopped\n')
        else:
            ec = os.waitstatus_to_exitcode(st)
            os._exit(ec if ec>=0 else 128-ec)

def spawn_job(cmd, sh=None):
    "Fork a shepherd on a fresh PTY running `cmd`; returns the parent-side `Job`"
    sh = sh or os.environ.get('SHELL', '/bin/sh')
    status_r,status_w = os.pipe()
    pid,master_fd = pty.fork()
    if pid==0:
        os.close(status_r)
        try: _shepherd(cmd, sh, status_w)
        finally: os._exit(127)
    os.close(status_w)
    msg = _read_line(status_r).split()
    if not msg or msg[0]!='pgid':
        os.close(master_fd); os.close(status_r); os.waitpid(pid, 0)
        raise OSError(f'failed to start job: {cmd!r}')
    return Job(cmd, pid, int(msg[1]), master_fd, status_r)

def _drain(job, out_fd):
    "Forward any buffered pty output"
    while select.select([job.master_fd], [], [], 0)[0]:
        try: data = os.read(job.master_fd, 1024)
        except OSError: return
        if not data: return
        job.captured.append(data)
        _writen(out_fd, data)

def copy_job(job, in_fd=pty.STDIN_FILENO, out_fd=pty.STDOUT_FILENO):
    "Shuttle bytes between `in_fd`/`out_fd` and the job's pty until it exits ('eof') or suspends ('stopped')"
    fds = [job.master_fd, job.status_r, in_fd]
    while True:
        rfds,_,_ = select.select(fds, [], [])
        if job.master_fd in rfds:
            try: data = os.read(job.master_fd, 1024)
            except OSError: data = b''
            if not data: return 'eof'
            job.captured.append(data)
            _writen(out_fd, data)
        if in_fd in rfds:
            data = os.read(in_fd, 1024)
            if data: _writen(job.master_fd, data)
            else: fds.remove(in_fd)
        if job.status_r in rfds:
            if _read_line(job.status_r).startswith('stopped'):
                _drain(job, out_fd)
                job.state = 'stopped'
                return 'stopped'
            fds.remove(job.status_r)  # EOF: shepherd has exited

def finish_job(job):
    "Reap the shepherd, then close the pty; returns the command's exit code (negative = killed by that signal)"
    _, status = os.waitpid(job.pid, 0)  # reap first: closing the master would SIGHUP the shepherd
    os.close(job.master_fd)
    os.close(job.status_r)
    ec = os.waitstatus_to_exitcode(status)
    return -(ec-128) if ec>128 else ec
