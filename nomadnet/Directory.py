import os
import RNS
import LXMF
import RNS.vendor.umsgpack as msgpack

class Directory:
    def __init__(self, app):
        self.directory_entries = {}
        self.app = app
        self.load_from_disk()

    def save_to_disk(self):
        try:
            packed_list = []
            for source_hash in self.directory_entries:
                e = self.directory_entries[source_hash]
                packed_list.append((e.source_hash, e.display_name, e.trust_level))

            file = open(self.app.directorypath, "wb")
            file.write(msgpack.packb(packed_list))
            file.close()
        except Exception as e:
            RNS.log("Could not write directory to disk. Then contained exception was: "+str(e), RNS.LOG_ERROR)

    def load_from_disk(self):
        if os.path.isfile(self.app.directorypath):
            try:
                file = open(self.app.directorypath, "rb")
                unpacked_list = msgpack.unpackb(file.read())
                file.close()

                entries = {}
                for e in unpacked_list:
                    entries[e[0]] = DirectoryEntry(e[0], e[1], e[2])

                self.directory_entries = entries

            except Exception as e:
                RNS.log("Could not load directory from disk. The contained exception was: "+str(e), RNS.LOG_ERROR)

    def display_name(self, source_hash):
        if source_hash in self.directory_entries:
            return self.directory_entries[source_hash].display_name
        else:
            return None

    def simplest_display_str(self, source_hash):
        trust_level = self.trust_level(source_hash)
        if trust_level == DirectoryEntry.WARNING or trust_level == DirectoryEntry.UNTRUSTED:
            return "<"+RNS.hexrep(source_hash, delimit=False)+">"
        else:
            if source_hash in self.directory_entries:
                return self.directory_entries[source_hash].display_name
            else:
                return "<"+RNS.hexrep(source_hash, delimit=False)+">"

    def trust_level(self, source_hash, announced_display_name=None):
        if source_hash in self.directory_entries:
            if announced_display_name == None:
                return self.directory_entries[source_hash].trust_level
            else:
                for entry in self.directory_entries:
                    e = self.directory_entries[entry]
                    if e.display_name == announced_display_name:
                        if e.source_hash != source_hash:
                            return DirectoryEntry.WARNING

                return self.directory_entries[source_hash].trust_level
        else:
            return DirectoryEntry.UNKNOWN

    def remember(self, entry):
        self.directory_entries[entry.source_hash] = entry

    def forget(self, source_hash):
        if source_hash in self.directory_entries:
            self.directory_entries.pop(source_hash)

    def find(self, source_hash):
        if source_hash in self.directory_entries:
            return self.directory_entries[source_hash]
        else:
            return None


class DirectoryEntry:
    WARNING   = 0x00
    UNTRUSTED = 0x01
    UNKNOWN   = 0x02
    TRUSTED   = 0xFF

    def __init__(self, source_hash, display_name=None, trust_level=UNKNOWN):
        if len(source_hash) == RNS.Identity.TRUNCATED_HASHLENGTH//8:
            self.source_hash  = source_hash
            self.display_name = display_name
            if display_name  == None:
                display_name  = source_hash

            self.trust_level  = trust_level
        else:
            raise TypeError("Attempt to add invalid source hash to directory")