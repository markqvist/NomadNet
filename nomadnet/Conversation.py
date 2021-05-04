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

    def __init__(self):
        pass