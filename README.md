# ipythonng

`ipythonng` is a small IPython extension for terminal sessions that adds:

- `text/markdown` rendering with Rich
- `image/png` rendering via `kittytgp`
- matplotlib inline support
- Includes display objects, streams, and rich results in stored history
- Stores complete Jupyter-style cell outputs in `Out[n]`

## Install

```bash
pip install ipythonng
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

## Cell outputs

`Out[n]` contains the ordered outputs from cell `n` as Jupyter-style dictionaries. This includes Python results, stdout and stderr, errors, rich displays, and shell command output:

```python
Out[3]
# [{'output_type': 'stream', 'name': 'stdout', 'text': 'hello\n'}]
```

Rich display data is stored as a MIME bundle. PNGs use Jupyter's base64 representation and can be decoded directly:

```python
from base64 import b64decode
png = b64decode(Out[4][0]['data']['image/png'])
```

Loading `ipythonng` intentionally changes standard IPython behavior: each `Out[n]` is a list containing every output from that cell, rather than only the final Python expression.

## Convenience launcher

The package also installs an `ipythonng` command that simply starts IPython with
`--ext ipythonng`.
