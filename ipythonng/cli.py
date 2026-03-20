import os,re,sys

from IPython import start_ipython

_IPYTHON_SHORT = set('mch')

def parse_flags(args=None):
    "Split args into (ng_flags, ipython_args), setting IPYTHONNG_FLAGS env var."
    if args is None: args = sys.argv[1:]
    ng_flags, ipython_args = [], []
    i = 0
    while i < len(args):
        if re.match(r'^-[a-zA-Z]$', args[i]) and args[i][1] not in _IPYTHON_SHORT:
            ng_flags.append(args[i])
            if i+1 < len(args) and not args[i+1].startswith('-'):
                ng_flags.append(args[i+1])
                i += 1
        else: ipython_args.append(args[i])
        i += 1
    if ng_flags: os.environ['IPYTHONNG_FLAGS'] = ' '.join(ng_flags)
    else: os.environ.pop('IPYTHONNG_FLAGS', None)
    return ng_flags, ipython_args

def main():
    _, ipython_args = parse_flags()
    start_ipython(argv=["--ext", "ipythonng", *ipython_args])
