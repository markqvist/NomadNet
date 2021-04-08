import os
import glob
import RNS
import nomadnet

from .MenuUI      import MenuUI
from .TextUI      import TextUI
from .GraphicalUI import GraphicalUI
from .WebUI       import WebUI

UI_NONE       = 0x00
UI_MENU       = 0x01
UI_TEXT       = 0x02
UI_GRAPHICAL  = 0x03
UI_WEB        = 0x04

UI_MODES = [UI_MENU, UI_TEXT, UI_GRAPHICAL, UI_WEB]

modules = glob.glob(os.path.dirname(__file__)+"/*.py")
__all__ = [ os.path.basename(f)[:-3] for f in modules if not f.endswith('__init__.py')]

def spawn(uimode):
    if uimode in UI_MODES:
        RNS.log("Starting user interface...", RNS.LOG_INFO)
        if uimode == UI_MENU:
            return MenuUI()
        elif uimode == UI_TEXT:
            return TextUI()
        elif uimode == UI_GRAPHICAL:
            return GraphicalUI()
        elif uimode == UI_WEB:
            return WebUI()
        else:
            return None
    else:
        RNS.log("Invalid UI mode", RNS.LOG_ERROR)
        nomadnet.panic()