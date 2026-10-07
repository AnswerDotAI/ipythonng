def test_command_python_and_async_magic_input(shell, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path/'nbs/01_drafting').mkdir(parents=True)
    shell.alias_manager.define_alias('say', 'echo')
    assert shell.check_complete('say nbs/01_drafting.ipynb') == ('complete', '')
    shell.run_cell('say nbs/01_drafting.ipynb', store_history=True)
    assert 'nbs/01_drafting.ipynb' in shell.history_manager.output_hist_reprs[shell.execution_count-1]
    assert shell.check_complete('cd nbs/01_drafting')[0] == 'complete'
    shell.run_cell('cd nbs/01_drafting', store_history=True)
    assert shell.user_ns['_dh'][-1] == tmp_path/'nbs/01_drafting'
    assert shell.check_complete('ls = (1,')[0] == 'incomplete'
    shell.run_cell('ls = (1,\n2)', store_history=True)
    assert shell.user_ns['ls'] == (1, 2)
    shell.user_ns['say'] = 1
    assert shell.check_complete('say nbs/01_drafting.ipynb')[0] == 'invalid'
    for code in ('def f(x):', 'x = [1,', 'ls\nx = ('): assert shell.check_complete(code)[0] == 'incomplete'
    async def magic(line, cell): return f'{line}:{cell.strip()}'
    shell.register_magic_function(magic, magic_kind='cell', magic_name='story')
    for code in ('%%story first\nhello\n', "await get_ipython().run_cell_magic('story', 'first', 'hello')"):
        result = shell.run_cell(code, store_history=True)
        assert not result.error_in_exec and result.result == 'first:hello'
        assert shell.history_manager.output_hist_reprs[result.execution_count] == "'first:hello'"
