import os
import RNS
import time
import threading
import subprocess
import RNS.vendor.umsgpack as msgpack

class Node:
    JOB_INTERVAL = 5

    def __init__(self, app):
        RNS.log("Nomad Network Node starting...", RNS.LOG_VERBOSE)
        self.app = app
        self.identity = self.app.identity
        self.destination = RNS.Destination(self.identity, RNS.Destination.IN, RNS.Destination.SINGLE, "nomadnetwork", "node")
        self.last_announce = None
        self.announce_interval = self.app.node_announce_interval
        self.job_interval = Node.JOB_INTERVAL
        self.should_run_jobs = True
        self.app_data = None
        self.name = self.app.node_name

        self.register_pages()
        self.register_files()

        if self.name == None:
            self.name = self.app.peer_settings["display_name"]+"'s Node"

        RNS.log("Node \""+self.name+"\" ready for incoming connections on "+RNS.prettyhexrep(self.destination.hash), RNS.LOG_VERBOSE)

        if self.app.node_announce_at_start:
            self.announce()

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
        file_path = path.replace("/page", self.app.pagespath, 1)
        try:
            RNS.log("Serving page: "+file_path, RNS.LOG_VERBOSE)
            if os.access(file_path, os.X_OK):
                generated = subprocess.run([file_path], stdout=subprocess.PIPE)
                return generated.stdout
            else:
                fh = open(file_path, "rb")
                response_data = fh.read()
                fh.close()
                return response_data

        except Exception as e:
            RNS.log("Error occurred while handling request "+RNS.prettyhexrep(request_id)+" for: "+str(path), RNS.LOG_ERROR)
            RNS.log("The contained exception was: "+str(e), RNS.LOG_ERROR)
            return None

    # TODO: Improve file handling, this will be slow for large files
    def serve_file(self, path, data, request_id, remote_identity, requested_at):
        RNS.log("File request "+RNS.prettyhexrep(request_id)+" for: "+str(path), RNS.LOG_VERBOSE)
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

    def peer_connected(link):
        RNS.log("Peer connected to "+str(self.destination), RNS.LOG_INFO)
        link.set_link_closed_callback(self.peer_disconnected)


DEFAULT_INDEX = '''>Default Home Page

This node is serving pages, but the home page file (index.mu) was not found in the page storage directory. This is an auto-generated placeholder.

If you are the node operator, you can define your own home page by creating a file named `*index.mu`* in the page storage directory.
'''