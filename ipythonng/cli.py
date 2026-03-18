import sys

from IPython import start_ipython


def main(): start_ipython(argv=["--ext", "ipythonng", *sys.argv[1:]])
