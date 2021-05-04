import os
import RNS
import LXMF

class Conversation:
    @staticmethod
    def ingest(lxmessage, app):
        source_hash_path = RNS.hexrep(lxmessage.source_hash, delimit=False)
        conversation_path = app.conversationpath + "/" + source_hash_path

        if not os.path.isdir(conversation_path):
            os.makedirs(conversation_path)

        lxmessage.write_to_directory(conversation_path)

    @staticmethod
    def conversation_list(app):
        conversations = []
        for entry in os.listdir(app.conversationpath):
            if len(entry) == RNS.Identity.TRUNCATED_HASHLENGTH//8*2 and os.path.isdir(app.conversationpath + "/" + entry):
                try:
                    conversations.append(entry)
                except Exception as e:
                    RNS.log("Error while loading conversation "+str(entry)+", skipping it. The contained exception was: "+str(e), RNS.LOG_ERROR)

        return conversations



    def __init__(self, source_hash, app):
        self.source_hash        = source_hash
        self.messages_path      = app.conversationpath + "/" + source_hash
        self.messages_load_time = None
        self.messages           = []
        self.source_known       = False
        self.source_trusted     = False
        self.source_blocked     = False

        for filename in os.listdir(self.messages_path):
            if len(filename) == RNS.Identity.HASHLENGTH//8*2:
                message_path = self.messages_path + "/" + filename
                self.messages.append(ConversationMessage(message_path))

    def __str__(self):
        return self.source_hash

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