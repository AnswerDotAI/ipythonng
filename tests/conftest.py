import io, os, signal, pytest
from IPython.terminal.interactiveshell import TerminalInteractiveShell
from traitlets.config import Config

from ipythonng import load_ipython_extension, unload_ipython_extension
from ipythonng.jobs import finish_job


class TerminalOutput(io.StringIO):
    def isatty(self): return True


@pytest.fixture
def shell(tmp_path):
    TerminalInteractiveShell.clear_instance()
    config = Config()
    config.TerminalInteractiveShell.simple_prompt = True
    config.HistoryManager.hist_file = str(tmp_path/'history.sqlite')
    config.HistoryManager.db_log_output = True
    shell = TerminalInteractiveShell.instance(config=config)
    shell.history_manager.outputs.clear()  # IPython stores this buffer on the class, not the shell instance
    shell._ipythonng_stream = TerminalOutput()
    load_ipython_extension(shell)
    try: yield shell
    finally:
        for job in shell._ipythonng_jobs.values():
            try: os.killpg(job.pgid, signal.SIGKILL)
            except ProcessLookupError: pass
            finish_job(job)
        unload_ipython_extension(shell)
        shell.history_manager.writeout_cache()
        shell.history_manager.end_session()
        shell._atexit_once = lambda: None
        TerminalInteractiveShell.clear_instance()
