"""Quote a stdlib source payload for read-only or approved checkpoint SSH."""
import base64,shlex,sys
from pathlib import Path
source=Path(sys.argv[1]);encoded=base64.b64encode(source.read_bytes()).decode()
code="import base64,sys;sys.argv="+repr([source.name]+sys.argv[2:])+";exec(compile(base64.b64decode("+repr(encoded)+"),"+repr(source.name)+",'exec'),{'__name__':'__main__'})"
print('python -c '+shlex.quote(code))
