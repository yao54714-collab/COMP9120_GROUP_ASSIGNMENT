"""Give pgAdmin's bundled Python access to the bundled libpq on Windows."""
import os
import runpy
import sys
handle=os.add_dll_directory(sys.argv[1]) if os.name=='nt' else None
script=sys.argv[2]
sys.argv=[script,*sys.argv[3:]]
runpy.run_path(script,run_name='__main__')
