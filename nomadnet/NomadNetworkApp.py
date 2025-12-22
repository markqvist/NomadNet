import os
import io
import sys
import time
import shlex
import atexit
import threading
import traceback
import subprocess
import contextlib

import RNS
import LXMF
import nomadnet

from nomadnet.Directory import DirectoryEntry
from datetime import datetime

import RNS.vendor.umsgpack as msgpack

from ._version import __version__
from RNS.vendor.configobj import ConfigObj

class NomadNetworkApp:
    time_format      = "%Y-%m-%d %H:%M:%S"
    _shared_instance = None

    userdir = os.path.expanduser("~")
    if os.path.isdir("/etc/nomadnetwork") and os.path.isfile("/etc/nomadnetwork/config"):
        configdir = "/etc/nomadnetwork"
    elif os.path.isdir(userdir+"/.config/nomadnetwork") and os.path.isfile(userdir+"/.config/nomadnetwork/config"):
        configdir = userdir+"/.config/nomadnetwork"
    else:
        configdir = userdir+"/.nomadnetwork"

    START_ANNOUNCE_DELAY = 3

    def exit_handler(self):
        self.should_run_jobs = False

        RNS.log("Saving directory...", RNS.LOG_VERBOSE)
        self.directory.save_to_disk()

        if hasattr(self.ui, "restore_ixon"):
            if self.ui.restore_ixon:
                try:
                    os.system("stty ixon")

                except Exception as e:
                    RNS.log("Could not restore flow control sequences. The contained exception was: "+str(e), RNS.LOG_WARNING)

        if hasattr(self.ui, "restore_palette"):
            if self.ui.restore_palette:
                try:
                    self.ui.screen.write("\x1b]104\x07")

                except Exception as e:
                    RNS.log("Could not restore terminal color palette. The contained exception was: "+str(e), RNS.LOG_WARNING)

        RNS.log("Nomad Network Client exiting now", RNS.LOG_VERBOSE)

    def exception_handler(self, e_type, e_value, e_traceback):
        RNS.log("An unhandled exception occurred, the details of which will be dumped below", RNS.LOG_ERROR)
        RNS.log("Type  : "+str(e_type), RNS.LOG_ERROR)
        RNS.log("Value : "+str(e_value), RNS.LOG_ERROR)
        t_string = ""
        for line in traceback.format_tb(e_traceback):
            t_string += line
        RNS.log("Trace : \n"+t_string, RNS.LOG_ERROR)

        if issubclass(e_type, KeyboardInterrupt):
            sys.__excepthook__(e_type, e_value, e_traceback)

    def __init__(self, configdir = None, rnsconfigdir = None, daemon = False, force_console = False):
        self.version       = __version__
        self.enable_client = False
        self.enable_node   = False
        self.identity      = None

        self.uimode        = None

        if configdir == None:
            self.configdir = NomadNetworkApp.configdir
        else:
            self.configdir = configdir

        if force_console:
            self.force_console_log = True
        else:
            self.force_console_log = False

        if NomadNetworkApp._shared_instance == None:
            NomadNetworkApp._shared_instance = self

        self.rns = RNS.Reticulum(configdir = rnsconfigdir)

        self.configpath        = self.configdir+"/config"
        self.ignoredpath       = self.configdir+"/ignored"
        self.logfilepath       = self.configdir+"/logfile"
        self.errorfilepath     = self.configdir+"/errors"
        self.pnannouncedpath   = self.configdir+"/pnannounced"
        self.storagepath       = self.configdir+"/storage"
        self.identitypath      = self.configdir+"/storage/identity"
        self.cachepath         = self.configdir+"/storage/cache"
        self.resourcepath      = self.configdir+"/storage/resources"
        self.conversationpath  = self.configdir+"/storage/conversations"
        self.directorypath     = self.configdir+"/storage/directory"
        self.peersettingspath  = self.configdir+"/storage/peersettings"
        self.tmpfilespath      = self.configdir+"/storage/tmp"

        self.pagespath         = self.configdir+"/storage/pages"
        self.filespath         = self.configdir+"/storage/files"
        self.cachepath         = self.configdir+"/storage/cache"
        self.examplespath      = self.configdir+"/examples"

        self.downloads_path    = os.path.expanduser("~/Downloads")

        self.firstrun               = False
        self.should_run_jobs        = True
        self.job_interval           = 5
        self.defer_jobs             = 90
        self.page_refresh_interval  = 0
        self.file_refresh_interval  = 0

        self.static_peers            = []
        self.peer_announce_at_start  = True
        self.try_propagation_on_fail = True
        self.disable_propagation     = True
        self.notify_on_new_message   = True

        self.lxmf_max_propagation_size = None
        self.lxmf_max_sync_size        = None
        self.lxmf_max_incoming_size    = None
        self.node_propagation_cost     = LXMF.LXMRouter.PROPAGATION_COST

        self.periodic_lxmf_sync = True
        self.lxmf_sync_interval = 360*60
        self.lxmf_sync_limit    = 8
        self.compact_stream     = False
        
        self.required_stamp_cost   = None
        self.accept_invalid_stamps = False


        if not os.path.isdir(self.storagepath):
            os.makedirs(self.storagepath)

        if not os.path.isdir(self.cachepath):
            os.makedirs(self.cachepath)

        if not os.path.isdir(self.resourcepath):
            os.makedirs(self.resourcepath)

        if not os.path.isdir(self.conversationpath):
            os.makedirs(self.conversationpath)

        if not os.path.isdir(self.pagespath):
            os.makedirs(self.pagespath)

        if not os.path.isdir(self.filespath):
            os.makedirs(self.filespath)

        if not os.path.isdir(self.cachepath):
            os.makedirs(self.cachepath)

        if not os.path.isdir(self.tmpfilespath):
            os.makedirs(self.tmpfilespath)
        else:
            self.clear_tmp_dir()

        if os.path.isfile(self.configpath):
            try:
                self.config = ConfigObj(self.configpath)
                try:
                    self.applyConfig()
                except Exception as e:
                    RNS.log("The configuration file is invalid. The contained exception was: "+str(e), RNS.LOG_ERROR)
                    nomadnet.panic()

                RNS.log("Configuration loaded from "+self.configpath)
            except Exception as e:
                RNS.log("Could not parse the configuration at "+self.configpath, RNS.LOG_ERROR)
                RNS.log("Check your configuration file for errors!", RNS.LOG_ERROR)
                nomadnet.panic()
        else:
            if not os.path.isdir(self.examplespath):
                try:
                    import shutil
                    examplespath = os.path.join(os.path.dirname(__file__), "examples")
                    shutil.copytree(examplespath, self.examplespath, ignore=shutil.ignore_patterns("__pycache__"))
                
                except Exception as e:
                    RNS.log("Could not copy examples into the "+self.examplespath+" directory.", RNS.LOG_ERROR)
                    RNS.log("The contained exception was: "+str(e), RNS.LOG_ERROR)
            
            RNS.log("Could not load config file, creating default configuration file...")
            self.createDefaultConfig()
            self.firstrun = True

        if os.path.isfile(self.identitypath):
            try:
                self.identity = RNS.Identity.from_file(self.identitypath)
                if self.identity != None:
                    RNS.log("Loaded Primary Identity %s from %s" % (str(self.identity), self.identitypath))
                else:
                    RNS.log("Could not load the Primary Identity from "+self.identitypath, RNS.LOG_ERROR)
                    nomadnet.panic()
            except Exception as e:
                RNS.log("Could not load the Primary Identity from "+self.identitypath, RNS.LOG_ERROR)
                RNS.log("The contained exception was: %s" % (str(e)), RNS.LOG_ERROR)
                nomadnet.panic()
        else:
            try:
                RNS.log("No Primary Identity file found, creating new...")
                self.identity = RNS.Identity()
                self.identity.to_file(self.identitypath)
                RNS.log("Created new Primary Identity %s" % (str(self.identity)))
            except Exception as e:
                RNS.log("Could not create and save a new Primary Identity", RNS.LOG_ERROR)
                RNS.log("The contained exception was: %s" % (str(e)), RNS.LOG_ERROR)
                nomadnet.panic()

        if os.path.isfile(self.peersettingspath):
            try:
                file = open(self.peersettingspath, "rb")
                self.peer_settings = msgpack.unpackb(file.read())
                file.close()

                if not "node_last_announce" in self.peer_settings:
                    self.peer_settings["node_last_announce"] = None

                if not "propagation_node" in self.peer_settings:
                    self.peer_settings["propagation_node"] = None

                if not "last_lxmf_sync" in self.peer_settings:
                    self.peer_settings["last_lxmf_sync"] = 0

                if not "node_connects" in self.peer_settings:
                    self.peer_settings["node_connects"] = 0

                if not "served_page_requests" in self.peer_settings:
                    self.peer_settings["served_page_requests"] = 0

                if not "served_file_requests" in self.peer_settings:
                    self.peer_settings["served_file_requests"] = 0

            except Exception as e:
                RNS.logdest = RNS.LOG_STDOUT
                RNS.log(f"Could not load local peer settings from {self.peersettingspath}", RNS.LOG_ERROR)
                RNS.log(f"The contained exception was: {e}", RNS.LOG_ERROR)
                RNS.log(f"This likely means that the peer settings file has become corrupt.", RNS.LOG_ERROR)
                RNS.log(f"You can try deleting the file at {self.peersettingspath} and restarting nomadnet.", RNS.LOG_ERROR)
                nomadnet.panic()
        else:
            try:
                RNS.log("No peer settings file found, creating new...")
                self.peer_settings = {
                    "display_name": "Anonymous Peer",
                    "announce_interval": None,
                    "last_announce": None,
                    "node_last_announce": None,
                    "propagation_node": None,
                    "last_lxmf_sync": 0,
                    "node_connects": 0,
                    "served_page_requests": 0,
                    "served_file_requests": 0
                }
                self.save_peer_settings()
                RNS.log("Created new peer settings file")
            except Exception as e:
                RNS.log("Could not create and save a new peer settings file", RNS.LOG_ERROR)
                RNS.log("The contained exception was: %s" % (str(e)), RNS.LOG_ERROR)
                nomadnet.panic()

        self.ignored_list = []
        if os.path.isfile(self.ignoredpath):
            try:
                fh = open(self.ignoredpath, "rb")
                ignored_input = fh.read()
                fh.close()

                ignored_hash_strs = ignored_input.splitlines()

                for hash_str in ignored_hash_strs:
                    if len(hash_str) == RNS.Identity.TRUNCATED_HASHLENGTH//8*2:
                        try:
                            ignored_hash = bytes.fromhex(hash_str.decode("utf-8"))
                            self.ignored_list.append(ignored_hash)

                        except Exception as e:
                            RNS.log("Could not decode RNS Identity hash from: "+str(hash_str), RNS.LOG_DEBUG)
                            RNS.log("The contained exception was: "+str(e), RNS.LOG_DEBUG)

            except Exception as e:
                RNS.log("Error while loading list of ignored destinations: "+str(e), RNS.LOG_ERROR)

        self.directory = nomadnet.Directory(self)

        static_peers = []
        for static_peer in self.static_peers:
            try:
                dh = bytes.fromhex(static_peer)
                if len(dh) != RNS.Reticulum.TRUNCATED_HASHLENGTH//8:
                    raise ValueError("Invalid destination length")
                static_peers.append(dh)
            except Exception as e:
                RNS.log(f"Could not decode static peer destination hash {static_peer}: {e}", RNS.LOG_ERROR)

        self.message_router = LXMF.LXMRouter(
            identity = self.identity, storagepath = self.storagepath, autopeer = True,
            propagation_limit = self.lxmf_max_propagation_size, sync_limit = self.lxmf_max_sync_size, delivery_limit = self.lxmf_max_incoming_size,
            max_peers = self.max_peers, static_peers = static_peers, propagation_cost=self.node_propagation_cost
        )

        self.message_router.register_delivery_callback(self.lxmf_delivery)

        for destination_hash in self.ignored_list:
            self.message_router.ignore_destination(destination_hash)

        self.lxmf_destination = self.message_router.register_delivery_identity(self.identity, display_name=self.peer_settings["display_name"], stamp_cost=self.required_stamp_cost)
        if not self.accept_invalid_stamps:
            self.message_router.enforce_stamps()

        RNS.Identity.remember(
            packet_hash=None,
            destination_hash=self.lxmf_destination.hash,
            public_key=self.identity.get_public_key(),
            app_data=None
        )

        RNS.log("LXMF Router ready to receive on: "+RNS.prettyhexrep(self.lxmf_destination.hash))

        if self.enable_node:
            self.message_router.set_message_storage_limit(megabytes=self.message_storage_limit)
            for dest_str in self.prioritised_lxmf_destinations:
                try:
                    dest_hash = bytes.fromhex(dest_str)
                    if len(dest_hash) == RNS.Reticulum.TRUNCATED_HASHLENGTH//8:
                        self.message_router.prioritise(dest_hash)

                except Exception as e:
                    RNS.log("Cannot prioritise "+str(dest_str)+", it is not a valid destination hash", RNS.LOG_ERROR)

            if self.disable_propagation:
                if os.path.isfile(self.pnannouncedpath):
                    try:
                        RNS.log("Sending indication to peered LXMF Propagation Node that this node is no longer participating", RNS.LOG_DEBUG)
                        self.message_router.disable_propagation()
                        os.unlink(self.pnannouncedpath)
                    except Exception as e:
                        RNS.log("An error ocurred while indicating that this LXMF Propagation Node is no longer participating. The contained exception was: "+str(e), RNS.LOG_ERROR)
            else:
                self.message_router.enable_propagation()
                try:
                    with open(self.pnannouncedpath, "wb") as pnf:
                        pnf.write(msgpack.packb(time.time()))
                        pnf.close()

                except Exception as e:
                    RNS.log("An error ocurred while writing Propagation Node announce timestamp. The contained exception was: "+str(e), RNS.LOG_ERROR)

            if not self.disable_propagation:
                RNS.log("LXMF Propagation Node started on: "+RNS.prettyhexrep(self.message_router.propagation_destination.hash))
                
            self.node = nomadnet.Node(self)
        else:
            self.node = None
            if os.path.isfile(self.pnannouncedpath):
                try:
                    RNS.log("Sending indication to peered LXMF Propagation Node that this node is no longer participating", RNS.LOG_DEBUG)
                    self.message_router.disable_propagation()
                    os.unlink(self.pnannouncedpath)
                except Exception as e:
                    RNS.log("An error ocurred while indicating that this LXMF Propagation Node is no longer participating. The contained exception was: "+str(e), RNS.LOG_ERROR)

        RNS.Transport.register_announce_handler(nomadnet.Conversation)
        RNS.Transport.register_announce_handler(nomadnet.Directory)

        self.autoselect_propagation_node()

        if self.peer_announce_at_start:
            def delayed_announce():
                time.sleep(NomadNetworkApp.START_ANNOUNCE_DELAY)
                self.announce_now()

            da_thread = threading.Thread(target=delayed_announce)
            da_thread.setDaemon(True)
            da_thread.start()

        atexit.register(self.exit_handler)
        sys.excepthook = self.exception_handler

        job_thread = threading.Thread(target=self.__jobs)
        job_thread.setDaemon(True)
        job_thread.start()

        # Override UI choice from config on --daemon switch
        if daemon:
            self.uimode = nomadnet.ui.UI_NONE

        # This stderr redirect is needed to stop urwid
        # from spewing KeyErrors to the console and thus,
        # messing up the UI. A pull request to fix the
        # bug in urwid was submitted, but until it is
        # merged, this hack will mitigate it.
        strio = io.StringIO()
        with contextlib.redirect_stderr(strio):
            nomadnet.ui.spawn(self.uimode)

        if strio.tell() > 0:
            try:
                strio.seek(0)
                err_file = open(self.errorfilepath, "w")
                err_file.write(strio.read())
                err_file.close()

            except Exception as e:
                RNS.log("Could not write stderr output to error log file at "+str(self.errorfilepath)+".", RNS.LOG_ERROR)
                RNS.log("The contained exception was: "+str(e), RNS.LOG_ERROR)


    def __jobs(self):
        RNS.log("Deferring scheduled jobs for "+str(self.defer_jobs)+" seconds...", RNS.LOG_DEBUG)
        time.sleep(self.defer_jobs)

        RNS.log("Starting job scheduler now", RNS.LOG_DEBUG)
        while self.should_run_jobs:
            now = time.time()
            
            if now > self.peer_settings["last_lxmf_sync"] + self.lxmf_sync_interval:
                RNS.log("Initiating automatic LXMF sync", RNS.LOG_VERBOSE)
                self.request_lxmf_sync(limit=self.lxmf_sync_limit)

            time.sleep(self.job_interval)

    def set_display_name(self, display_name):
        self.peer_settings["display_name"] = display_name
        self.lxmf_destination.display_name = display_name
        self.save_peer_settings()

    def get_display_name(self):
        return self.peer_settings["display_name"]

    def get_display_name_bytes(self):
        return self.peer_settings["display_name"].encode("utf-8")

    def get_sync_status(self):
        if self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_IDLE:
            return "Idle"
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_PATH_REQUESTED:
            return "Path requested"
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_LINK_ESTABLISHING:
            return "Establishing link"
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_LINK_ESTABLISHED:
            return "Link established"
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_REQUEST_SENT:
            return "Sync request sent"
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_RECEIVING:
            return "Receiving messages"
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_RESPONSE_RECEIVED:
            return "Messages received"
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_NO_PATH:
            return "No path to node"
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_LINK_FAILED:
            return "Link establisment failed"
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_TRANSFER_FAILED:
            return "Sync request failed"
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_NO_IDENTITY_RCVD:
            return "Remote got no identity"
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_NO_ACCESS:
            return "Node rejected request"
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_FAILED:
            return "Sync failed"
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_COMPLETE:
            new_msgs = self.message_router.propagation_transfer_last_result
            if new_msgs == 0:
                return "Done, no new messages"
            else:
                return "Downloaded "+str(new_msgs)+" new messages"
        else:
            return "Unknown"

    def sync_status_show_percent(self):
        if self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_IDLE:
            return False
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_PATH_REQUESTED:
            return False
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_LINK_ESTABLISHING:
            return False
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_LINK_ESTABLISHED:
            return False
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_REQUEST_SENT:
            return False
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_RECEIVING:
            return True
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_RESPONSE_RECEIVED:
            return True
        elif self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_COMPLETE:
            return False
        else:
            return False

    def get_sync_progress(self):
        return self.message_router.propagation_transfer_progress

    def request_lxmf_sync(self, limit = None):
        if self.message_router.propagation_transfer_state == LXMF.LXMRouter.PR_IDLE or self.message_router.propagation_transfer_state >= LXMF.LXMRouter.PR_COMPLETE:
            self.peer_settings["last_lxmf_sync"] = time.time()
            self.save_peer_settings()
            self.message_router.request_messages_from_propagation_node(self.identity, max_messages = limit)

    def cancel_lxmf_sync(self):
        if self.message_router.propagation_transfer_state != LXMF.LXMRouter.PR_IDLE:
            self.message_router.cancel_propagation_node_requests()

    def announce_now(self):
        self.message_router.set_inbound_stamp_cost(self.lxmf_destination.hash, self.required_stamp_cost)
        self.lxmf_destination.display_name = self.peer_settings["display_name"]
        self.message_router.announce(self.lxmf_destination.hash)
        self.peer_settings["last_announce"] = time.time()
        self.save_peer_settings()

    def autoselect_propagation_node(self):
        selected_node = None

        if "propagation_node" in self.peer_settings and self.peer_settings["propagation_node"] != None:
            selected_node = self.peer_settings["propagation_node"]
        else:
            nodes = self.directory.known_nodes()
            trusted_nodes = []

            best_hops = RNS.Transport.PATHFINDER_M+1

            for node in nodes:
                if node.trust_level == DirectoryEntry.TRUSTED:
                    hops = RNS.Transport.hops_to(node.source_hash)

                    if hops < best_hops:
                        best_hops = hops
                        selected_node = node.source_hash

        if selected_node == None:
            RNS.log("Could not autoselect a propagation node! LXMF propagation will not be available until a trusted node announces on the network, or a propagation node is manually selected.", RNS.LOG_WARNING)
        else:
            pn_name_str = ""
            RNS.log("Selecting "+RNS.prettyhexrep(selected_node)+pn_name_str+" as default LXMF propagation node", RNS.LOG_DEBUG)
            self.message_router.set_outbound_propagation_node(selected_node)

    def get_user_selected_propagation_node(self):
        if "propagation_node" in self.peer_settings:
            return self.peer_settings["propagation_node"]
        else:
            return None

    def set_user_selected_propagation_node(self, node_hash):
        self.peer_settings["propagation_node"] = node_hash
        self.save_peer_settings()
        self.autoselect_propagation_node()
    
    def get_default_propagation_node(self):
        return self.message_router.get_outbound_propagation_node()

    def save_peer_settings(self):
        tmp_path = f"{self.peersettingspath}.tmp"
        with open(tmp_path, "wb") as file: file.write(msgpack.packb(self.peer_settings))
        os.replace(tmp_path, self.peersettingspath)

    def lxmf_delivery(self, message):
        time_string = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(message.timestamp))
        signature_string = "Signature is invalid, reason undetermined"
        if message.signature_validated:
            signature_string = "Validated"
        else:
            if message.unverified_reason == LXMF.LXMessage.SIGNATURE_INVALID:
                signature_string = "Invalid signature"
            if message.unverified_reason == LXMF.LXMessage.SOURCE_UNKNOWN:
                signature_string = "Cannot verify, source is unknown"

        nomadnet.Conversation.ingest(message, self)

        if self.notify_on_new_message:
            self.notify_message_recieved()

        if self.should_print(message):
            self.print_message(message)

    def should_print(self, message):
        if self.print_messages:
            if self.print_all_messages:
                return True
            
            else:
                source_hash_text = RNS.hexrep(message.source_hash, delimit=False)

                if self.print_trusted_messages:
                    trust_level = self.directory.trust_level(message.source_hash)
                    if trust_level == DirectoryEntry.TRUSTED:
                        return True

                if type(self.allowed_message_print_destinations) is list:
                    if source_hash_text in self.allowed_message_print_destinations:
                        return True

        return False

    def print_file(self, filename):
        print_command = self.print_command+" "+filename

        try:
            return_code = subprocess.call(shlex.split(print_command), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        except Exception as e:
            RNS.log("An error occurred while executing print command: "+str(print_command), RNS.LOG_ERROR)
            RNS.log("The contained exception was: "+str(e), RNS.LOG_ERROR)
            return False

        if return_code == 0:
            RNS.log("Successfully printed "+str(filename)+" using print command: "+print_command, RNS.LOG_DEBUG)
            return True

        else:
            RNS.log("Printing "+str(filename)+" failed using print command: "+print_command, RNS.LOG_DEBUG)
            return False


    def print_message(self, message, received = None):
        try:
            template = self.printing_template_msg

            if received == None:
                received = time.time()

            g = self.ui.glyphs
            
            m_rtime = datetime.fromtimestamp(message.timestamp)
            stime = m_rtime.strftime(self.time_format)

            message_time = datetime.fromtimestamp(received)
            rtime = message_time.strftime(self.time_format)

            display_name = self.directory.simplest_display_str(message.source_hash)
            title = message.title_as_string()
            if title == "":
                title = "None"

            output = template.format(
                origin=display_name,
                stime=stime,
                rtime=rtime,
                mtitle=title,
                mbody=message.content_as_string(),
            )

            filename = "/tmp/"+RNS.hexrep(RNS.Identity.full_hash(output.encode("utf-8")), delimit=False)
            with open(filename, "wb") as f:
                f.write(output.encode("utf-8"))
                f.close()

            self.print_file(filename)

            os.unlink(filename)

        except Exception as e:
            RNS.log("Error while printing incoming LXMF message. The contained exception was: "+str(e))

    def conversations(self):
        return nomadnet.Conversation.conversation_list(self)

    def has_unread_conversations(self):
        if len(nomadnet.Conversation.unread_conversations) > 0:
            return True
        else:
            return False

    def conversation_is_unread(self, source_hash):
        if bytes.fromhex(source_hash) in nomadnet.Conversation.unread_conversations:
            return True
        else:
            return False

    def mark_conversation_read(self, source_hash):
        if bytes.fromhex(source_hash) in nomadnet.Conversation.unread_conversations:
            nomadnet.Conversation.unread_conversations.pop(bytes.fromhex(source_hash))
            if os.path.isfile(self.conversationpath + "/" + source_hash + "/unread"):
                os.unlink(self.conversationpath + "/" + source_hash + "/unread")

    def notify_message_recieved(self):
        if self.uimode == nomadnet.ui.UI_TEXT:
            sys.stdout.write("\a")
            sys.stdout.flush()

    def clear_tmp_dir(self):
        if os.path.isdir(self.tmpfilespath):
            for file in os.listdir(self.tmpfilespath):
                fpath = self.tmpfilespath+"/"+file
                os.unlink(fpath)

    def createDefaultConfig(self):
        self.config = ConfigObj(__default_nomadnet_config__)
        self.config.filename = self.configpath
        
        if not os.path.isdir(self.configdir):
            os.makedirs(self.configdir)
        self.config.write()
        self.applyConfig()


    def applyConfig(self):
        if "logging" in self.config:
            for option in self.config["logging"]:
                value = self.config["logging"][option]
                if option == "loglevel":
                    RNS.loglevel = int(value)
                    if RNS.loglevel < 0:
                        RNS.loglevel = 0
                    if RNS.loglevel > 7:
                        RNS.loglevel = 7
                if option == "destination":
                    if value.lower() == "file" and not self.force_console_log:
                        RNS.logdest = RNS.LOG_FILE
                        if "logfile" in self.config["logging"]:
                            self.logfilepath = self.config["logging"]["logfile"]
                        RNS.logfile = self.logfilepath
                    else:
                        RNS.logdest = RNS.LOG_STDOUT

        if "client" in self.config:
            for option in self.config["client"]:
                value = self.config["client"][option]

                if option == "enable_client":
                    value = self.config["client"].as_bool(option)
                    self.enable_client = value

                if option == "downloads_path":
                    value = self.config["client"]["downloads_path"]
                    self.downloads_path = os.path.expanduser(value)

                if option == "announce_at_start":
                    value = self.config["client"].as_bool(option)
                    self.peer_announce_at_start = value

                if option == "try_propagation_on_send_fail":
                    value = self.config["client"].as_bool(option)
                    self.try_propagation_on_fail = value

                if option == "periodic_lxmf_sync":
                    value = self.config["client"].as_bool(option)
                    self.periodic_lxmf_sync = value

                if option == "lxmf_sync_interval":
                    value = self.config["client"].as_int(option)*60

                    if value >= 60:
                        self.lxmf_sync_interval = value

                if option == "lxmf_sync_limit":
                    value = self.config["client"].as_int(option)    

                    if value > 0:
                        self.lxmf_sync_limit = value
                    else:
                        self.lxmf_sync_limit = None

                if option == "required_stamp_cost":
                    value = self.config["client"][option]
                    if value.lower() == "none":
                        self.required_stamp_cost = None
                    else:
                        value = self.config["client"].as_int(option)

                        if value > 0:
                            if value > 255:
                                value = 255
                            self.required_stamp_cost = value
                        else:
                            self.required_stamp_cost = None

                if option == "accept_invalid_stamps":
                    value = self.config["client"].as_bool(option)
                    self.accept_invalid_stamps = value

                if option == "max_accepted_size":
                    value = self.config["client"].as_float(option)    

                    if value > 0:
                        self.lxmf_max_incoming_size = value
                    else:
                        self.lxmf_max_incoming_size = 500

                if option == "compact_announce_stream":
                    value = self.config["client"].as_bool(option)
                    self.compact_stream = value

                if option == "notify_on_new_message":
                    value = self.config["client"].as_bool(option)
                    self.notify_on_new_message = value

                if option == "user_interface":
                    value = value.lower()
                    if value == "none":
                        self.uimode = nomadnet.ui.UI_NONE
                    if value == "menu":
                        self.uimode = nomadnet.ui.UI_MENU
                    if value == "text":
                        self.uimode = nomadnet.ui.UI_TEXT
                        if "textui" in self.config:
                            if not "intro_time" in self.config["textui"]:
                                self.config["textui"]["intro_time"] = 1
                            else:
                                self.config["textui"]["intro_time"] = self.config["textui"].as_float("intro_time")

                            if not "intro_text" in self.config["textui"]:
                                self.config["textui"]["intro_text"] = "Nomad Network"

                            if not "editor" in self.config["textui"]:
                                self.config["textui"]["editor"] = "nano"

                            if not "glyphs" in self.config["textui"]:
                                self.config["textui"]["glyphs"] = "unicode"

                            if not "mouse_enabled" in self.config["textui"]:
                                self.config["textui"]["mouse_enabled"] = True
                            else:
                                self.config["textui"]["mouse_enabled"] = self.config["textui"].as_bool("mouse_enabled")

                            if not "hide_guide" in self.config["textui"]:
                                self.config["textui"]["hide_guide"] = False
                            else:
                                self.config["textui"]["hide_guide"] = self.config["textui"].as_bool("hide_guide")

                            if not "animation_interval" in self.config["textui"]:
                                self.config["textui"]["animation_interval"] = 1
                            else:
                                self.config["textui"]["animation_interval"] = self.config["textui"].as_int("animation_interval")

                            if not "colormode" in self.config["textui"]:
                                self.config["textui"]["colormode"] = nomadnet.ui.COLORMODE_16
                            else:
                                if self.config["textui"]["colormode"].lower() == "monochrome":
                                    self.config["textui"]["colormode"] = nomadnet.ui.TextUI.COLORMODE_MONO
                                elif self.config["textui"]["colormode"].lower() == "16":
                                    self.config["textui"]["colormode"] = nomadnet.ui.TextUI.COLORMODE_16
                                elif self.config["textui"]["colormode"].lower() == "88":
                                    self.config["textui"]["colormode"] = nomadnet.ui.TextUI.COLORMODE_88
                                elif self.config["textui"]["colormode"].lower() == "256":
                                    self.config["textui"]["colormode"] = nomadnet.ui.TextUI.COLORMODE_256
                                elif self.config["textui"]["colormode"].lower() == "24bit":
                                    self.config["textui"]["colormode"] = nomadnet.ui.TextUI.COLORMODE_TRUE
                                else:
                                    raise ValueError("The selected Text UI color mode is invalid")

                            if not "theme" in self.config["textui"]:
                                self.config["textui"]["theme"] = nomadnet.ui.TextUI.THEME_DARK
                            else:
                                if self.config["textui"]["theme"].lower() == "dark":
                                    self.config["textui"]["theme"] = nomadnet.ui.TextUI.THEME_DARK
                                elif self.config["textui"]["theme"].lower() == "light":
                                    self.config["textui"]["theme"] = nomadnet.ui.TextUI.THEME_LIGHT
                                else:
                                    raise ValueError("The selected Text UI theme is invalid")
                        else:
                            raise KeyError("Text UI selected in configuration file, but no [textui] section found")
                    if value == "graphical":
                        self.uimode = nomadnet.ui.UI_GRAPHICAL
                    if value == "web":
                        self.uimode = nomadnet.ui.UI_WEB

        if "node" in self.config:
            if not "enable_node" in self.config["node"]:
                self.enable_node = False
            else:
                self.enable_node = self.config["node"].as_bool("enable_node")

            if not "node_name" in self.config["node"]:
                self.node_name = None
            else:
                value = self.config["node"]["node_name"]
                if value.lower() == "none":
                    self.node_name = None
                else:
                    self.node_name = self.config["node"]["node_name"]

            if not "disable_propagation" in self.config["node"]:
                self.disable_propagation = True
            else:
                self.disable_propagation = self.config["node"].as_bool("disable_propagation")

            if not "max_transfer_size" in self.config["node"]:
                self.lxmf_max_propagation_size = 256
            else:
                value = self.config["node"].as_float("max_transfer_size")
                if value < 1:
                    value = 1
                self.lxmf_max_propagation_size = value

            if not "max_sync_size" in self.config["node"]:
                self.lxmf_max_sync_size = 256*40
            else:
                value = self.config["node"].as_float("max_sync_size")
                if value < self.lxmf_max_propagation_size:
                    value = self.lxmf_max_propagation_size
                self.lxmf_max_sync_size = value

            if not "announce_at_start" in self.config["node"]:
                self.node_announce_at_start = False
            else:
                value = self.config["node"].as_bool("announce_at_start")
                self.node_announce_at_start = value

            if not "announce_interval" in self.config["node"]:
                self.node_announce_interval = 720
            else:
                value = self.config["node"].as_int("announce_interval")
                if value < 1:
                    value = 1
                self.node_announce_interval = value

            if not "propagation_cost" in self.config["node"]:
                self.node_propagation_cost = 16
            else:
                value = self.config["node"].as_int("propagation_cost")
                if value < 13: value = 13
                self.node_propagation_cost = value
                
            if "pages_path" in self.config["node"]:
                self.pagespath = self.config["node"]["pages_path"]
                
            if not "page_refresh_interval" in self.config["node"]:
                self.page_refresh_interval = 0
            else:
                value = self.config["node"].as_int("page_refresh_interval")
                if value < 0:
                    value = 0
                self.page_refresh_interval = value
                

            if "files_path" in self.config["node"]:
                self.filespath = self.config["node"]["files_path"]
                
            if not "file_refresh_interval" in self.config["node"]:
                self.file_refresh_interval = 0
            else:
                value = self.config["node"].as_int("file_refresh_interval")
                if value < 0:
                    value = 0
                self.file_refresh_interval = value
                

            if "prioritise_destinations" in self.config["node"]:
                self.prioritised_lxmf_destinations = self.config["node"].as_list("prioritise_destinations")
            else:
                self.prioritised_lxmf_destinations = []

            if "static_peers" in self.config["node"]:
                self.static_peers = self.config["node"].as_list("static_peers")
            else:
                self.static_peers = []
                
            if not "max_peers" in self.config["node"]:
                self.max_peers = None
            else:
                value = self.config["node"].as_int("max_peers")
                if value < 0:
                    value = 0
                self.max_peers = value

            if not "message_storage_limit" in self.config["node"]:
                self.message_storage_limit = 2000
            else:
                value = self.config["node"].as_float("message_storage_limit")
                if value < 0.005:
                    value = 0.005
                self.message_storage_limit = value

        self.print_command = "lp"
        self.print_messages = False
        self.print_all_messages = False
        self.print_trusted_messages = False
        if "printing" in self.config:
            if not "print_messages" in self.config["printing"]:
                self.print_messages = False
            else:
                self.print_messages = self.config["printing"].as_bool("print_messages")

                if "print_command" in self.config["printing"]:
                    self.print_command = self.config["printing"]["print_command"]

                if self.print_messages:
                    if not "print_from" in self.config["printing"]:
                        self.allowed_message_print_destinations = None
                    else:
                        if type(self.config["printing"]["print_from"]) == str:
                            self.allowed_message_print_destinations = []
                            if self.config["printing"]["print_from"].lower() == "everywhere":
                                self.print_all_messages = True

                            if self.config["printing"]["print_from"].lower() == "trusted":
                                
                                self.print_all_messages = False
                                self.print_trusted_messages = True

                            if len(self.config["printing"]["print_from"]) == (RNS.Identity.TRUNCATED_HASHLENGTH//8)*2:
                                self.allowed_message_print_destinations.append(self.config["printing"]["print_from"])
                        
                        if type(self.config["printing"]["print_from"]) == list:
                                self.allowed_message_print_destinations =  self.config["printing"].as_list("print_from")
                                for allowed_entry in self.allowed_message_print_destinations:
                                    if allowed_entry.lower() == "trusted":
                                        self.print_trusted_messages = True


                    if not "message_template" in self.config["printing"]:
                        self.printing_template_msg = __printing_template_msg__
                    else:
                        mt_path = os.path.expanduser(self.config["printing"]["message_template"])
                        if os.path.isfile(mt_path):
                            template_file = open(mt_path, "rb")
                            self.printing_template_msg = template_file.read().decode("utf-8")
                        else:
                            template_file = open(mt_path, "wb")
                            template_file.write(__printing_template_msg__.encode("utf-8"))
                            self.printing_template_msg = __printing_template_msg__

              
    @staticmethod
    def get_shared_instance():
        if NomadNetworkApp._shared_instance != None:
            return NomadNetworkApp._shared_instance
        else:
            raise UnboundLocalError("No Nomad Network applications have been instantiated yet")


    def quit(self):
        RNS.log("Nomad Network Client shutting down...")
        os._exit(0)


# Default configuration file:
__default_nomadnet_config__ = '''# This is the default Nomad Network config file.
# You should probably edit it to suit your needs and use-case,

[logging]
# Valid log levels are 0 through 7:
#   0: Log only critical information
#   1: Log errors and lower log levels
#   2: Log warnings and lower log levels
#   3: Log notices and lower log levels
#   4: Log info and lower (this is the default)
#   5: Verbose logging
#   6: Debug logging
#   7: Extreme logging

loglevel = 4
destination = file

[client]

enable_client = yes
user_interface = text
downloads_path = ~/Downloads
notify_on_new_message = yes

# By default, the peer is announced at startup
# to let other peers reach it immediately.
announce_at_start = yes

# By default, the client will try to deliver a
# message via the LXMF propagation network, if
# a direct delivery to the recipient is not
# possible.
try_propagation_on_send_fail = yes

# Nomadnet will periodically sync messages from
# LXMF propagation nodes by default, if any are
# present. You can disable this if you want to
# only sync when manually initiated.
periodic_lxmf_sync = yes

# The sync interval in minutes. This value is
# equal to 6 hours (360 minutes) by default.
lxmf_sync_interval = 360

# By default, automatic LXMF syncs will only
# download 8 messages at a time. You can change
# this number, or set the option to 0 to disable
# the limit, and download everything every time.
lxmf_sync_limit = 8

# You can specify a required stamp cost for
# inbound messages to be accepted. Specifying
# a stamp cost will require untrusted senders
# that message you to include a cryptographic
# stamp in their messages. Performing this
# operation takes the sender an amount of time
# proportional to the stamp cost. As a rough
# estimate, a stamp cost of 8 will take less
# than a second to compute, and a stamp cost
# of 20 could take several minutes, even on
# a fast computer.
required_stamp_cost = None

# You can signal stamp requirements to senders,
# but still accept messages with invalid stamps
# by setting this option to True.
accept_invalid_stamps = False

# The maximum accepted unpacked size for mes-
# sages received directly from other peers,
# specified in kilobytes. Messages larger than
# this will be rejected before the transfer
# begins.
max_accepted_size = 500

# The announce stream will only show one entry
# per destination or node by default. You can
# change this to show as many announces as have
# been received, for every destination.
compact_announce_stream = yes

[textui]

# Amount of time to show intro screen
intro_time = 1

# You can specify the display theme.
# theme = light
theme = dark

# Specify the number of colors to use
# valid colormodes are:
# monochrome, 16, 88, 256 and 24bit
#
# The default is a conservative 256 colors.
# If your terminal does not support this,
# you can lower it. Some terminals support
# 24 bit color.

# colormode = monochrome
# colormode = 16
# colormode = 88
colormode = 256
# colormode = 24bit

# By default, unicode glyphs are used. If
# you have a Nerd Font installed, you can
# enable this for a better user interface.
# You can also enable plain text glyphs if
# your terminal doesn't support unicode.

# glyphs = plain
glyphs = unicode
# glyphs = nerdfont

# You can specify whether mouse events
# should be considered as input to the
# application. On by default.
mouse_enabled = True

# What editor to use for editing text.
editor = nano

# If you don't want the Guide section to
# show up in the menu, you can disable it.
hide_guide = no

[node]

# Whether to enable node hosting
enable_node = no

# The node name will be visible to other
# peers on the network, and included in
# announces.
node_name = None

# Automatic announce interval in minutes.
# 6 hours by default.
announce_interval = 360

# Whether to announce when the node starts.
announce_at_start = Yes

# When Nomad Network is hosting a page-serving
# node, it can also act as an LXMF propagation
# node. This is a convenient feature that lets
# you easily set up and run a propagation node
# on the network, but it is not as fully
# featured as using the lxmd program to host a
# propagation node. For complete control and
# flexibility, use lxmd to run a PN. For a
# small local system or network, the built-in
# PN functionality will suffice for most cases.
#
# If there is already a large amount of
# propagation nodes on the network, or you
# simply want to run a pageserving-only node,
# you should disable running a propagation node.
# Due to lots of propagation nodes being
# available, this is currently the default.

disable_propagation = Yes

# For clients and other propagation nodes
# delivering messages via this node, you can
# configure the minimum required propagation
# stamp costs. All messages delivered to the
# propagation node network must have a valid
# propagation stamp, or they will be rejected.
# Clients automatically detect the stamp cost
# for the node they are delivering to, and
# compute a corresponding stamp before trying
# to deliver the message to the propagation
# node.
#
# Propagation stamps are easier to verify in
# large batches, and therefore also somewhat
# easier to compute for the senders. As such,
# a reasonable propagation stamp cost should
# be a bit higher than the normal peer-to-peer
# stamp costs.
#
# Propagation stamps does not incur any extra
# load for propagation nodes processing them,
# since they are only required to verify that
# they are correct, and only the generation
# is computationally costly. Setting a sensible
# propagation stamp cost (and periodically
# checking the average network consensus) helps
# keep spam and misuse out of the propagation
# node network.

propagation_cost = 16

# The maximum amount of storage to use for
# the LXMF Propagation Node message store,
# specified in megabytes. When this limit
# is reached, LXMF will periodically remove
# messages in its message store. By default,
# LXMF prioritises keeping messages that are
# new and small. Large and old messages will
# be removed first. This setting is optional
# and defaults to 2 gigabytes.

# message_storage_limit = 2000

# The maximum accepted transfer size per in-
# coming propagation message, in kilobytes.
# This sets the upper limit for the size of
# single messages accepted onto this node.

max_transfer_size = 256

# The maximum accepted transfer size per in-
# coming propagation node sync.
#
# If a node wants to propagate a larger number
# of messages to this node, than what can fit
# within this limit, it will prioritise sending
# the smallest messages first, and try again
# with any remaining messages at a later point.

max_sync_size = 10240

# You can tell the LXMF message router to
# prioritise storage for one or more
# destinations. If the message store reaches
# the specified limit, LXMF will prioritise
# keeping messages for destinations specified
# with this option. This setting is optional,
# and generally you do not need to use it.

# prioritise_destinations = 41d20c727598a3fbbdf9106133a3a0ed, d924b81822ca24e68e2effea99bcb8cf

# You can configure the maximum number of other
# propagation nodes that this node will peer
# with automatically. The default is 20.

# max_peers = 20

# You can configure a list of static propagation
# node peers, that this node will always be
# peered with, by specifying a list of
# destination hashes.

# static_peers = e17f833c4ddf8890dd3a79a6fea8161d, 5a2d0029b6e5ec87020abaea0d746da4

# You can specify the interval in minutes for
# rescanning the hosted pages path. By default,
# this option is disabled, and the pages path
# will only be scanned on startup.

# page_refresh_interval = 0

# You can specify the interval in minutes for
# rescanning the hosted files path. By default,
# this option is disabled, and the files path
# will only be scanned on startup.

# file_refresh_interval = 0

[printing]

# You can configure Nomad Network to print
# various kinds of information and messages.

# Printing messages is disabled by default

print_messages = No

# You can configure a custom template for
# message printing. If you uncomment this
# option, set a path to the template and
# restart Nomad Network, a default template
# will be created that you can edit.

# message_template = ~/.nomadnetwork/print_template_msg.txt

# You can configure Nomad Network to only
# print messages from trusted destinations.

# print_from = trusted

# Or specify the source LXMF addresses that
# will automatically have messages printed
# on arrival.

# print_from = 76fe5751a56067d1e84eef3e88eab85b, 0e70b5848eb57c13154154feaeeb89b7

# Or allow printing from anywhere, if you
# are feeling brave and adventurous.

# print_from = everywhere

# You can configure the printing command.
# This will use the default CUPS printer on
# your system.

print_command = lp

# You can specify what printer to use
# print_command = lp -d [PRINTER_NAME]

# Or specify more advanced options. This
# example works well for small thermal-
# roll printers:
# print_command = lp -d [PRINTER_NAME] -o cpi=16 -o lpi=8

# This one is more suitable for full-sheet
# printers. It will print a QR code at the center of any media
# your printer will accept, print in portrait mode, and move the message to
# the top of the print queue:
# print_command = lp -d [PRINTER_NAME] -o job-priority=100 -o media=Custom.75x75mm -o orientation-requested=3

# But you can modify the size to fit your needs.
# The custom media option accepts millimeters, centimeters, and
# inches in a width by length format like so:
# -o media=Custom.[WIDTH]x[LENGTH][mm,cm,in]
#
# The job priority option accepts 1-100, though you can remove it
# entirely if you aren't concerned with a print queue:
# -o job-priority=[1-100]
#
# Finally, the orientation option allows for 90 degree rotations beginning with 3, so:
# -o orientation-requested=4 (landscape, 90 degrees)
# -o orientation-requested=5 (reverse portrait, 180 degrees)
#
# Here is the full command with the recommended customizable variables:
# print_command = lp -d [PRINTER_NAME] -o job-priority=[N] -o media=[MEDIA_SIZE] -o orientation-requested=[N] -o sides=one-sided

# For example, here's a configuration for USB thermal printer that uses the POS-58 PPD driver
# with rolls 47.98x209.9mm in size:
# print_command = lp -d [PRINTER_NAME] -o job-priority=100 -o media=custom_47.98x209.9mm_47.98x209.9mm -o sides=one-sided

'''.splitlines()

__printing_template_msg__ = """
---------------------------
From: {origin}
Sent: {stime}
Rcvd: {rtime}
Title: {mtitle}

{mbody}
---------------------------
"""
