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
