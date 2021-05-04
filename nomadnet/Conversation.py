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
            if os.path.isdir(app.conversationpath + "/" + entry):
                try:
                    conversations.append(Conversation(entry, app))
                except Exception as e:
                    RNS.log("Error while loading conversation "+str(entry)+", skipping it. The contained exception was: "+str(e), RNS.LOG_ERROR)

        return conversations



    def __init__(self, source_hash, app):
        self.source_hash        = source_hash
        self.message_path       = app.conversationpath + "/" + source_hash
        self.messages_load_time = None
        self.messages           = []
        self.source_known       = False
        self.source_trusted     = False
        self.source_blocked     = False

    def __str__(self):
        return self.source_hash