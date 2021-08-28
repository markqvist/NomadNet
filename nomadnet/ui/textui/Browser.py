import RNS
import time
import urwid
import nomadnet
import threading
from .MicronParser import markup_to_attrmaps
from nomadnet.vendor.Scrollable import *

# TODO: REMOVE
import os

class BrowserFrame(urwid.Frame):
    def keypress(self, size, key):
        if key == "ctrl w":
            self.delegate.disconnect()
        elif self.get_focus() == "body":
            return super(BrowserFrame, self).keypress(size, key)
            # if key == "up" and self.delegate.messagelist.top_is_visible:
            #     nomadnet.NomadNetworkApp.get_shared_instance().ui.main_display.frame.set_focus("header")
            # elif key == "down" and self.delegate.messagelist.bottom_is_visible:
            #     self.set_focus("footer")
            # else:
            #     return super(ConversationFrame, self).keypress(size, key)
        else:
            return super(BrowserFrame, self).keypress(size, key)

class Browser:
    DEFAULT_PATH       = "/page/index.mu"
    DEFAULT_TIMEOUT    = 5

    NO_PATH            = 0x00
    PATH_REQUESTED     = 0x01
    ESTABLISHING_LINK  = 0x02
    LINK_ESTABLISHED   = 0x03
    REQUESTING         = 0x04
    REQUEST_SENT       = 0x05
    REQUEST_FAILED     = 0x06
    REQUEST_TIMEOUT    = 0x07
    RECEIVING_RESPONSE = 0x08
    DONE               = 0xFF
    DISCONECTED        = 0xFE

    def __init__(self, app, app_name, aspects, destination_hash = None, path = None, auth_identity = None, delegate = None):
        self.app = app
        self.g = self.app.ui.glyphs
        self.delegate = delegate
        self.app_name = app_name
        self.aspects = aspects
        self.destination_hash = destination_hash
        self.path = path
        self.timeout = Browser.DEFAULT_TIMEOUT
        self.last_keypress = None

        self.link = None
        self.status = Browser.DISCONECTED
        self.response_progress = 0
        self.response_size = None
        self.response_transfer_size = None
        self.page_data = None
        self.displayed_page_data = None
        self.auth_identity = auth_identity
        self.display_widget = None
        self.frame = None
        self.attr_maps = []
        self.build_display()

        if self.path == None:
            self.path = Browser.DEFAULT_PATH

        if self.destination_hash != None:
            self.load_page()

    def current_url(self):
        if self.destination_hash == None:
            return ""
        else:
            if self.path == None:
                path = ""
            else:
                path = self.path
            return RNS.hexrep(self.destination_hash, delimit=False)+":"+path

    def handle_link(self, link_target):
        RNS.log("Browser handling link to: "+str(link_target), RNS.LOG_DEBUG)
        try:
            self.retrieve_url(link_target)
        except Exception as e:
            self.browser_footer = urwid.Text("Could not open link: "+str(e))
            self.frame.contents["footer"] = (self.browser_footer, self.frame.options())


    def micron_released_focus(self):
        if self.delegate != None:
            self.delegate.focus_lists()

    def build_display(self):
        self.browser_header = urwid.Text("")
        self.browser_footer = urwid.Text("")

        self.browser_body = urwid.Filler(urwid.Text("Disconnected\n"+self.g["arrow_l"]+"  "+self.g["arrow_r"], align="center"), "middle")

        self.frame = BrowserFrame(self.browser_body, header=self.browser_header, footer=self.browser_footer)
        self.frame.delegate = self
        self.display_widget = urwid.AttrMap(urwid.LineBox(self.frame, title="Remote Node"), "inactive_text")

    def make_status_widget(self):
        if self.response_progress > 0:
            pb = ResponseProgressBar("progress_empty" , "progress_full", current=self.response_progress, done=1.0, satt=None)
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
            ("weight", 0.5, urwid.Text(" ")),
            (8, urwid.Button("Back", on_press=back_action)),
            ("weight", 0.5, urwid.Text(" "))
        ])

        if len(self.attr_maps) > 0:
            pile = urwid.Pile([
                    urwid.Text("!\n\n"+self.status_text()+"\n", align="center"),
                    columns
            ])
        else:
            pile = urwid.Pile([
                    urwid.Text("!\n\n"+self.status_text(), align="center")
            ])

        return urwid.Filler(pile, "middle")
    
    def update_display(self):
        if self.status == Browser.DISCONECTED:
            self.display_widget.set_attr_map({None: "inactive_text"})
            self.browser_body = urwid.Filler(urwid.Text("Disconnected\n"+self.g["arrow_l"]+"  "+self.g["arrow_r"], align="center"), "middle")
            self.browser_footer = urwid.Text("")
            self.browser_header = urwid.Text("")
        else:
            self.display_widget.set_attr_map({None: "body_text"})
            self.browser_header = self.make_control_widget()

            if self.status == Browser.DONE:
                self.browser_footer = self.make_status_widget()
                self.update_page_display()
            
            elif self.status <= Browser.REQUEST_SENT:
                if len(self.attr_maps) == 0:
                    self.browser_body = urwid.Filler(urwid.Text("Retrieving\n["+self.current_url()+"]", align="center"), "middle")

                self.browser_footer = self.make_status_widget()
            
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
        self.browser_body = urwid.AttrMap(ScrollBar(Scrollable(pile), thumb_char="\u2503", trough_char=" "), "scrollbar")

    def identify(self):
        if self.link != None:
            if self.link.status == RNS.Link.ACTIVE:
                self.link.identify(self.auth_identity)


    def disconnect(self):
        if self.link != None:
            self.link.teardown()
        
        self.attr_maps = []
        self.status = Browser.DISCONECTED
        self.response_progress = 0
        self.response_size = None
        self.response_transfer_size = None

        self.update_display()


    def retrieve_url(self, url):
        self.previous_destination_hash = self.destination_hash
        self.previous_path = self.path

        destination_hash = None
        path = None

        components = url.split(":")
        if len(components) == 1:
            if len(components[0]) == 20:
                try:
                    destination_hash = bytes.fromhex(components[0])
                except Exception as e:
                    raise ValueError("Malformed URL")
                path = Browser.DEFAULT_PATH
            else:
                raise ValueError("Malformed URL")
        elif len(components) == 2:
            if len(components[0]) == 20:
                try:
                    destination_hash = bytes.fromhex(components[0])
                except Exception as e:
                    raise ValueError("Malformed URL")
                path = components[1]
                if len(path) == 0:
                    path = Browser.DEFAULT_PATH
            else:
                if len(components[0]) == 0:
                    if self.destination_hash != None:
                        destination_hash = self.destination_hash
                        path = components[1]
                        if len(path) == 0:
                            path = Browser.DEFAULT_PATH
                    else:
                        raise ValueError("Malformed URL")
                else:
                        raise ValueError("Malformed URL")
        else:
            raise ValueError("Malformed URL")

        if destination_hash != None and path != None:
            self.set_destination_hash(destination_hash)
            self.set_path(path)
            self.load_page()

    def set_destination_hash(self, destination_hash):
        if len(destination_hash) == RNS.Identity.TRUNCATED_HASHLENGTH//8:
            self.destination_hash = destination_hash
            return True
        else:
            return False


    def set_path(self, path):
        self.path = path


    def set_timeout(self, timeout):
        self.timeout = timeout


    def load_page(self):
        load_thread = threading.Thread(target=self.__load)
        load_thread.setDaemon(True)
        load_thread.start()


    def __load(self):
        # If an established link exists, but it doesn't match the target
        # destination, we close and clear it.
        if self.link != None and self.link.destination.hash != self.destination_hash:
            self.link.close()
            self.link = None

        # If no link to the destination exists, we create one.
        if self.link == None:
            if not RNS.Transport.has_path(self.destination_hash):
                self.status = Browser.NO_PATH
                self.update_display()

                RNS.Transport.request_path(self.destination_hash)
                self.status = Browser.PATH_REQUESTED
                self.update_display()

                pr_time = time.time()
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

            l_time = time.time()
            while not self.status == Browser.LINK_ESTABLISHED:
                now = time.time()
                if now > l_time+self.timeout:
                    self.request_timeout()
                    return

                time.sleep(0.25)

            self.update_display()

        # Send the request
        self.status = Browser.REQUESTING
        self.response_progress = 0
        self.response_size = None
        self.response_transfer_size = None

        self.update_display()
        receipt = self.link.request(
            self.path,
            data = None,
            response_callback = self.response_received,
            failed_callback = self.request_failed,
            progress_callback = self.response_progressed,
            timeout = self.timeout
        )

        self.last_request_receipt = receipt
        self.last_request_id = receipt.request_id

        self.status = Browser.REQUEST_SENT
        self.update_display()


    def link_established(self, link):
        self.status = Browser.LINK_ESTABLISHED


    def link_closed(self, link):
        if self.status == Browser.DISCONECTED or self.status == Browser.DONE:
            self.link = None
        else:
            self.link = None
            self.status = Browser.REQUEST_FAILED
        self.update_display()


    def response_received(self, request_receipt):
        try:
            self.status = Browser.DONE
            self.page_data = request_receipt.response
            self.markup = self.page_data.decode("utf-8")
            self.attr_maps = markup_to_attrmaps(self.markup, url_delegate=self)
            self.response_progress = 0

            self.update_display()
        except Exception as e:
            RNS.log("An error occurred while handling response. The contained exception was: "+str(e))

    
    def request_failed(self, request_receipt=None):
        if request_receipt != None:
            if request_receipt.request_id == self.last_request_id:
                self.status = Browser.REQUEST_FAILED
                self.response_progress = 0
                self.response_size = None
                self.response_transfer_size = None

                self.update_display()
        else:
            self.status = Browser.REQUEST_FAILED
            self.response_progress = 0
            self.response_size = None
            self.response_transfer_size = None

            self.update_display()


    def request_timeout(self, request_receipt=None):
        self.status = Browser.REQUEST_TIMEOUT
        self.response_progress = 0
        self.response_size = None
        self.response_transfer_size = None

        self.update_display()


    def response_progressed(self, request_receipt):
        self.response_progress      = request_receipt.progress
        self.response_time          = request_receipt.response_time()
        self.response_size          = request_receipt.response_size
        self.response_transfer_size = request_receipt.response_transfer_size
        self.update_display()


    def status_text(self):
        if self.response_transfer_size != None:
            response_time_str = "{:.2f}".format(self.response_time)
            stats_string = "  "+self.g["page"]+size_str(self.response_size)
            stats_string += "   "+self.g["arrow_d"]+size_str(self.response_transfer_size)+" in "+response_time_str
            stats_string += "s   "+self.g["speed"]+size_str(self.response_transfer_size/self.response_time, suffix="b")+"/s"
        else:
            stats_string = ""

        if self.status == Browser.NO_PATH:
            return "No path to destination known"
        elif self.status == Browser.PATH_REQUESTED:
            return "Path requested, waiting for path..."
        elif self.status == Browser.ESTABLISHING_LINK:
            return "Establishing link..."
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
            return "Done"+stats_string
        elif self.status == Browser.DISCONECTED:
            return "Disconnected"
        else:
            return "Browser Status Unknown"


class ResponseProgressBar(urwid.ProgressBar):
    def get_text(self):
        return "Receiving response "+super().get_text()

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