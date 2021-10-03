import os
import RNS
import LXMF
import shutil
import nomadnet
from nomadnet.Directory import DirectoryEntry

class Conversation:
    cached_conversations = {}
    unread_conversations = {}
    created_callback = None

    aspect_filter = "lxmf.delivery"
    @staticmethod
    def received_announce(destination_hash, announced_identity, app_data):
        app = nomadnet.NomadNetworkApp.get_shared_instance()
        destination_hash_text = RNS.hexrep(destination_hash, delimit=False)
        # Check if the announced destination is in
        # our list of conversations
        if destination_hash_text in [e[0] for e in Conversation.conversation_list(app)]:
            if app.directory.find(destination_hash):
                if Conversation.created_callback != None:
                    Conversation.created_callback()
            else:
                if Conversation.created_callback != None:
                    Conversation.created_callback()

        # Add the announce to the directory announce
        # stream logger
        app.directory.lxmf_announce_received(destination_hash, app_data)

    @staticmethod
    def query_for_peer(source_hash):
        try:
            RNS.Transport.request_path(bytes.fromhex(source_hash))
        except Exception as e:
            RNS.log("Error while querying network for peer identity. The contained exception was: "+str(e), RNS.LOG_ERROR)

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

        if not source_hash in Conversation.unread_conversations:
            Conversation.unread_conversations[source_hash] = True
            try:
                dirname = RNS.hexrep(source_hash, delimit=False)
                open(app.conversationpath + "/" + dirname + "/unread", 'a').close()
            except Exception as e:
                pass

            Conversation.created_callback()

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

                    unread = False
                    if source_hash in Conversation.unread_conversations:
                        unread = True
                    elif os.path.isfile(app.conversationpath + "/" + dirname + "/unread"):
                        Conversation.unread_conversations[source_hash] = True
                        unread = True

                    if display_name == None and app_data:
                        display_name = app_data.decode("utf-8")

                    if display_name == None:
                        sort_name = ""
                    else:
                        sort_name = display_name
                    
                    trust_level      = app.directory.trust_level(source_hash, display_name)
                    
                    entry = (source_hash_text, display_name, trust_level, sort_name, unread)
                    conversations.append(entry)

                except Exception as e:
                    RNS.log("Error while loading conversation "+str(dirname)+", skipping it. The contained exception was: "+str(e), RNS.LOG_ERROR)

        conversations.sort(key=lambda e: (-e[2], e[3], e[0]), reverse=False)

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

    def __init__(self, source_hash, app, initiator=False):
        self.app                = app
        self.source_hash        = source_hash
        self.send_destination   = None
        self.messages           = []
        self.messages_path      = app.conversationpath + "/" + source_hash
        self.messages_load_time = None
        self.source_known       = False
        self.source_trusted     = False
        self.source_blocked     = False
        self.unread             = False

        self.__changed_callback = None

        self.source_identity = RNS.Identity.recall(bytes.fromhex(self.source_hash))

        if self.source_identity:
            self.source_known = True
            self.send_destination = RNS.Destination(self.source_identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")

        if initiator:
            if not os.path.isdir(self.messages_path):
                os.makedirs(self.messages_path)
                if Conversation.created_callback != None:
                    Conversation.created_callback()

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

        new_len = len(self.messages)

        if new_len > old_len:
            self.unread = True

        if self.__changed_callback != None:
            self.__changed_callback(self)

    def purge_failed(self):
        purged_messages = []
        for conversation_message in self.messages:
            if conversation_message.get_state() == LXMF.LXMessage.FAILED:
                purged_messages.append(conversation_message)
                conversation_message.purge()

        for purged_message in purged_messages:
            self.messages.remove(purged_message)

    def clear_history(self):
        purged_messages = []
        for conversation_message in self.messages:
            purged_messages.append(conversation_message)
            conversation_message.purge()

        for purged_message in purged_messages:
            self.messages.remove(purged_message)

    def register_changed_callback(self, callback):
        self.__changed_callback = callback

    def send(self, content="", title=""):
        if self.send_destination:
            dest = self.send_destination
            source = self.app.lxmf_destination
            desired_method = LXMF.LXMessage.DIRECT
            if self.app.directory.preferred_delivery(dest.hash) == DirectoryEntry.PROPAGATED:
                if self.app.message_router.get_outbound_propagation_node() != None:
                    desired_method = LXMF.LXMessage.PROPAGATED

            lxm = LXMF.LXMessage(dest, source, content, title=title, desired_method=desired_method)
            lxm.register_delivery_callback(self.message_notification)
            lxm.register_failed_callback(self.message_notification)

            if self.app.message_router.get_outbound_propagation_node() != None:
                lxm.try_propagation_on_fail = self.app.try_propagation_on_fail

            self.app.message_router.handle_outbound(lxm)

            message_path = Conversation.ingest(lxm, self.app, originator=True)
            self.messages.append(ConversationMessage(message_path))

            return True
        else:
            RNS.log("Destination is not known, cannot create LXMF Message.", RNS.LOG_VERBOSE)
            return False

    def message_notification(self, message):
        if message.state == LXMF.LXMessage.FAILED and hasattr(message, "try_propagation_on_fail") and message.try_propagation_on_fail:
            RNS.log("Direct delivery of "+str(message)+" failed. Retrying as propagated message.", RNS.LOG_VERBOSE)
            message.try_propagation_on_fail = None
            message.delivery_attempts = 0
            del message.next_delivery_attempt
            message.packed = None
            message.desired_method = LXMF.LXMessage.PROPAGATED
            self.app.message_router.handle_outbound(message)
        else:
            message_path = Conversation.ingest(message, self.app, originator=True)

    def __str__(self):
        string = self.source_hash

        if self.source_identity:
            if self.source_identity.app_data:
                # TODO: Sanitise for viewing
                string += " | "+self.source.source_identity.app_data.decode("utf-8")

        return string



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
            self.sort_timestamp = os.path.getmtime(self.file_path)

            if self.lxm.state > LXMF.LXMessage.DRAFT and self.lxm.state < LXMF.LXMessage.SENT:
                found = False
                for pending in nomadnet.NomadNetworkApp.get_shared_instance().message_router.pending_outbound:
                    if pending.hash == self.lxm.hash:
                        found = True

                if not found:
                    self.lxm.state = LXMF.LXMessage.FAILED

        except Exception as e:
            RNS.log("Error while loading LXMF message "+str(self.file_path)+" from disk. The contained exception was: "+str(e), RNS.LOG_ERROR)

    def unload(self):
        self.loaded = False
        self.lxm    = None

    def purge(self):
        self.unload()
        if os.path.isfile(self.file_path):
            os.unlink(self.file_path)

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

    def get_state(self):
        if not self.loaded:
            self.load()

        return self.lxm.state

    def get_transport_encryption(self):
        if not self.loaded:
            self.load()

        return self.lxm.transport_encryption

    def get_transport_encrypted(self):
        if not self.loaded:
            self.load()

        return self.lxm.transport_encrypted

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