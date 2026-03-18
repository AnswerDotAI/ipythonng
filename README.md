# ipythonng

`ipythonng` is a small IPython extension for terminal sessions that adds:

- `text/markdown` rendering with Rich
- `image/png` rendering via `kittytgp`
- richer `%history -o` / persisted output history by flattening IPython's structured per-cell outputs after execution

It intentionally keeps the feature set narrow:

- kitty only, no sixel backend
- PNG only, no JPEG support
- markdown history always stores the markdown source
- image history always stores `[image/png]`

## Install

```bash
pip install ~/aai-ws/kittytgp ~/aai-ws/ipythonng
```

## Use as an extension

Add the extension and enable output logging in your IPython config:

```python
c.InteractiveShellApp.extensions = ["ipythonng"]
c.HistoryManager.db_log_output = True
c.InteractiveShellApp.exec_lines = ["%matplotlib inline"]  # optional, for inline matplotlib plots
```

Or launch it ad hoc:

```bash
ipython --ext ipythonng
```

For matplotlib, `%matplotlib inline` works with the existing `image/png` renderer. No custom matplotlib backend is needed. Using `exec_lines` runs the magic after extensions load, which is the cleanest startup path for terminal IPython.

## Convenience launcher

The package also installs an `ipythonng` command that simply starts IPython with
`--ext ipythonng`.
