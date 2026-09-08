import os
import sys

import RNS
import time
import threading
import subprocess
import RNS.vendor.umsgpack as msgpack

class Node:
    JOB_INTERVAL = 5
    SETTINGS_FLUSH_INTERVAL = 60
    START_ANNOUNCE_DELAY = 6

    def __init__(self, app):
        RNS.log("Nomad Network Node starting...", RNS.LOG_VERBOSE)
        self.app = app
        self.identity = self.app.identity
        self.destination = RNS.Destination(self.identity, RNS.Destination.IN, RNS.Destination.SINGLE, "nomadnetwork", "node")
        self.last_announce = time.time()
        self.last_file_refresh = time.time()
        self.last_page_refresh = time.time()
        self.announce_interval = self.app.node_announce_interval
        self.page_refresh_interval = self.app.page_refresh_interval
        self.file_refresh_interval = self.app.file_refresh_interval
        self.job_interval = Node.JOB_INTERVAL
        self.should_run_jobs = True
        self.settings_dirty = False
        self.last_settings_flush = time.time()
        self.app_data = None
        self.name = self.app.node_name

        self.register_pages()
        self.register_files()
        self.register_media()

        self.destination.set_link_established_callback(self.peer_connected)

        if self.name == None:
            self.name = self.app.peer_settings["display_name"]+"'s Node"

        RNS.log("Node \""+self.name+"\" ready for incoming connections on "+RNS.prettyhexrep(self.destination.hash), RNS.LOG_VERBOSE)

        if self.app.node_announce_at_start:
            def delayed_announce():
                time.sleep(Node.START_ANNOUNCE_DELAY)
                self.announce()

            da_thread = threading.Thread(target=delayed_announce)
            da_thread.setDaemon(True)
            da_thread.start()

        job_thread = threading.Thread(target=self.__jobs)
        job_thread.setDaemon(True)
        job_thread.start()


    def register_pages(self):
        # TODO: Deregister previously registered pages
        # that no longer exist.
        self.servedpages = []
        self.scan_pages(self.app.pagespath)

        if not self.app.pagespath+"index.mu" in self.servedpages:
            self.destination.register_request_handler(
                "/page/index.mu",
                response_generator = self.serve_default_index,
                allow = RNS.Destination.ALLOW_ALL)

        for page in self.servedpages:
            request_path = "/page"+page.replace(self.app.pagespath, "")
            self.destination.register_request_handler(
                request_path,
                response_generator = self.serve_page,
                allow = RNS.Destination.ALLOW_ALL)

    def register_media(self):
        self.destination.register_request_handler("/media", response_generator = self.serve_media,
                                                  allow = RNS.Destination.ALLOW_ALL)

    def register_files(self):
        # TODO: Deregister previously registered files
        # that no longer exist.
        self.servedfiles = []
        self.scan_files(self.app.filespath)

        for file in self.servedfiles:
            request_path = "/file"+file.replace(self.app.filespath, "")
            self.destination.register_request_handler(
                request_path,
                response_generator = self.serve_file,
                allow = RNS.Destination.ALLOW_ALL,
                auto_compress = 32_000_000)

    def scan_pages(self, base_path):
        files = [file for file in os.listdir(base_path) if os.path.isfile(os.path.join(base_path, file)) and file[:1] != "."]
        directories = [file for file in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, file)) and file[:1] != "."]

        for file in files:
            if not file.endswith(".allowed"):
                self.servedpages.append(base_path+"/"+file)

        for directory in directories:
            self.scan_pages(base_path+"/"+directory)

    def scan_files(self, base_path):
        files = [file for file in os.listdir(base_path) if os.path.isfile(os.path.join(base_path, file)) and file[:1] != "."]
        directories = [file for file in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, file)) and file[:1] != "."]

        for file in files:
            if not file.endswith(".allowed"):
                self.servedfiles.append(base_path+"/"+file)

        for directory in directories:
            self.scan_files(base_path+"/"+directory)

    def serve_page(self, path, data, request_id, link_id, remote_identity, requested_at):
        RNS.log("Page request "+RNS.prettyhexrep(request_id)+" for: "+str(path), RNS.LOG_VERBOSE)
        try:
            self.app.peer_settings["served_page_requests"] += 1
            self.settings_dirty = True
            
        except Exception as e:
            RNS.log("Could not increase served page request count", RNS.LOG_ERROR)

        file_path = path.replace("/page", self.app.pagespath, 1)
        request_allowed = self.request_allowed(file_path, remote_identity)

        try:
            if request_allowed:
                RNS.log("Serving page: "+file_path, RNS.LOG_VERBOSE)
                if not RNS.vendor.platformutils.is_windows() and os.access(file_path, os.X_OK):
                    env_map = {}
                    if "PATH" in os.environ:
                        env_map["PATH"] = os.environ["PATH"]
                    if link_id != None:
                        env_map["link_id"] = RNS.hexrep(link_id, delimit=False)
                    if remote_identity != None:
                        env_map["remote_identity"] = RNS.hexrep(remote_identity.hash, delimit=False)

                    if data != None and isinstance(data, dict):
                        for e in data:
                            if isinstance(e, str) and (e.startswith("field_") or e.startswith("var_")):
                                env_map[e] = data[e]

                    generated = subprocess.run([file_path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env_map)
                    return generated.stdout
                else:
                    with open(file_path, "rb") as fh:
                        response_data = fh.read()
                    return response_data
            else:
                RNS.log("Request denied", RNS.LOG_VERBOSE)
                return DEFAULT_NOTALLOWED.encode("utf-8")

        except Exception as e:
            RNS.log("Error occurred while handling request "+RNS.prettyhexrep(request_id)+" for: "+str(path), RNS.LOG_ERROR)
            RNS.log("The contained exception was: "+str(e), RNS.LOG_ERROR)
            return None

    MEDIA_EXTS = [".webp"]
    def serve_media(self, path, data, request_id, link_id, remote_identity, requested_at):
        if not type(data) == dict: return None
        if not "path" in data: return None
        if not "key" in data: return None

        jail       = os.path.normpath(self.app.pagespath)
        media_path = os.path.join(self.app.pagespath, data["path"].replace("/media/", "").lstrip("/"))
        media_path = os.path.normpath(media_path)
        base_name  = os.path.basename(media_path)
        base_ext   = os.path.splitext(base_name)[-1]

        if not base_ext.lower() in self.MEDIA_EXTS:
            RNS.log(f"Invalid media request type: {media_path}, must be in {self.MEDIA_EXTS}", RNS.LOG_DEBUG)
            return False

        if not media_path.startswith(jail+os.sep):
            RNS.log(f"Invalid media request path: {media_path}", RNS.LOG_DEBUG)
            return False

        if len(media_path) > 512:
            RNS.log(f"Invalid media request path length: {len(media_path)}", RNS.LOG_DEBUG)
            return False

        RNS.log(f"Media request {RNS.prettyhexrep(request_id)} for: {media_path}", RNS.LOG_VERBOSE)
        try:
            self.app.peer_settings["served_media_requests"] += 1
            self.settings_dirty = True
        except Exception as e: RNS.log("Could not increase served page request count", RNS.LOG_ERROR)

        request_allowed = self.request_allowed(media_path, remote_identity)
        try:
            if request_allowed:
                file_path = media_path
                file_name = os.path.basename(file_path)
                RNS.log(f"Serving media: {file_path}", RNS.LOG_VERBOSE)
                return [open(file_path, "rb"), {"name": file_name.encode("utf-8")}]
            
            else:
                RNS.log("Request denied", RNS.LOG_VERBOSE)
                return False

        except Exception as e:
            RNS.log("Error occurred while handling request "+RNS.prettyhexrep(request_id)+" for: "+str(media_path), RNS.LOG_ERROR)
            RNS.log("The contained exception was: "+str(e), RNS.LOG_ERROR)
            return False

    def request_allowed(self, file_path, remote_identity):
        if file_path.lower().endswith(".allowed"): return False
        allowed_path = file_path+".allowed"
        if not os.path.isfile(allowed_path): return True

        allowed_list = []
        try:
            if os.access(allowed_path, os.X_OK):
                allowed_input = subprocess.run([allowed_path], stdout=subprocess.PIPE).stdout
            else:
                with open(allowed_path, "rb") as fh:
                    allowed_input = fh.read()

            for hash_str in allowed_input.splitlines():
                if len(hash_str) == RNS.Identity.TRUNCATED_HASHLENGTH//8*2:
                    try:
                        allowed_list.append(bytes.fromhex(hash_str.decode("utf-8")))
                    except Exception as e:
                        RNS.log("Could not decode RNS Identity hash from: "+str(hash_str), RNS.LOG_DEBUG)
                        RNS.log("The contained exception was: "+str(e), RNS.LOG_DEBUG)

        except Exception as e:
            RNS.log("Error while fetching list of allowed identities for request: "+str(e), RNS.LOG_ERROR)

        if hasattr(remote_identity, "hash") and remote_identity.hash in allowed_list:
            return True

        RNS.log("Denying request, remote identity was not in list of allowed identities", RNS.LOG_VERBOSE)
        return False

    # TODO: Improve file handling, this will be slow for large files
    def serve_file(self, path, data, request_id, remote_identity, requested_at):
        RNS.log("File request "+RNS.prettyhexrep(request_id)+" for: "+str(path), RNS.LOG_VERBOSE)
        try:
            self.app.peer_settings["served_file_requests"] += 1
            self.settings_dirty = True
            
        except Exception as e:
            RNS.log("Could not increase served file request count", RNS.LOG_ERROR)

        file_path = path.replace("/file", self.app.filespath, 1)
        file_name = os.path.basename(file_path)
        if not self.request_allowed(file_path, remote_identity):
            RNS.log("Request denied", RNS.LOG_VERBOSE)
            return DEFAULT_NOTALLOWED.encode("utf-8")

        try:
            RNS.log("Serving file: "+file_path, RNS.LOG_VERBOSE)
            return [open(file_path, "rb"), {"name": file_name.encode("utf-8")}]

        except Exception as e:
            RNS.log("Error occurred while handling request "+RNS.prettyhexrep(request_id)+" for: "+str(path), RNS.LOG_ERROR)
            RNS.log("The contained exception was: "+str(e), RNS.LOG_ERROR)
            return None

    def serve_default_index(self, path, data, request_id, remote_identity, requested_at):
        RNS.log("Serving default index for request "+RNS.prettyhexrep(request_id)+" for: "+str(path), RNS.LOG_VERBOSE)
        return DEFAULT_INDEX.encode("utf-8")

    def announce(self):
        self.app_data = self.name.encode("utf-8")
        self.last_announce = time.time()
        self.app.peer_settings["node_last_announce"] = self.last_announce
        self.destination.announce(app_data=self.app_data)
        if not self.app.disable_propagation: self.app.message_router.announce_propagation_node()

    def __jobs(self):
        while self.should_run_jobs:
            now = time.time()
            
            if now > self.last_announce + self.announce_interval*60:
                self.announce()
                
            if self.page_refresh_interval > 0:
                if now > self.last_page_refresh + self.page_refresh_interval*60:
                    self.register_pages()
                    self.last_page_refresh = time.time()

            if self.file_refresh_interval > 0:
                if now > self.last_file_refresh + self.file_refresh_interval*60:
                    self.register_files()
                    self.last_file_refresh = time.time()

            if self.settings_dirty and now > self.last_settings_flush + Node.SETTINGS_FLUSH_INTERVAL:
                self.settings_dirty = False
                self.last_settings_flush = now
                try: self.app.save_peer_settings()
                except Exception as e: RNS.log("Could not save peer settings: "+str(e), RNS.LOG_ERROR)

            time.sleep(self.job_interval)

    def peer_connected(self, link):
        RNS.log("Peer connected to "+str(self.destination), RNS.LOG_VERBOSE)
        try:
            self.app.peer_settings["node_connects"] += 1
            self.settings_dirty = True

        except Exception as e:
            RNS.log("Could not increase node connection count", RNS.LOG_ERROR)

        link.set_link_closed_callback(self.peer_disconnected)

    def peer_disconnected(self, link):
        RNS.log("Peer disconnected from "+str(self.destination), RNS.LOG_VERBOSE)
        pass

DEFAULT_INDEX = '''>Default Home Page

This node is serving pages, but the home page file (index.mu) was not found in the page storage directory. This is an auto-generated placeholder.

If you are the node operator, you can define your own home page by creating a file named `*index.mu`* in the page storage directory.
'''

DEFAULT_NOTALLOWED = '''>Request Not Allowed

You are not authorised to carry out the request.
'''
