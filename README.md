# ipythonng

`ipythonng` is a small IPython extension for terminal sessions that adds:

- `text/markdown` rendering with Rich
- `image/png` rendering via `kittytgp`
- matplotlib inline support
- Includes display objects, streams, and rich results in stored history

## Install

```bash
pip install ~/aai-ws/kittytgp ~/aai-ws/ipythonng
```

## Use as an extension

Add the extension and enable output logging in your IPython config:

```python
c.InteractiveShellApp.extensions = ["ipythonng"]
c.HistoryManager.db_log_output = True
c.InteractiveShellApp.exec_lines = ["%matplotlib inline"]  # if you like
```

Or launch it ad hoc:

```bash
ipython --ext ipythonng
```

For matplotlib, `%matplotlib inline` works with the existing `image/png` renderer. No custom matplotlib backend is needed. Using `exec_lines` runs the magic after extensions load.

## Convenience launcher

The package also installs an `ipythonng` command that simply starts IPython with
`--ext ipythonng`.
