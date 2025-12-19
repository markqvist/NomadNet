import os
import glob

from .NomadNetworkApp import NomadNetworkApp
from .Conversation import Conversation
from .Directory import Directory
from .Node import Node
from .ui import *


py_modules  = glob.glob(os.path.dirname(__file__)+"/*.py")
pyc_modules = glob.glob(os.path.dirname(__file__)+"/*.pyc")
modules     = py_modules+pyc_modules
__all__ = list(set([os.path.basename(f).replace(".pyc", "").replace(".py", "") for f in modules if not (f.endswith("__init__.py") or f.endswith("__init__.pyc"))]))

def panic():
    os._exit(255)