import os
import RNS
import LXMF
import shutil
from nomadnet.Directory import DirectoryEntry

class Conversation:
    cached_conversations = {}
    created_callback = None

    @staticmethod
    def ingest(lxmessage, app, originator = False, delegate = None):
        if originator:
            source_hash = lxmessage.destination_hash
        else:
            source_hash = lxmessage.source_hash
        
        source_hash_path = RNS.hexrep(source_hash, delimit=False)

        conversation_path = app.conversationpath + "/" + source_hash_path

        if not os.path.isdir(conversation_path):
            os.makedirs(conversation_path)
            if Conversation.created_callback != None:
                Conversation.created_callback()

        ingested_path = lxmessage.write_to_directory(conversation_path)

        if RNS.hexrep(source_hash, delimit=False) in Conversation.cached_conversations:
            conversation = Conversation.cached_conversations[RNS.hexrep(source_hash, delimit=False)]
            conversation.scan_storage()

        return ingested_path

    @staticmethod
    def conversation_list(app):
        conversations = []
        for dirname in os.listdir(app.conversationpath):
            if len(dirname) == RNS.Identity.TRUNCATED_HASHLENGTH//8*2 and os.path.isdir(app.conversationpath + "/" + dirname):
                try:
                    source_hash_text = dirname
                    source_hash      = bytes.fromhex(dirname)
                    app_data         = RNS.Identity.recall_app_data(source_hash)
                    display_name     = app.directory.display_name(source_hash)

                    if display_name == None and app_data:
                        display_name = app_data.decode("utf-8")
                    
                    trust_level      = app.directory.trust_level(source_hash, display_name)
                    
                    entry = (source_hash_text, display_name, trust_level)
                    conversations.append(entry)

                except Exception as e:
                    RNS.log("Error while loading conversation "+str(dirname)+", skipping it. The contained exception was: "+str(e), RNS.LOG_ERROR)

        conversations.sort(key=lambda e: (-e[2], e[1], e[0]), reverse=False)

        return conversations

    @staticmethod
    def cache_conversation(conversation):
        Conversation.cached_conversations[conversation.source_hash] = conversation

    @staticmethod
    def delete_conversation(source_hash_path, app):
        conversation_path = app.conversationpath + "/" + source_hash_path

        try:
            if os.path.isdir(conversation_path):
                shutil.rmtree(conversation_path)
        except Exception as e:
            RNS.log("Could not remove conversation at "+str(conversation_path)+". The contained exception was: "+str(e), RNS.LOG_ERROR)

    def __init__(self, source_hash, app):
        self.app                = app
        self.source_hash        = source_hash
        self.send_destination   = None
        self.messages           = []
        self.messages_path      = app.conversationpath + "/" + source_hash
        self.messages_load_time = None
        self.source_known       = False
        self.source_trusted     = False
        self.source_blocked     = False

        self.__changed_callback = None

        self.source_identity = RNS.Identity.recall(bytes.fromhex(self.source_hash))

        if self.source_identity:
            self.source_known = True
            self.send_destination = RNS.Destination(self.source_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")

        self.scan_storage()

        self.trust_level = app.directory.trust_level(bytes.fromhex(self.source_hash))

        Conversation.cache_conversation(self)

    def scan_storage(self):
        old_len = len(self.messages)
        self.messages = []
        for filename in os.listdir(self.messages_path):
            if len(filename) == RNS.Identity.HASHLENGTH//8*2:
                message_path = self.messages_path + "/" + filename
                self.messages.append(ConversationMessage(message_path))

        if self.__changed_callback != None:
            self.__changed_callback(self)


    def __str__(self):
        string = self.source_hash

        if self.source_identity:
            if self.source_identity.app_data:
                # TODO: Sanitise for viewing
                string += " | "+self.source.source_identity.app_data.decode("utf-8")

        return string

    def register_changed_callback(self, callback):
        self.__changed_callback = callback

    def send(self, content="", title=""):
        if self.send_destination:
            dest = self.send_destination
            source = self.app.lxmf_destination
            lxm = LXMF.LXMessage(dest, source, content, desired_method=LXMF.LXMessage.DIRECT)
            lxm.register_delivery_callback(self.message_delivered)
            self.app.message_router.handle_outbound(lxm)

            message_path = Conversation.ingest(lxm, self.app, originator=True)
            self.messages.append(ConversationMessage(message_path))

        else:
            # TODO: Implement
            # Alter UI so message cannot be sent until there is a path, or LXMF propagation is implemented
            RNS.log("Destination unknown")

    def message_delivered(self, message):
        message_path = Conversation.ingest(message, self.app, originator=True)



class ConversationMessage:
    def __init__(self, file_path):
        self.file_path = file_path
        self.loaded    = False
        self.timestamp = None
        self.lxm       = None

    def load(self):
        try:
            self.lxm = LXMF.LXMessage.unpack_from_file(open(self.file_path, "rb"))
            self.loaded = True
            self.timestamp = self.lxm.timestamp
        except Exception as e:
            RNS.log("Error while loading LXMF message "+str(self.file_path)+" from disk. The contained exception was: "+str(e), RNS.LOG_ERROR)

    def unload(self):
        self.loaded = False
        self.lxm    = None

    def get_timestamp(self):
        if not self.loaded:
            self.load()

        return self.timestamp

    def get_title(self):
        if not self.loaded:
            self.load()

        return self.lxm.title_as_string()

    def get_content(self):
        if not self.loaded:
            self.load()

        return self.lxm.content_as_string()

    def get_hash(self):
        if not self.loaded:
            self.load()

        return self.lxm.hash

    def signature_validated(self):
        if not self.loaded:
            self.load()

        return self.lxm.signature_validated

    def get_signature_description(self):
        if self.signature_validated():
            return "Signature Verified"
        else:
            if self.lxm.unverified_reason == LXMF.LXMessage.SOURCE_UNKNOWN:
                return "Unknown Origin"
            elif self.lxm.unverified_reason == LXMF.LXMessage.SIGNATURE_INVALID:
                return "Invalid Signature"
            else:
                return "Unknown signature validation failure"