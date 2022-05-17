import os
import glob
import RNS
import nomadnet

modules = glob.glob(os.path.dirname(__file__)+"/*.py")
__all__ = [ os.path.basename(f)[:-3] for f in modules if not f.endswith('__init__.py')]


UI_NONE       = 0x00
UI_MENU       = 0x01
UI_TEXT       = 0x02
UI_GRAPHICAL  = 0x03
UI_WEB        = 0x04
UI_MODES = [UI_NONE, UI_MENU, UI_TEXT, UI_GRAPHICAL, UI_WEB]

def spawn(uimode):
    if uimode in UI_MODES:
        if uimode == UI_NONE:
            RNS.log("Starting Nomad Network daemon...", RNS.LOG_INFO)
        else:
            RNS.log("Starting user interface...", RNS.LOG_INFO)

        if uimode == UI_MENU:
            from .MenuUI import MenuUI
            return MenuUI()
        elif uimode == UI_TEXT:
            from .TextUI import TextUI
            return TextUI()
        elif uimode == UI_GRAPHICAL:
            from .GraphicalUI import GraphicalUI
            return GraphicalUI()
        elif uimode == UI_WEB:
            from .WebUI import WebUI
            return WebUI()
        elif uimode == UI_NONE:
            from .NoneUI import NoneUI
            return NoneUI()
        else:
            return None
    else:
        RNS.log("Invalid UI mode", RNS.LOG_ERROR, _override_destination=True)
        nomadnet.panic()