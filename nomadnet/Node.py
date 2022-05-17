import os
import RNS
import time
import threading
import subprocess
import RNS.vendor.umsgpack as msgpack

class Node:
    JOB_INTERVAL = 5
    START_ANNOUNCE_DELAY = 6

    def __init__(self, app):
        RNS.log("Nomad Network Node starting...", RNS.LOG_VERBOSE)
        self.app = app
        self.identity = self.app.identity
        self.destination = RNS.Destination(self.identity, RNS.Destination.IN, RNS.Destination.SINGLE, "nomadnetwork", "node")
        self.last_announce = time.time()
        self.announce_interval = self.app.node_announce_interval
        self.job_interval = Node.JOB_INTERVAL
        self.should_run_jobs = True
        self.app_data = None
        self.name = self.app.node_name

        self.register_pages()
        self.register_files()

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
        self.servedpages = []
        self.scan_pages(self.app.pagespath)

        if not self.app.pagespath+"index.mu" in self.servedpages:
            self.destination.register_request_handler(
                "/page/index.mu",
                response_generator = self.serve_default_index,
                allow = RNS.Destination.ALLOW_ALL
            )

        for page in self.servedpages:
            request_path = "/page"+page.replace(self.app.pagespath, "")
            self.destination.register_request_handler(
                request_path,
                response_generator = self.serve_page,
                allow = RNS.Destination.ALLOW_ALL
            )

    def register_files(self):
        self.servedfiles = []
        self.scan_files(self.app.filespath)

        for file in self.servedfiles:
            request_path = "/file"+file.replace(self.app.filespath, "")
            self.destination.register_request_handler(
                request_path,
                response_generator = self.serve_file,
                allow = RNS.Destination.ALLOW_ALL
            )

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
            self.servedfiles.append(base_path+"/"+file)

        for directory in directories:
            self.scan_files(base_path+"/"+directory)

    def serve_page(self, path, data, request_id, remote_identity, requested_at):
        RNS.log("Page request "+RNS.prettyhexrep(request_id)+" for: "+str(path), RNS.LOG_VERBOSE)
        try:
            self.app.peer_settings["served_page_requests"] += 1
            self.app.save_peer_settings()
            
        except Exception as e:
            RNS.log("Could not increase served page request count", RNS.LOG_ERROR)

        file_path = path.replace("/page", self.app.pagespath, 1)

        allowed_path = file_path+".allowed"
        request_allowed = False

        if os.path.isfile(allowed_path):
            allowed_list = []

            try:
                if os.access(allowed_path, os.X_OK):
                    allowed_result = subprocess.run([allowed_path], stdout=subprocess.PIPE)
                    allowed_input = allowed_result.stdout

                else:
                    fh = open(allowed_path, "rb")
                    allowed_input = fh.read()
                    fh.close()

                allowed_hash_strs = allowed_input.splitlines()

                for hash_str in allowed_hash_strs:
                    if len(hash_str) == RNS.Identity.TRUNCATED_HASHLENGTH//8*2:
                        try:
                            allowed_hash = bytes.fromhex(hash_str.decode("utf-8"))
                            allowed_list.append(allowed_hash)

                        except Exception as e:
                            RNS.log("Could not decode RNS Identity hash from: "+str(hash_str), RNS.LOG_DEBUG)
                            RNS.log("The contained exception was: "+str(e), RNS.LOG_DEBUG)

            except Exception as e:
                RNS.log("Error while fetching list of allowed identities for request: "+str(e), RNS.LOG_ERROR)

            if hasattr(remote_identity, "hash") and remote_identity.hash in allowed_list:
                request_allowed = True
            else:
                request_allowed = False
                RNS.log("Denying request, remote identity was not in list of allowed identities", RNS.LOG_VERBOSE)

        else:
            request_allowed = True

        try:
            if request_allowed:
                RNS.log("Serving page: "+file_path, RNS.LOG_VERBOSE)
                if os.access(file_path, os.X_OK):
                    generated = subprocess.run([file_path], stdout=subprocess.PIPE)
                    return generated.stdout
                else:
                    fh = open(file_path, "rb")
                    response_data = fh.read()
                    fh.close()
                    return response_data
            else:
                RNS.log("Request denied", RNS.LOG_VERBOSE)
                return DEFAULT_NOTALLOWED.encode("utf-8")

        except Exception as e:
            RNS.log("Error occurred while handling request "+RNS.prettyhexrep(request_id)+" for: "+str(path), RNS.LOG_ERROR)
            RNS.log("The contained exception was: "+str(e), RNS.LOG_ERROR)
            return None

    # TODO: Improve file handling, this will be slow for large files
    def serve_file(self, path, data, request_id, remote_identity, requested_at):
        RNS.log("File request "+RNS.prettyhexrep(request_id)+" for: "+str(path), RNS.LOG_VERBOSE)
        try:
            self.app.peer_settings["served_file_requests"] += 1
            self.app.save_peer_settings()
            
        except Exception as e:
            RNS.log("Could not increase served file request count", RNS.LOG_ERROR)

        file_path = path.replace("/file", self.app.filespath, 1)
        file_name = path.replace("/file/", "", 1)
        try:
            RNS.log("Serving file: "+file_path, RNS.LOG_VERBOSE)
            fh = open(file_path, "rb")
            file_data = fh.read()
            fh.close()
            return [file_name, file_data]

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
        self.app.message_router.announce_propagation_node()

    def __jobs(self):
        while self.should_run_jobs:
            now = time.time()
            
            if now > self.last_announce + self.announce_interval*60:
                self.announce()

            time.sleep(self.job_interval)

    def peer_connected(self, link):
        RNS.log("Peer connected to "+str(self.destination), RNS.LOG_VERBOSE)
        try:
            self.app.peer_settings["node_connects"] += 1
            self.app.save_peer_settings()

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