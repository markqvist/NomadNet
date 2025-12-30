import RNS
import LXMF
import io
import os
import time
import urwid
import shutil
import nomadnet
import subprocess
import threading
from threading import Lock
from .MicronParser import markup_to_attrmaps, make_style, default_state
from nomadnet.Directory import DirectoryEntry
from nomadnet.vendor.Scrollable import *
from nomadnet.util import strip_modifiers

class BrowserFrame(urwid.Frame):
    def keypress(self, size, key):
        if key == "ctrl w":
            self.delegate.disconnect()
        elif key == "ctrl d":
            self.delegate.back()
        elif key == "ctrl f":
            self.delegate.forward()
        elif key == "ctrl r":
            self.delegate.reload()
        elif key == "ctrl u":
            self.delegate.url_dialog()
        elif key == "ctrl s":
            self.delegate.save_node_dialog()
        elif key == "ctrl b":
            self.delegate.save_node_dialog()
        elif key == "ctrl g":
            nomadnet.NomadNetworkApp.get_shared_instance().ui.main_display.sub_displays.network_display.toggle_fullscreen()
        elif self.focus_position == "body":
            if key == "down" or key == "up":
                try:
                    if hasattr(self.delegate, "page_pile") and self.delegate.page_pile:
                        def df(loop, user_data):
                            st = None
                            if self.delegate.page_pile:
                                nf = self.delegate.page_pile.focus
                                if hasattr(nf, "key_timeout"):
                                    st = nf
                                elif hasattr(nf, "original_widget"):
                                    no = nf.original_widget
                                    if hasattr(no, "original_widget"):
                                        st = no.original_widget
                                    else:
                                        if hasattr(no, "key_timeout"):
                                            st = no
                            
                                if st and hasattr(st, "key_timeout") and hasattr(st, "keypress") and callable(st.keypress):
                                    st.keypress(None, None)

                        nomadnet.NomadNetworkApp.get_shared_instance().ui.loop.set_alarm_in(0.25, df)
                
                except Exception as e:
                    RNS.log("Error while setting up cursor timeout. The contained exception was: "+str(e), RNS.LOG_ERROR)
                                        
            return super(BrowserFrame, self).keypress(size, key)

        else:
            return super(BrowserFrame, self).keypress(size, key)

class Browser:
    DEFAULT_PATH       = "/page/index.mu"
    DEFAULT_TIMEOUT    = 10
    DEFAULT_CACHE_TIME = 12*60*60

    NO_PATH            = 0x00
    PATH_REQUESTED     = 0x01
    ESTABLISHING_LINK  = 0x02
    LINK_TIMEOUT       = 0x03
    LINK_ESTABLISHED   = 0x04
    REQUESTING         = 0x05
    REQUEST_SENT       = 0x06
    REQUEST_FAILED     = 0x07
    REQUEST_TIMEOUT    = 0x08
    RECEIVING_RESPONSE = 0x09
    DISCONECTED        = 0xFE
    DONE               = 0xFF

    def __init__(self, app, app_name, aspects, destination_hash = None, path = None, auth_identity = None, delegate = None):
        self.app = app
        self.g = self.app.ui.glyphs
        self.delegate = delegate
        self.app_name = app_name
        self.aspects = aspects
        self.destination_hash = destination_hash
        self.path = path
        self.request_data = None
        self.timeout = Browser.DEFAULT_TIMEOUT
        self.last_keypress = None

        self.link = None
        self.loopback = None
        self.status = Browser.DISCONECTED
        self.progress_updated_at = None
        self.previous_progress = 0
        self.response_progress = 0
        self.response_speed = None
        self.response_size = None
        self.response_transfer_size = None
        self.page_background_color = None
        self.page_foreground_color = None
        self.saved_file_name = None
        self.page_data = None
        self.displayed_page_data = None
        self.auth_identity = auth_identity
        self.display_widget = None
        self.link_status_showing = False
        self.link_target = None
        self.frame = None
        self.attr_maps = []
        self.page_pile = None
        self.page_partials = {}
        self.updater_running = False
        self.partial_updater_lock = Lock()
        self.build_display()

        self.history = []
        self.history_ptr = 0
        self.history_inc = False
        self.history_dec = False
        self.reloading = False
        self.loaded_from_cache = False

        if self.path == None:
            self.path = Browser.DEFAULT_PATH

        if self.destination_hash != None:
            self.load_page()

        self.clean_cache()

    def current_url(self):
        if self.destination_hash == None:
            return ""
        else:
            if self.path == None:
                path = ""
            else:
                path = self.path
            return RNS.hexrep(self.destination_hash, delimit=False)+":"+path

    def url_hash(self, url):
        if url == None:
            return None
        else:
            url = url.encode("utf-8")
            return RNS.hexrep(RNS.Identity.full_hash(url), delimit=False)


    def marked_link(self, link_target):
        if self.status == Browser.DONE:
            self.link_target = link_target
            self.app.ui.loop.set_alarm_in(0.1, self.marked_link_job)

    def marked_link_job(self, sender, event):
        link_target = self.link_target

        if link_target == None:
            if self.link_status_showing:
                self.browser_footer = self.make_status_widget()
                self.frame.contents["footer"] = (self.browser_footer, self.frame.options())
                self.link_status_showing = False
                if self.page_background_color != None or self.page_foreground_color != None:
                    style_name = make_style(default_state(fg=self.page_foreground_color, bg=self.page_background_color))
                    self.browser_footer.set_attr_map({None: style_name})
        else:
            self.link_status_showing = True
            self.browser_footer = urwid.AttrMap(urwid.Pile([urwid.Divider(self.g["divider1"]), urwid.Text("Link to: "+str(link_target))]), "browser_controls")
            self.frame.contents["footer"] = (self.browser_footer, self.frame.options())
            if self.page_background_color != None or self.page_foreground_color != None:
                style_name = make_style(default_state(fg=self.page_foreground_color, bg=self.page_background_color))
                self.browser_footer.set_attr_map({None: style_name})

    def expand_shorthands(self, destination_type):
        if destination_type == "nnn":
            return "nomadnetwork.node"
        elif destination_type == "lxmf":
            return "lxmf.delivery"
        else:
            return destination_type

    def handle_link(self, link_target, link_data = None):
        partial_ids = None
        request_data = None
        if link_data != None:
            link_fields = []
            request_data = {}
            all_fields = True if "*" in link_data else False

            for e in link_data:
                if "=" in e:
                    c = e.split("=")
                    if len(c) == 2:
                        request_data["var_"+str(c[0])] = str(c[1])
                else:
                    link_fields.append(e)

                def recurse_down(w):
                    if isinstance(w, list):
                        for t in w:
                            recurse_down(t)
                    elif isinstance(w, tuple):
                        for t in w:
                            recurse_down(t)
                    elif hasattr(w, "contents"):
                        recurse_down(w.contents)
                    elif hasattr(w, "original_widget"):
                        recurse_down(w.original_widget)
                    elif hasattr(w, "_original_widget"):
                        recurse_down(w._original_widget)
                    else:
                        if hasattr(w, "field_name") and (all_fields or w.field_name in link_fields):
                            field_key = "field_" + w.field_name
                            if isinstance(w, urwid.Edit):
                                request_data[field_key] = w.edit_text
                            elif isinstance(w, urwid.RadioButton):
                                if w.state:
                                    user_data = getattr(w, "field_value", None)  
                                    if user_data is not None:
                                        request_data[field_key] = user_data
                            elif isinstance(w, urwid.CheckBox):
                                user_data = getattr(w, "field_value", "1")
                                if w.state:
                                    existing_value = request_data.get(field_key, '')
                                    if existing_value:
                                        # Concatenate the new value with the existing one
                                        request_data[field_key] = existing_value + ',' + user_data
                                    else:
                                        # Initialize the field with the current value
                                        request_data[field_key] = user_data
                                else:
                                    pass  # do nothing if checkbox is not check

            recurse_down(self.attr_maps)
            RNS.log("Including request data: "+str(request_data), RNS.LOG_DEBUG)

        components = link_target.split("@")
        destination_type = None

        if len(components) == 2:
            destination_type = self.expand_shorthands(components[0])
            link_target = components[1]
        elif link_target.startswith("p:"):
            comps = link_target.split(":")
            if len(comps) > 1: partial_ids = comps[1:]
            destination_type = "partial"
        else:
            destination_type = "nomadnetwork.node"
            link_target = components[0]

        if destination_type == "nomadnetwork.node":
            if self.status >= Browser.DISCONECTED:
                RNS.log("Browser handling link to: "+str(link_target), RNS.LOG_DEBUG)
                self.browser_footer = urwid.Text("Opening link to: "+str(link_target))
                try:
                    self.retrieve_url(link_target, request_data)
                except Exception as e:
                    self.browser_footer = urwid.Text("Could not open link: "+str(e))
                    self.frame.contents["footer"] = (self.browser_footer, self.frame.options())
            else:
                RNS.log("Browser already handling link, cannot handle link to: "+str(link_target), RNS.LOG_DEBUG)

        elif destination_type == "lxmf.delivery":
            RNS.log("Passing LXMF link to handler", RNS.LOG_DEBUG)
            self.handle_lxmf_link(link_target)

        elif destination_type == "partial":
            if partial_ids != None and len(partial_ids) > 0: self.handle_partial_updates(partial_ids)

        else:
            RNS.log("No known handler for destination type "+str(destination_type), RNS.LOG_DEBUG)
            self.browser_footer = urwid.Text("Could not open link: "+"No known handler for destination type "+str(destination_type))
            self.frame.contents["footer"] = (self.browser_footer, self.frame.options())

    def handle_lxmf_link(self, link_target):
        try:
            if not type(link_target) is str:
                raise ValueError("Invalid data type for LXMF link")

            if len(link_target) != (RNS.Reticulum.TRUNCATED_HASHLENGTH//8)*2:
                raise ValueError("Invalid length for LXMF link")

            try:
                bytes.fromhex(link_target)

            except Exception as e:
                raise ValueError("Could not decode destination hash from LXMF link")

            existing_conversations = nomadnet.Conversation.conversation_list(self.app)
            
            source_hash_text = link_target
            display_name_data = RNS.Identity.recall_app_data(bytes.fromhex(source_hash_text))

            display_name = None
            if display_name_data != None:
                display_name = LXMF.display_name_from_app_data(display_name_data)

            if not source_hash_text in [c[0] for c in existing_conversations]:
                entry = DirectoryEntry(bytes.fromhex(source_hash_text), display_name=display_name)
                self.app.directory.remember(entry)

                new_conversation = nomadnet.Conversation(source_hash_text, nomadnet.NomadNetworkApp.get_shared_instance(), initiator=True)
                self.app.ui.main_display.sub_displays.conversations_display.update_conversation_list()

            self.app.ui.main_display.sub_displays.conversations_display.display_conversation(None, source_hash_text)
            self.app.ui.main_display.show_conversations(None)

        except Exception as e:
            RNS.log("Error while starting conversation from link. The contained exception was: "+str(e), RNS.LOG_ERROR)
            self.browser_footer = urwid.Text("Could not open LXMF link: "+str(e))
            self.frame.contents["footer"] = (self.browser_footer, self.frame.options())


    def micron_released_focus(self):
        if self.delegate != None:
            self.delegate.focus_lists()

    def build_display(self):
        self.browser_header = urwid.Text("")
        self.browser_footer = urwid.Text("")

        self.page_pile = None
        self.page_partials = {}
        self.browser_body = urwid.Filler(
            urwid.Text("Disconnected\n"+self.g["arrow_l"]+"  "+self.g["arrow_r"], align=urwid.CENTER),
            urwid.MIDDLE,
        )

        self.frame = BrowserFrame(self.browser_body, header=self.browser_header, footer=self.browser_footer)
        self.frame.delegate = self
        self.linebox = urwid.LineBox(self.frame, title="Remote Node")
        self.display_widget = urwid.AttrMap(self.linebox, "inactive_text")

    def make_status_widget(self):
        if self.response_progress > 0:
            if self.page_background_color != None or self.page_foreground_color != None:
                style_name = make_style(default_state(fg=self.page_foreground_color, bg=self.page_background_color))
                style_name_inverted = make_style(default_state(bg=self.page_foreground_color, fg=self.page_background_color))
            else:
                style_name = "progress_empty"
                style_name_inverted = "progress_full"

            pb = ResponseProgressBar(style_name , style_name_inverted, current=self.response_progress, done=1.0, satt=None, owner=self)
            widget = urwid.Pile([urwid.Divider(self.g["divider1"]), pb])
        else:
            widget = urwid.Pile([urwid.Divider(self.g["divider1"]), urwid.Text(self.status_text())])

        return urwid.AttrMap(widget, "browser_controls")

    def make_control_widget(self):
        return urwid.AttrMap(urwid.Pile([urwid.Text(self.g["node"]+" "+self.current_url()), urwid.Divider(self.g["divider1"])]), "browser_controls")

    def make_request_failed_widget(self):
        def back_action(sender):
            self.status = Browser.DONE
            self.destination_hash = self.previous_destination_hash
            self.path = self.previous_path
            self.update_display()

        columns = urwid.Columns([
            (urwid.WEIGHT, 0.5, urwid.Text(" ")),
            (8, urwid.Button("Back", on_press=back_action)),
            (urwid.WEIGHT, 0.5, urwid.Text(" ")),
        ])

        if len(self.attr_maps) > 0:
            pile = urwid.Pile([
                urwid.Text("!\n\n"+self.status_text()+"\n", align=urwid.CENTER),
                columns
            ])
        else:
            pile = urwid.Pile([urwid.Text("!\n\n"+self.status_text(), align=urwid.CENTER)])

        return urwid.Filler(pile, urwid.MIDDLE)
    
    def update_display(self):
        if self.status == Browser.DISCONECTED:
            self.display_widget.set_attr_map({None: "inactive_text"})
            self.page_pile = None
            self.page_partials = {}
            self.browser_body = urwid.Filler(
                urwid.Text("Disconnected\n"+self.g["arrow_l"]+"  "+self.g["arrow_r"], align=urwid.CENTER),
                urwid.MIDDLE,
            )
            self.browser_footer = urwid.Text("")
            self.browser_header = urwid.Text("")
            self.linebox.set_title("Remote Node")
        else:
            self.display_widget.set_attr_map({None: "body_text"})
            self.browser_header = self.make_control_widget()
            if self.page_background_color != None or self.page_foreground_color != None:
                style_name = make_style(default_state(fg=self.page_foreground_color, bg=self.page_background_color))
                self.browser_header.set_attr_map({None: style_name})

            if self.destination_hash != None:
                remote_display_string = self.app.directory.simplest_display_str(self.destination_hash)
            else:
                remote_display_string = ""

            if self.loopback != None and remote_display_string == RNS.prettyhexrep(self.loopback):
                remote_display_string = self.app.node.name

            self.linebox.set_title(remote_display_string)

            if self.status == Browser.DONE:
                self.browser_footer = self.make_status_widget()
                self.update_page_display()

                if self.page_background_color != None or self.page_foreground_color != None:
                    style_name = make_style(default_state(fg=self.page_foreground_color, bg=self.page_background_color))
                    self.browser_body.set_attr_map({None: style_name})
                    self.browser_footer.set_attr_map({None: style_name})
                    self.browser_header.set_attr_map({None: style_name})
                    self.display_widget.set_attr_map({None: style_name})
            
            elif self.status == Browser.LINK_TIMEOUT:
                self.browser_body = self.make_request_failed_widget()
                self.browser_footer = urwid.Text("")
            
            elif self.status <= Browser.REQUEST_SENT:
                if len(self.attr_maps) == 0:
                    self.browser_body = urwid.Filler(
                        urwid.Text("Retrieving\n["+self.current_url()+"]", align=urwid.CENTER),
                        urwid.MIDDLE,
                    )

                self.browser_footer = self.make_status_widget()

                if self.page_background_color != None or self.page_foreground_color != None:
                    style_name = make_style(default_state(fg=self.page_foreground_color, bg=self.page_background_color))
                    self.browser_footer.set_attr_map({None: style_name})
                    self.browser_header.set_attr_map({None: style_name})
                    self.display_widget.set_attr_map({None: style_name})
            
            elif self.status == Browser.REQUEST_FAILED:
                self.browser_body = self.make_request_failed_widget()
                self.browser_footer = urwid.Text("")
            
            elif self.status == Browser.REQUEST_TIMEOUT:
                self.browser_body = self.make_request_failed_widget()
                self.browser_footer = urwid.Text("")
            
            else:
                pass

        self.frame.contents["body"] = (self.browser_body, self.frame.options())
        self.frame.contents["header"] = (self.browser_header, self.frame.options())
        self.frame.contents["footer"] = (self.browser_footer, self.frame.options())

    def update_page_display(self):
        pile = urwid.Pile(self.attr_maps)
        pile.automove_cursor_on_scroll = True
        self.page_pile = pile
        self.page_partials = {}
        self.browser_body = urwid.AttrMap(ScrollBar(Scrollable(pile, force_forward_keypress=True), thumb_char="\u2503", trough_char=" "), "scrollbar")
        self.detect_partials()

    def parse_url(self, url):
        path = None
        destination_hash = None
        components = url.split(":")
        if len(components) == 1:
            if len(components[0]) == (RNS.Reticulum.TRUNCATED_HASHLENGTH//8)*2:
                try: destination_hash = bytes.fromhex(components[0])
                except Exception as e: raise ValueError("Malformed URL")
                path = Browser.DEFAULT_PATH
            else: raise ValueError("Malformed URL")
        elif len(components) == 2:
            if len(components[0]) == (RNS.Reticulum.TRUNCATED_HASHLENGTH//8)*2:
                try: destination_hash = bytes.fromhex(components[0])
                except Exception as e: raise ValueError("Malformed URL")
                path = components[1]
                if len(path) == 0: path = Browser.DEFAULT_PATH
            else:
                if len(components[0]) == 0:
                    if self.destination_hash != None:
                        destination_hash = self.destination_hash
                        path = components[1]
                        if len(path) == 0: path = Browser.DEFAULT_PATH
                    else: raise ValueError("Malformed URL")
                else: raise ValueError("Malformed URL")
        else: raise ValueError("Malformed URL")

        return destination_hash, path

    def detect_partials(self):
        for w in self.attr_maps:
            o = w._original_widget
            if hasattr(o, "partial_hash"):
                RNS.log(f"Found partial: {o.partial_hash} / {o.partial_url} / {o.partial_refresh}")
                partial = {"hash": o.partial_hash, "id": o.partial_id, "url": o.partial_url, "fields": o.partial_fields,
                           "refresh": o.partial_refresh, "content": None, "updated": None, "update_requested": None, "request_id": None,
                            "destination": None, "link": None, "pile": o, "attr_maps": None, "failed": False, "pr_throttle": 0}

                self.page_partials[o.partial_hash] = partial

        if len(self.page_partials) > 0: self.start_partial_updater()

    def partial_failed(self, request_receipt):
        RNS.log("Loading page partial failed", RNS.LOG_ERROR)
        for pid in self.page_partials:
            partial = self.page_partials[pid]
            if partial["request_id"] == request_receipt.request_id:
                try:
                    partial["updated"] = time.time()
                    partial["request_id"] = None
                    partial["content"] = None
                    partial["attr_maps"] = None
                    url = partial["url"]
                    pile = partial["pile"]
                    pile.contents = [(urwid.Text(f"Could not load partial {url}: The resource transfer failed"), pile.options())]
                except Exception as e:
                    RNS.log(f"Error in partial failed callback: {e}", RNS.LOG_ERROR)
                    RNS.trace_exception(e)

    def partial_progressed(self, request_receipt):
        pass

    def partial_received(self, request_receipt):
        for pid in self.page_partials:
            partial = self.page_partials[pid]
            if partial["request_id"] == request_receipt.request_id:
                try:
                    partial["updated"] = partial["update_requested"]
                    partial["request_id"] = None
                    partial["content"] = request_receipt.response.decode("utf-8").rstrip()
                    partial["attr_maps"] = markup_to_attrmaps(strip_modifiers(partial["content"]), url_delegate=self, fg_color=self.page_foreground_color, bg_color=self.page_background_color)
                    pile = partial["pile"]
                    pile.contents = [(e, pile.options()) for e in partial["attr_maps"]]

                except Exception as e:
                    RNS.trace_exception(e)

    def __load_partial(self, partial):
        if partial["failed"] == True: return
        try: partial_destination_hash, path = self.parse_url(partial["url"])
        except Exception as e:
            RNS.log(f"Could not parse partial URL: {e}", RNS.LOG_ERROR)
            partial["failed"] = True
            pile = partial["pile"]
            url = partial["url"]
            pile.contents = [(urwid.Text(f"Could not load partial {url}: {e}"), pile.options())]
            return

        if partial_destination_hash != self.loopback and not RNS.Transport.has_path(partial_destination_hash):
            if time.time() <= partial["pr_throttle"]: return
            else:
                partial["pr_throttle"] = time.time()+15
                RNS.log(f"Requesting path for partial: {partial_destination_hash} / {path}", RNS.LOG_EXTREME)
                RNS.Transport.request_path(partial_destination_hash)
                pr_time = time.time()+RNS.Transport.first_hop_timeout(partial_destination_hash)
                while not RNS.Transport.has_path(partial_destination_hash):
                    now = time.time()
                    if now > pr_time+self.timeout: return
                    time.sleep(0.25)

        for pid in self.page_partials:
            other_partial = self.page_partials[pid]
            if other_partial["link"]:
                existing_link = other_partial["link"]
                if existing_link.destination.hash == partial_destination_hash and existing_link.status == RNS.Link.ACTIVE:
                    RNS.log(f"Re-using existing link: {existing_link}", RNS.LOG_EXTREME)
                    partial["link"] = existing_link
                    break

        if not partial["link"] or partial["link"].status == RNS.Link.CLOSED:
            RNS.log(f"Establishing link for partial: {partial_destination_hash} / {path}", RNS.LOG_EXTREME)
            identity = RNS.Identity.recall(partial_destination_hash)
            destination = RNS.Destination(identity, RNS.Destination.OUT, RNS.Destination.SINGLE, self.app_name, self.aspects)
            
            def established(link):
                RNS.log(f"Link established for partial: {partial_destination_hash} / {path}", RNS.LOG_EXTREME)

            def closed(link):
                RNS.log(f"Link closed for partial: {partial_destination_hash} / {path}", RNS.LOG_EXTREME)
                partial["link"] = None
            
            partial["link"] = RNS.Link(destination, established_callback = established, closed_callback = closed)
            timeout = time.time()+self.timeout
            while partial["link"].status != RNS.Link.ACTIVE and time.time() < timeout: time.sleep(0.1)

        if partial["link"] and partial["link"].status == RNS.Link.ACTIVE and partial["request_id"] == None:
            RNS.log(f"Sending request for partial: {partial_destination_hash} / {path}", RNS.LOG_EXTREME)
            receipt = partial["link"].request(path, data=self.__get_partial_request_data(partial), response_callback = self.partial_received,
                                              failed_callback = self.partial_failed, progress_callback = self.partial_progressed)

            if receipt: partial["request_id"] = receipt.request_id
            else: RNS.log(f"Partial request failed", RNS.LOG_ERROR)

    def __get_partial_request_data(self, partial):
        request_data = None
        if partial["fields"] != None:
            link_data = partial["fields"]
            link_fields = []
            request_data = {}
            all_fields = True if "*" in link_data else False

            for e in link_data:
                if "=" in e:
                    c = e.split("=")
                    if len(c) == 2:
                        request_data["var_"+str(c[0])] = str(c[1])
                else:
                    link_fields.append(e)

                def recurse_down(w):
                    if isinstance(w, list):
                        for t in w:
                            recurse_down(t)
                    elif isinstance(w, tuple):
                        for t in w:
                            recurse_down(t)
                    elif hasattr(w, "contents"):
                        recurse_down(w.contents)
                    elif hasattr(w, "original_widget"):
                        recurse_down(w.original_widget)
                    elif hasattr(w, "_original_widget"):
                        recurse_down(w._original_widget)
                    else:
                        if hasattr(w, "field_name") and (all_fields or w.field_name in link_fields):
                            field_key = "field_" + w.field_name
                            if isinstance(w, urwid.Edit):
                                request_data[field_key] = w.edit_text
                            elif isinstance(w, urwid.RadioButton):
                                if w.state:
                                    user_data = getattr(w, "field_value", None)  
                                    if user_data is not None:
                                        request_data[field_key] = user_data
                            elif isinstance(w, urwid.CheckBox):
                                user_data = getattr(w, "field_value", "1")
                                if w.state:
                                    existing_value = request_data.get(field_key, '')
                                    if existing_value:
                                        # Concatenate the new value with the existing one
                                        request_data[field_key] = existing_value + ',' + user_data
                                    else:
                                        # Initialize the field with the current value
                                        request_data[field_key] = user_data
                                else:
                                    pass  # do nothing if checkbox is not check

            recurse_down(self.attr_maps)
            RNS.log("Including request data: "+str(request_data), RNS.LOG_DEBUG)

        return request_data

    def start_partial_updater(self):
        if not self.updater_running: self.update_partials()

    def handle_partial_updates(self, partial_ids):
        RNS.log(f"Update partials: {partial_ids}")
        def job():
            for pid in self.page_partials:
                try:
                    partial = self.page_partials[pid]
                    if partial["id"] in partial_ids:
                        partial["update_requested"] = time.time()
                        self.__load_partial(partial)
                except Exception as e: RNS.log(f"Error updating page partial: {e}", RNS.LOG_ERROR)

        threading.Thread(target=job, daemon=True).start()

    def update_partials(self, loop=None, user_data=None):
        with self.partial_updater_lock:
            def job():
                for pid in self.page_partials:
                    try:
                        partial = self.page_partials[pid]
                        if partial["failed"]: continue
                        if not partial["updated"] or (partial["refresh"] != None and time.time() > partial["updated"]+partial["refresh"]):
                            partial["update_requested"] = time.time()
                            self.__load_partial(partial)
                    except Exception as e: RNS.log(f"Error updating page partial: {e}", RNS.LOG_ERROR)

            threading.Thread(target=job, daemon=True).start()
            
            if len(self.page_partials) > 0:
                self.updater_running = True
                self.app.ui.loop.set_alarm_in(1, self.update_partials)
            else:
                self.updater_running = False

    def identify(self):
        if self.link != None:
            if self.link.status == RNS.Link.ACTIVE:
                self.link.identify(self.auth_identity)


    def disconnect(self):
        if self.link != None:
            self.link.teardown()
        
        self.request_data = None
        self.attr_maps = []
        self.status = Browser.DISCONECTED
        self.response_progress = 0
        self.response_speed = None
        self.progress_updated_at = None
        self.previous_progress = 0
        self.response_size = None
        self.response_transfer_size = None

        self.history = []
        self.history_ptr = 0
        self.history_inc = False
        self.history_dec = False

        self.update_display()


    def retrieve_url(self, url, request_data = None):
        self.previous_destination_hash = self.destination_hash
        self.previous_path = self.path

        destination_hash = None
        path = None

        components = url.split(":")
        if len(components) == 1:
            if len(components[0]) == (RNS.Reticulum.TRUNCATED_HASHLENGTH//8)*2:
                try: destination_hash = bytes.fromhex(components[0])
                except Exception as e: raise ValueError("Malformed URL")
                path = Browser.DEFAULT_PATH
            else: raise ValueError("Malformed URL")
        elif len(components) == 2:
            if len(components[0]) == (RNS.Reticulum.TRUNCATED_HASHLENGTH//8)*2:
                try: destination_hash = bytes.fromhex(components[0])
                except Exception as e: raise ValueError("Malformed URL")
                path = components[1]
                if len(path) == 0: path = Browser.DEFAULT_PATH
            else:
                if len(components[0]) == 0:
                    if self.destination_hash != None:
                        destination_hash = self.destination_hash
                        path = components[1]
                        if len(path) == 0: path = Browser.DEFAULT_PATH
                    else: raise ValueError("Malformed URL")
                else: raise ValueError("Malformed URL")
        else: raise ValueError("Malformed URL")

        if destination_hash != None and path != None:
            if path.startswith("/file/"):
                if destination_hash != self.loopback:
                    if destination_hash == self.destination_hash:
                        self.download_file(destination_hash, path)
                    else:
                        RNS.log("Cannot request file download from a node that is not currently connected.", RNS.LOG_ERROR)
                        RNS.log("The requested URL was: "+str(url), RNS.LOG_ERROR)
                else:
                    self.download_local_file(path)
            else:
                self.set_destination_hash(destination_hash)
                self.set_path(path)
                self.set_request_data(request_data)
                self.load_page()

    def set_destination_hash(self, destination_hash):
        if len(destination_hash) == RNS.Identity.TRUNCATED_HASHLENGTH//8:
            self.destination_hash = destination_hash
            return True
        else:
            return False


    def set_path(self, path):
        self.path = path

    def set_request_data(self, request_data):
        self.request_data = request_data

    def set_timeout(self, timeout):
        self.timeout = timeout

    def download_local_file(self, path):
        try:
            file_path = self.app.filespath+path.replace("/file", "", 1)
            if os.path.isfile(file_path):
                file_name = os.path.basename(file_path)
                file_destination = self.app.downloads_path+"/"+file_name

                counter = 0
                while os.path.isfile(file_destination):
                    counter += 1
                    file_destination = self.app.downloads_path+"/"+file_name+"."+str(counter)

                fs = open(file_path, "rb")
                fd = open(file_destination, "wb")
                fd.write(fs.read())
                fd.close()
                fs.close()

                self.saved_file_name = file_destination.replace(self.app.downloads_path+"/", "", 1)
                
                self.update_display()
            else:
                RNS.log("The requested local download file does not exist: "+str(file_path), RNS.LOG_ERROR)

            self.status = Browser.DONE
            self.response_progress = 0
            self.response_speed = None
            self.progress_updated_at = None
            self.previous_progress = 0
            
        except Exception as e:
            RNS.log("An error occurred while handling file response. The contained exception was: "+str(e), RNS.LOG_ERROR)

    def download_file(self, destination_hash, path):
        if self.link == None or self.link.destination.hash != self.destination_hash:
            if not RNS.Transport.has_path(self.destination_hash):
                self.status = Browser.NO_PATH
                self.update_display()

                RNS.Transport.request_path(self.destination_hash)
                self.status = Browser.PATH_REQUESTED
                self.update_display()

                pr_time = time.time()+RNS.Transport.first_hop_timeout(self.destination_hash)
                while not RNS.Transport.has_path(self.destination_hash):
                    now = time.time()
                    if now > pr_time+self.timeout:
                        self.request_timeout()
                        return

                    time.sleep(0.25)

            self.status = Browser.ESTABLISHING_LINK
            self.update_display()

            identity = RNS.Identity.recall(self.destination_hash)
            destination = RNS.Destination(
                identity,
                RNS.Destination.OUT,
                RNS.Destination.SINGLE,
                self.app_name,
                self.aspects
            )

            self.link = RNS.Link(destination, established_callback = self.link_established, closed_callback = self.link_closed)

            while self.status == Browser.ESTABLISHING_LINK:
                time.sleep(0.1)

            if self.status != Browser.LINK_ESTABLISHED:
                return

            self.update_display()

        if self.link != None and self.link.destination.hash == self.destination_hash:
            # Send the request
            self.status = Browser.REQUESTING
            self.response_progress = 0
            self.response_speed = None
            self.progress_updated_at = None
            self.previous_progress = 0
            self.response_size = None
            self.response_transfer_size = None
            self.saved_file_name = None

            self.update_display()
            receipt = self.link.request(
                path,
                data = None,
                response_callback = self.file_received,
                failed_callback = self.request_failed,
                progress_callback = self.response_progressed
            )

            if receipt:
                self.last_request_receipt = receipt
                self.last_request_id = receipt.request_id
                self.status = Browser.REQUEST_SENT
                self.update_display()
            else:
                self.link.teardown()

    def write_history(self):
        entry = [self.destination_hash, self.path]
        self.history.insert(self.history_ptr, entry)
        self.history_ptr += 1

        if len(self.history) > self.history_ptr:
            self.history = self.history[:self.history_ptr]

    def back(self):
        target_ptr = self.history_ptr-1
        if not self.history_inc and not self.history_dec:
            if target_ptr > 0:
                self.history_dec = True
                entry = self.history[target_ptr-1]
                url = RNS.hexrep(entry[0], delimit=False)+":"+entry[1]
                self.history_ptr = target_ptr
                self.retrieve_url(url)

    def forward(self):
        target_ptr = self.history_ptr+1
        if not self.history_inc and not self.history_dec:
            if target_ptr <= len(self.history):
                self.history_dec = True
                entry = self.history[target_ptr-1]
                url = RNS.hexrep(entry[0], delimit=False)+":"+entry[1]
                self.history_ptr = target_ptr
                self.retrieve_url(url)

    def reload(self):
        if not self.reloading and self.status == Browser.DONE:
            self.reloading = True
            self.uncache_page(self.current_url())
            self.load_page()

    def close_dialogs(self):
        options = self.delegate.columns.options(urwid.WEIGHT, self.delegate.right_area_width)
        self.delegate.columns.contents[1] = (self.display_widget, options)

    def url_dialog(self):
        e_url = UrlEdit(caption="URL : ", edit_text=self.current_url())

        def dismiss_dialog(sender):
            self.close_dialogs()

        def confirmed(sender):
            try:
                self.retrieve_url(e_url.get_edit_text().strip())
            except Exception as e:
                self.browser_footer = urwid.Text("Could not open link: "+str(e))
                self.frame.contents["footer"] = (self.browser_footer, self.frame.options())

            self.close_dialogs()

        dialog = UrlDialogLineBox(
            urwid.Pile([
                e_url,
                urwid.Columns([
                    (urwid.WEIGHT, 0.45, urwid.Button("Cancel", on_press=dismiss_dialog)),
                    (urwid.WEIGHT, 0.1, urwid.Text("")),
                    (urwid.WEIGHT, 0.45, urwid.Button("Go", on_press=confirmed)),
                ])
            ]), title="Enter URL"
        )
        e_url.confirmed = confirmed
        dialog.confirmed = confirmed
        dialog.delegate = self
        bottom = self.display_widget

        overlay = urwid.Overlay(
            dialog,
            bottom,
            align=urwid.CENTER,
            width=(urwid.RELATIVE, 65),
            valign=urwid.MIDDLE,
            height=urwid.PACK,
            left=2,
            right=2,
        )

        options = self.delegate.columns.options(urwid.WEIGHT, self.delegate.right_area_width)
        self.delegate.columns.contents[1] = (overlay, options)
        self.delegate.columns.focus_position = 1

    def save_node_dialog(self):
        if self.destination_hash != None:
            try:
                def dismiss_dialog(sender):
                    self.close_dialogs()

                display_name = RNS.Identity.recall_app_data(self.destination_hash)
                disp_str = ""
                if display_name != None:
                    display_name = display_name.decode("utf-8")
                    disp_str = " \""+display_name+"\""
                    
                def confirmed(sender):
                    node_entry = DirectoryEntry(self.destination_hash, display_name=display_name, hosts_node=True)
                    self.app.directory.remember(node_entry)
                    self.app.ui.main_display.sub_displays.network_display.directory_change_callback()

                    self.close_dialogs()

                dialog = UrlDialogLineBox(
                    urwid.Pile([
                        urwid.Text("Save connected node"+disp_str+" "+RNS.prettyhexrep(self.destination_hash)+" to Known Nodes?\n"),
                        urwid.Columns([
                            (urwid.WEIGHT, 0.45, urwid.Button("Cancel", on_press=dismiss_dialog)),
                            (urwid.WEIGHT, 0.1, urwid.Text("")),
                            (urwid.WEIGHT, 0.45, urwid.Button("Save", on_press=confirmed)),
                        ])
                    ]), title="Save Node"
                )

                dialog.confirmed = confirmed
                dialog.delegate = self
                bottom = self.display_widget

                overlay = urwid.Overlay(
                    dialog,
                    bottom,
                    align=urwid.CENTER,
                    width=(urwid.RELATIVE, 50),
                    valign=urwid.MIDDLE,
                    height=urwid.PACK,
                    left=2,
                    right=2,
                )

                options = self.delegate.columns.options(urwid.WEIGHT, self.delegate.right_area_width)
                self.delegate.columns.contents[1] = (overlay, options)
                self.delegate.columns.focus_position = 1

            except Exception as e:
                pass

    def load_page(self):
        if self.request_data == None:
            cached = self.get_cached(self.current_url())
        else:
            cached = None

        if cached:
            self.status = Browser.DONE
            self.page_data = cached
            self.markup = self.page_data.decode("utf-8")
            
            self.page_background_color = None
            bgpos = self.markup.find("#!bg=")
            if bgpos >= 0:
                endpos = self.markup.find("\n", bgpos)
                if endpos-(bgpos+5) == 3:
                    bg = self.markup[bgpos+5:endpos]
                    self.page_background_color = bg

            self.page_foreground_color = None
            fgpos = self.markup.find("#!fg=")
            if fgpos >= 0:
                endpos = self.markup.find("\n", fgpos)
                if endpos-(fgpos+5) == 3:
                    fg = self.markup[fgpos+5:endpos]
                    self.page_foreground_color = fg

            try: self.attr_maps = markup_to_attrmaps(strip_modifiers(self.markup), url_delegate=self, fg_color=self.page_foreground_color, bg_color=self.page_background_color)
            except Exception as e: self.attr_maps = [urwid.AttrMap(urwid.Text(f"Could not render page: {e}"), "inactive_text")]
            
            self.response_progress = 0
            self.response_speed = None
            self.progress_updated_at = None
            self.previous_progress = 0
            self.response_size = None
            self.response_transfer_size = None
            self.saved_file_name = None
            self.loaded_from_cache = True

            self.update_display()

            if not self.history_inc and not self.history_dec and not self.reloading:
                self.write_history()
            else:
                self.history_dec = False
                self.history_inc = False
                self.reloading = False

        else:
            if self.destination_hash != self.loopback:
                load_thread = threading.Thread(target=self.__load)
                load_thread.setDaemon(True)
                load_thread.start()
            else:
                RNS.log("Browser handling local page: "+str(self.path), RNS.LOG_DEBUG)
                page_path = self.app.pagespath+self.path.replace("/page", "", 1)

                page_data = b"The requested local page did not exist in the file system"
                if os.path.isfile(page_path):
                    if os.access(page_path, os.X_OK):
                        if self.request_data != None:
                            env_map = self.request_data
                        else:
                            env_map = {}
                            
                        if "PATH" in os.environ:
                            env_map["PATH"] = os.environ["PATH"]

                        generated = subprocess.run([page_path], stdout=subprocess.PIPE, env=env_map)
                        page_data = generated.stdout
                    else:
                        file = open(page_path, "rb")
                        page_data = file.read()
                        file.close()

                self.status = Browser.DONE
                self.page_data = page_data
                self.markup = self.page_data.decode("utf-8")
                
                self.page_background_color = None
                bgpos = self.markup.find("#!bg=")
                if bgpos >= 0:
                    endpos = self.markup.find("\n", bgpos)
                    if endpos-(bgpos+5) == 3:
                        bg = self.markup[bgpos+5:endpos]
                        self.page_background_color = bg

                self.page_foreground_color = None
                fgpos = self.markup.find("#!fg=")
                if fgpos >= 0:
                    endpos = self.markup.find("\n", fgpos)
                    if endpos-(fgpos+5) == 3:
                        fg = self.markup[fgpos+5:endpos]
                        self.page_foreground_color = fg

                try: self.attr_maps = markup_to_attrmaps(strip_modifiers(self.markup), url_delegate=self, fg_color=self.page_foreground_color, bg_color=self.page_background_color)
                except Exception as e: self.attr_maps = [urwid.AttrMap(urwid.Text(f"Could not render page: {e}"), "inactive_text")]
                
                self.response_progress = 0
                self.response_speed = None
                self.progress_updated_at = None
                self.previous_progress = 0
                self.response_size = None
                self.response_transfer_size = None
                self.saved_file_name = None
                self.loaded_from_cache = False

                self.update_display()

                if not self.history_inc and not self.history_dec and not self.reloading:
                    self.write_history()
                else:
                    self.history_dec = False
                    self.history_inc = False
                    self.reloading = False


    def __load(self):
        # If an established link exists, but it doesn't match the target
        # destination, we close and clear it.
        if self.link != None and (self.link.destination.hash != self.destination_hash or self.link.status != RNS.Link.ACTIVE):
            self.link.teardown()
            self.link = None

        # If no link to the destination exists, we create one.
        if self.link == None:
            if not RNS.Transport.has_path(self.destination_hash):
                self.status = Browser.NO_PATH
                self.update_display()

                RNS.Transport.request_path(self.destination_hash)
                self.status = Browser.PATH_REQUESTED
                self.update_display()

                pr_time = time.time()+RNS.Transport.first_hop_timeout(self.destination_hash)
                while not RNS.Transport.has_path(self.destination_hash):
                    now = time.time()
                    if now > pr_time+self.timeout:
                        self.request_timeout()
                        return

                    time.sleep(0.25)

            self.status = Browser.ESTABLISHING_LINK
            self.update_display()

            identity = RNS.Identity.recall(self.destination_hash)
            destination = RNS.Destination(
                identity,
                RNS.Destination.OUT,
                RNS.Destination.SINGLE,
                self.app_name,
                self.aspects
            )

            self.link = RNS.Link(destination, established_callback = self.link_established, closed_callback = self.link_closed)

            while self.status == Browser.ESTABLISHING_LINK:
                time.sleep(0.1)

            if self.status != Browser.LINK_ESTABLISHED:
                return

            self.update_display()

        # Send the request
        self.status = Browser.REQUESTING
        self.response_progress = 0
        self.response_speed = None
        self.progress_updated_at = None
        self.previous_progress = 0
        self.response_size = None
        self.response_transfer_size = None
        self.saved_file_name = None


        self.update_display()
        receipt = self.link.request(
            self.path,
            data = self.request_data,
            response_callback = self.response_received,
            failed_callback = self.request_failed,
            progress_callback = self.response_progressed
        )

        if receipt:
            self.last_request_receipt = receipt
            self.last_request_id = receipt.request_id
            self.status = Browser.REQUEST_SENT
            self.update_display()
        else:
            self.link.teardown()



    def link_established(self, link):
        self.status = Browser.LINK_ESTABLISHED

        if self.app.directory.should_identify_on_connect(self.destination_hash):
            RNS.log("Link established, identifying to remote system...", RNS.LOG_VERBOSE)
            self.link.identify(self.app.identity)


    def link_closed(self, link):
        if self.status == Browser.DISCONECTED or self.status == Browser.DONE:
            self.link = None
        elif self.status == Browser.ESTABLISHING_LINK:
            self.link_establishment_timeout()
        else:
            self.link = None
            self.status = Browser.REQUEST_FAILED
        self.update_display()

    def link_establishment_timeout(self):
        self.status = Browser.LINK_TIMEOUT
        self.response_progress = 0
        self.response_speed = None
        self.progress_updated_at = None
        self.previous_progress = 0
        self.response_size = None
        self.response_transfer_size = None
        self.link = None

        self.update_display()


    def response_received(self, request_receipt):
        try:
            self.status = Browser.DONE
            self.page_data = request_receipt.response
            self.markup = self.page_data.decode("utf-8")

            self.page_background_color = None
            bgpos = self.markup.find("#!bg=")
            if bgpos >= 0:
                endpos = self.markup.find("\n", bgpos)
                if endpos-(bgpos+5) == 3:
                    bg = self.markup[bgpos+5:endpos]
                    self.page_background_color = bg

            self.page_foreground_color = None
            fgpos = self.markup.find("#!fg=")
            if fgpos >= 0:
                endpos = self.markup.find("\n", fgpos)
                if endpos-(fgpos+5) == 3:
                    fg = self.markup[fgpos+5:endpos]
                    self.page_foreground_color = fg

            try: self.attr_maps = markup_to_attrmaps(strip_modifiers(self.markup), url_delegate=self, fg_color=self.page_foreground_color, bg_color=self.page_background_color)
            except Exception as e: self.attr_maps = [urwid.AttrMap(urwid.Text(f"Could not render page: {e}"), "inactive_text")]

            self.response_progress = 0
            self.response_speed = None
            self.progress_updated_at = None
            self.previous_progress = 0
            self.loaded_from_cache = False

            # Simple header handling. Should be expanded when more
            # header tags are added.
            cache_time = Browser.DEFAULT_CACHE_TIME
            if self.markup[:4] == "#!c=":
                endpos = self.markup.find("\n")
                if endpos == -1:
                    endpos = len(self.markup)
                cache_time = int(self.markup[4:endpos])

            self.update_display()

            if not self.history_inc and not self.history_dec and not self.reloading:
                self.write_history()
            else:
                self.history_dec = False
                self.history_inc = False
                self.reloading = False

            if cache_time == 0:
                RNS.log("Received page "+str(self.current_url())+", not caching due to header.", RNS.LOG_DEBUG)
            else:
                RNS.log("Received page "+str(self.current_url())+", caching for %.3f hours." % (cache_time/60/60), RNS.LOG_DEBUG)    
                self.cache_page(cache_time)

        except Exception as e:
            RNS.log("An error occurred while handling response. The contained exception was: "+str(e))

    def uncache_page(self, url):
        url_hash = self.url_hash(url)
        files = os.listdir(self.app.cachepath)
        for file in files:
            if file.startswith(url_hash):
                cachefile = self.app.cachepath+"/"+file
                os.unlink(cachefile)
                RNS.log("Removed "+str(cachefile)+" from cache.", RNS.LOG_DEBUG)

    def get_cached(self, url):
        url_hash = self.url_hash(url)
        files = os.listdir(self.app.cachepath)
        for file in files:
            cachepath = self.app.cachepath+"/"+file
            try:
                components = file.split("_")
                if len(components) == 2 and len(components[0]) == 64 and len(components[1]) > 0:
                    expires = float(components[1])

                    if time.time() > expires:
                        RNS.log("Removing stale cache entry "+str(file), RNS.LOG_DEBUG)
                        os.unlink(cachepath)
                    else:
                        if file.startswith(url_hash):
                            RNS.log("Found "+str(file)+" in cache.", RNS.LOG_DEBUG)
                            RNS.log("Returning cached page", RNS.LOG_DEBUG)
                            file = open(cachepath, "rb")
                            data = file.read()
                            file.close()
                            return data

            except Exception as e:
                RNS.log("Error while parsing cache entry "+str(cachepath)+", removing it.", RNS.LOG_ERROR)
                RNS.log("The contained exception was: "+str(e), RNS.LOG_ERROR)
                try:
                    os.unlink(cachepath)
                except Exception as e:
                    RNS.log("Additionally, an exception occurred while unlinking the entry: "+str(e), RNS.LOG_ERROR)
                    RNS.log("You will probably need to remove this entry manually by deleting the file: "+str(cachepath), RNS.LOG_ERROR)

                
        return None

    def clean_cache(self):
        files = os.listdir(self.app.cachepath)
        for file in files:
            cachepath = self.app.cachepath+"/"+file
            try:
                components = file.split("_")
                if len(components) == 2 and len(components[0]) == 64 and len(components[1]) > 0:
                    expires = float(components[1])

                    if time.time() > expires:
                        RNS.log("Removing stale cache entry "+str(file), RNS.LOG_DEBUG)
                        os.unlink(cachepath)

            except Exception as e:
                pass


    def cache_page(self, cache_time):
        url_hash = self.url_hash(self.current_url())
        if url_hash == None:
            RNS.log("Could not cache page "+str(self.current_url()), RNS.LOG_ERROR)
        else:
            try:
                self.uncache_page(self.current_url())
                cache_expires = time.time()+cache_time
                filename = url_hash+"_"+str(cache_expires)
                cachefile = self.app.cachepath+"/"+filename
                file = open(cachefile, "wb")
                file.write(self.page_data)
                file.close()
                RNS.log("Cached page "+str(self.current_url())+" to "+str(cachefile), RNS.LOG_DEBUG)

            except Exception as e:
                RNS.log("Could not write cache file for page "+str(self.current_url()), RNS.LOG_ERROR)
                RNS.log("The contained exception was: "+str(e), RNS.LOG_ERROR)


    def file_received(self, request_receipt):
        try:
            if type(request_receipt.response) == io.BufferedReader:
                if request_receipt.metadata != None:
                    file_name   = os.path.basename(request_receipt.metadata["name"].decode("utf-8"))
                    file_handle = request_receipt.response
                    file_destination = self.app.downloads_path+"/"+file_name

                    counter = 0
                    while os.path.isfile(file_destination):
                        counter += 1
                        file_destination = self.app.downloads_path+"/"+file_name+"."+str(counter)

                    shutil.move(file_handle.name, file_destination)

            else:
                file_name = request_receipt.response[0]
                file_data = request_receipt.response[1]
                file_destination_name = os.path.basename(file_name)
                file_destination = self.app.downloads_path+"/"+file_destination_name

                counter = 0
                while os.path.isfile(file_destination):
                    counter += 1
                    file_destination = self.app.downloads_path+"/"+file_destination_name+"."+str(counter)

                fh = open(file_destination, "wb")
                fh.write(file_data)
                fh.close()

                self.saved_file_name = file_destination.replace(self.app.downloads_path+"/", "", 1)
                    
            self.status = Browser.DONE
            self.response_progress = 0
            self.response_speed = None
            self.progress_updated_at = None
            self.previous_progress = 0

            self.update_display()
        except Exception as e:
            RNS.log("An error occurred while handling file response. The contained exception was: "+str(e), RNS.LOG_ERROR)

    
    def request_failed(self, request_receipt=None):
        if request_receipt != None:
            if request_receipt.request_id == self.last_request_id:
                self.status = Browser.REQUEST_FAILED
                self.response_progress = 0
                self.response_speed = None
                self.progress_updated_at = None
                self.previous_progress = 0
                self.response_size = None
                self.response_transfer_size = None

                self.update_display()
                if self.link != None:
                    try:
                        self.link.teardown()
                    except Exception as e:
                        pass
        else:
            self.status = Browser.REQUEST_FAILED
            self.response_progress = 0
            self.response_speed = None
            self.progress_updated_at = None
            self.previous_progress = 0
            self.response_size = None
            self.response_transfer_size = None

            self.update_display()
            if self.link != None:
                try:
                    self.link.teardown()
                except Exception as e:
                    pass


    def request_timeout(self, request_receipt=None):
        self.status = Browser.REQUEST_TIMEOUT
        self.response_progress = 0
        self.response_speed = None
        self.progress_updated_at = None
        self.previous_progress = 0
        self.response_size = None
        self.response_transfer_size = None

        self.update_display()
        if self.link != None:
            try:
                self.link.teardown()
            except Exception as e:
                pass


    def response_progressed(self, request_receipt):
        self.response_progress      = request_receipt.progress
        self.response_time          = request_receipt.get_response_time()
        self.response_size          = request_receipt.response_size
        self.response_transfer_size = request_receipt.response_transfer_size
        
        now = time.time()
        if self.progress_updated_at == None: self.progress_updated_at = now
        if now > self.progress_updated_at+1:
            td = now - self.progress_updated_at
            pd = self.response_progress - self.previous_progress
            bd = pd*self.response_size
            self.response_speed = (bd/td)*8
            self.previous_progress = self.response_progress
            self.progress_updated_at = now

        self.update_display()


    def status_text(self):
        if self.status == Browser.DONE and self.response_transfer_size != None:
            if self.response_time != None:
                response_time_str = "{:.2f}".format(self.response_time)
            else:
                response_time_str = "None"

            stats_string = "  "+self.g["page"]+size_str(self.response_size)
            stats_string += "   "+self.g["arrow_d"]+size_str(self.response_transfer_size)+" in "+response_time_str
            stats_string += "s   "+self.g["speed"]+size_str(self.response_transfer_size/self.response_time, suffix="b")+"/s"
        elif self.loaded_from_cache:
            stats_string = " (cached)"
        else:
            stats_string = ""

        if self.status == Browser.NO_PATH:
            return "No path to destination known"
        elif self.status == Browser.PATH_REQUESTED:
            return "Path requested, waiting for path..."
        elif self.status == Browser.ESTABLISHING_LINK:
            return "Establishing link..."
        elif self.status == Browser.LINK_TIMEOUT:
            return "Link establishment timed out"
        elif self.status == Browser.LINK_ESTABLISHED:
            return "Link established"
        elif self.status == Browser.REQUESTING:
            return "Sending request..."
        elif self.status == Browser.REQUEST_SENT:
            return "Request sent, awaiting response..."
        elif self.status == Browser.REQUEST_FAILED:
            return "Request failed"
        elif self.status == Browser.REQUEST_TIMEOUT:
            return "Request timed out"
        elif self.status == Browser.RECEIVING_RESPONSE:
            return "Receiving response..."
        elif self.status == Browser.DONE:
            if self.saved_file_name == None:
                return "Done"+stats_string
            else:
                return "Saved "+str(self.saved_file_name)+stats_string
        elif self.status == Browser.DISCONECTED:
            return "Disconnected"
        else:
            return "Browser Status Unknown"


class ResponseProgressBar(urwid.ProgressBar):
    def __init__(self, empty, full, current=None, done=None, satt=None, owner=None):
        super().__init__(empty, full, current=current, done=done, satt=satt)
        self.owner = owner

    def get_text(self):
        if self.owner.response_speed: speed_str = " "+RNS.prettyspeed(self.owner.response_speed)
        else: speed_str = ""
        return "Receiving response "+super().get_text().replace(" %", "%")+speed_str

# A convenience function for printing a human-
# readable file size
def size_str(num, suffix='B'):
    units = ['','K','M','G','T','P','E','Z']
    last_unit = 'Y'

    if suffix == 'b':
        num *= 8
        units = ['','K','M','G','T','P','E','Z']
        last_unit = 'Y'

    for unit in units:
        if abs(num) < 1000.0:
            if unit == "":
                return "%.0f%s%s" % (num, unit, suffix)
            else:
                return "%.2f%s%s" % (num, unit, suffix)
        num /= 1000.0

    return "%.2f%s%s" % (num, last_unit, suffix)

class UrlDialogLineBox(urwid.LineBox):
    def keypress(self, size, key):
        if key == "esc":
            self.delegate.close_dialogs()
        else:
            return super(UrlDialogLineBox, self).keypress(size, key)

class UrlEdit(urwid.Edit):
    def keypress(self, size, key):
        if key == "enter":
            self.confirmed(self)
        else:
            return super(UrlEdit, self).keypress(size, key)
