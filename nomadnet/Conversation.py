import os
import RNS
import LXMF
import shutil
import msgpack
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

        if not destination_hash in app.ignored_list:
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

            # This reformats the new v0.5.0 announce data back to the expected format
            # for nomadnets storage and other handling functions.
            dn = LXMF.display_name_from_app_data(app_data)
            app_data = b""
            if dn != None:
                app_data = dn.encode("utf-8")
            
            # Add the announce to the directory announce
            # stream logger
            app.directory.lxmf_announce_received(destination_hash, app_data)
            
        else:
            RNS.log("Ignored announce from "+RNS.prettyhexrep(destination_hash), RNS.LOG_DEBUG)

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

        try:
            ConversationMessage.extract_attachments_from_lxm(lxmessage, app)
        except Exception as e:
            RNS.log("Error extracting attachments: "+str(e), RNS.LOG_ERROR)

        if RNS.hexrep(source_hash, delimit=False) in Conversation.cached_conversations:
            conversation = Conversation.cached_conversations[RNS.hexrep(source_hash, delimit=False)]
            conversation.scan_storage()

        if source_hash in Conversation.unread_conversations:
            Conversation.unread_conversations[source_hash] += 1
        else:
            Conversation.unread_conversations[source_hash] = 1

        try:
            dirname = RNS.hexrep(source_hash, delimit=False)
            with open(app.conversationpath + "/" + dirname + "/unread", "w") as uf:
                uf.write(str(Conversation.unread_conversations[source_hash]))
        except Exception as e:
            pass

        if Conversation.created_callback != None:
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

                    unread = 0
                    if source_hash in Conversation.unread_conversations:
                        unread = Conversation.unread_conversations[source_hash]
                    elif os.path.isfile(app.conversationpath + "/" + dirname + "/unread"):
                        try:
                            with open(app.conversationpath + "/" + dirname + "/unread", "r") as uf:
                                content = uf.read().strip()
                                unread = int(content) if content else 1
                        except Exception:
                            unread = 1
                        Conversation.unread_conversations[source_hash] = unread

                    if display_name == None and app_data:
                        display_name = LXMF.display_name_from_app_data(app_data)

                    if display_name == None:
                        sort_name = ""
                    else:
                        sort_name = display_name
                    
                    trust_level      = app.directory.trust_level(source_hash, display_name)

                    conversation_dir = app.conversationpath + "/" + dirname
                    try:
                        last_activity = os.path.getmtime(conversation_dir)
                    except Exception:
                        last_activity = 0

                    entry = (source_hash_text, display_name, trust_level, sort_name, unread, last_activity)
                    conversations.append(entry)

                except Exception as e:
                    RNS.log("Error while loading conversation "+str(dirname)+", skipping it. The contained exception was: "+str(e), RNS.LOG_ERROR)

        conversations.sort(key=lambda e: e[5], reverse=True)

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

        if not RNS.Identity.recall(bytes.fromhex(self.source_hash)):
            RNS.Transport.request_path(bytes.fromhex(source_hash))

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
        existing = {}
        for msg in self.messages:
            existing[msg.file_path] = msg

        index = ConversationMessage.read_index(self.messages_path)

        self.messages = []
        for filename in os.listdir(self.messages_path):
            if len(filename) == RNS.Identity.HASHLENGTH//8*2:
                message_path = self.messages_path + "/" + filename
                if message_path in existing:
                    old_msg = existing[message_path]
                    try:
                        current_mtime = os.path.getmtime(message_path)
                        if current_mtime > old_msg.sort_timestamp:
                            old_msg._cached_state = None
                            old_msg._cached_method = None
                            old_msg.sort_timestamp = current_mtime
                    except Exception:
                        pass
                    self.messages.append(old_msg)
                else:
                    msg = ConversationMessage(message_path)
                    if filename in index:
                        msg.restore_from_index(index[filename])
                    self.messages.append(msg)

        new_len = len(self.messages)

        needs_index_update = []
        for msg in self.messages:
            filename = os.path.basename(msg.file_path)
            if msg._cached_state is not None:
                if filename not in index:
                    needs_index_update.append(msg)
                elif "content" not in index[filename]:
                    needs_index_update.append(msg)
        if needs_index_update:
            ConversationMessage.write_index(self.messages_path, needs_index_update)

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

    def send(self, content="", title="", fields=None):
        if self.send_destination:
            dest = self.send_destination
            source = self.app.lxmf_destination
            desired_method = LXMF.LXMessage.DIRECT
            if self.app.directory.preferred_delivery(dest.hash) == DirectoryEntry.PROPAGATED:
                if self.app.message_router.get_outbound_propagation_node() != None:
                    desired_method = LXMF.LXMessage.PROPAGATED
            else:
                if not self.app.message_router.delivery_link_available(dest.hash) and RNS.Identity.current_ratchet_id(dest.hash) != None:
                    RNS.log(f"Have ratchet for {RNS.prettyhexrep(dest.hash)}, requesting opportunistic delivery of message", RNS.LOG_DEBUG)
                    desired_method = LXMF.LXMessage.OPPORTUNISTIC

            dest_is_trusted = False
            if self.app.directory.trust_level(dest.hash) == DirectoryEntry.TRUSTED:
                dest_is_trusted = True

            lxm = LXMF.LXMessage(dest, source, content, title=title, fields=fields, desired_method=desired_method, include_ticket=dest_is_trusted)
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

    def paper_output(self, content="", title="", mode="print_qr"):
        if self.send_destination:
            try:
                dest = self.send_destination
                source = self.app.lxmf_destination
                desired_method = LXMF.LXMessage.PAPER

                lxm = LXMF.LXMessage(dest, source, content, title=title, desired_method=desired_method)

                if mode == "print_qr":
                    qr_code = lxm.as_qr()
                    qr_tmp_path = self.app.tmpfilespath+"/"+str(RNS.hexrep(lxm.hash, delimit=False))
                    qr_code.save(qr_tmp_path)

                    print_result = self.app.print_file(qr_tmp_path)
                    os.unlink(qr_tmp_path)
                    
                    if print_result:
                        message_path = Conversation.ingest(lxm, self.app, originator=True)
                        self.messages.append(ConversationMessage(message_path))

                    return print_result

                elif mode == "save_qr":
                    qr_code = lxm.as_qr()
                    qr_save_path = self.app.downloads_path+"/LXM_"+str(RNS.hexrep(lxm.hash, delimit=False)+".png")
                    qr_code.save(qr_save_path)
                    message_path = Conversation.ingest(lxm, self.app, originator=True)
                    self.messages.append(ConversationMessage(message_path))
                    return qr_save_path

                elif mode == "save_uri":
                    lxm_uri = lxm.as_uri()+"\n"
                    uri_save_path = self.app.downloads_path+"/LXM_"+str(RNS.hexrep(lxm.hash, delimit=False)+".txt")
                    with open(uri_save_path, "wb") as f:
                        f.write(lxm_uri.encode("utf-8"))

                    message_path = Conversation.ingest(lxm, self.app, originator=True)
                    self.messages.append(ConversationMessage(message_path))
                    return uri_save_path

                elif mode == "return_uri":
                    return lxm.as_uri()

            except Exception as e:
                RNS.log("An error occurred while generating paper message, the contained exception was: "+str(e), RNS.LOG_ERROR)
                return False

        else:
            RNS.log("Destination is not known, cannot create LXMF Message.", RNS.LOG_VERBOSE)
            return False

    def message_notification(self, message):
        if message.state == LXMF.LXMessage.FAILED and hasattr(message, "try_propagation_on_fail") and message.try_propagation_on_fail:
            if hasattr(message, "stamp_generation_failed") and message.stamp_generation_failed == True:
                RNS.log(f"Could not send {message} due to a stamp generation failure", RNS.LOG_ERROR)
            else:
                RNS.log("Direct delivery of "+str(message)+" failed. Retrying as propagated message.", RNS.LOG_VERBOSE)
                message.try_propagation_on_fail = None
                message.delivery_attempts = 0
                if hasattr(message, "next_delivery_attempt"):
                    del message.next_delivery_attempt
                message.packed = None
                message.desired_method = LXMF.LXMessage.PROPAGATED
                self.app.message_router.handle_outbound(message)
        else:
            message_path = Conversation.ingest(message, self.app, originator=True)

    def __str__(self):
        string = self.source_hash

        # TODO: Remove this
        # if self.source_identity:
        #     if self.source_identity.app_data:
        #         # TODO: Sanitise for viewing, or just clean this
        #         string += " | "+self.source_identity.app_data.decode("utf-8")

        return string



class ConversationMessage:
    def __init__(self, file_path):
        self.file_path = file_path
        self.loaded    = False
        self.timestamp = None
        self.lxm       = None

        self._cached_hash = None
        self._cached_state = None
        self._cached_title = None
        self._cached_content = None
        self._cached_source_hash = None
        self._cached_transport_encrypted = None
        self._cached_transport_encryption = None
        self._cached_signature_validated = None
        self._cached_unverified_reason = None
        self._cached_method = None
        self._cached_has_attachments = None
        self._cached_attachment_names = None

        self.sort_timestamp = os.path.getmtime(file_path) if os.path.isfile(file_path) else 0

        filename = os.path.basename(file_path)
        if len(filename) == RNS.Identity.HASHLENGTH//8*2:
            try:
                self._cached_hash = bytes.fromhex(filename)
            except Exception:
                pass

    def load(self):
        try:
            with open(self.file_path, "rb") as lxm_file:
                self.lxm = LXMF.LXMessage.unpack_from_file(lxm_file)
            self.loaded = True
            self.timestamp = self.lxm.timestamp
            self.sort_timestamp = os.path.getmtime(self.file_path)

            if self.lxm.state > LXMF.LXMessage.GENERATING and self.lxm.state < LXMF.LXMessage.SENT:
                found = False

                for pending in nomadnet.NomadNetworkApp.get_shared_instance().message_router.pending_outbound:
                    if pending.hash == self.lxm.hash:
                        found = True

                for pending_id in nomadnet.NomadNetworkApp.get_shared_instance().message_router.pending_deferred_stamps:
                    if pending_id == self.lxm.hash:
                        found = True

                if not found:
                    self.lxm.state = LXMF.LXMessage.FAILED

            if self._cached_hash is None:
                self._cached_hash = self.lxm.hash
            self._cached_state = self.lxm.state
            if self._cached_source_hash is None:
                self._cached_source_hash = self.lxm.source_hash
            self._cached_transport_encrypted = self.lxm.transport_encrypted
            self._cached_transport_encryption = self.lxm.transport_encryption
            if self._cached_signature_validated is None:
                self._cached_signature_validated = self.lxm.signature_validated
            self._cached_method = self.lxm.method
            if self._cached_unverified_reason is None and hasattr(self.lxm, "unverified_reason"):
                self._cached_unverified_reason = self.lxm.unverified_reason
            self._cached_title = self.lxm.title_as_string()
            self._cached_content = self.lxm.content_as_string()

            if self._cached_has_attachments is None:
                found_in_fields = False
                fields = None
                if hasattr(self.lxm, "get_fields"):
                    fields = self.lxm.get_fields()
                if fields and isinstance(fields, dict):
                    found_in_fields = (
                        LXMF.FIELD_FILE_ATTACHMENTS in fields
                        or LXMF.FIELD_IMAGE in fields
                        or LXMF.FIELD_AUDIO in fields
                    )
                    if found_in_fields:
                        names = []
                        file_atts = fields.get(LXMF.FIELD_FILE_ATTACHMENTS, [])
                        for att in file_atts:
                            if isinstance(att, list) and len(att) >= 2:
                                size = len(att[1]) if isinstance(att[1], bytes) else 0
                                names.append(("file", str(att[0]), size))
                        if LXMF.FIELD_IMAGE in fields:
                            fmt, data = ConversationMessage._unpack_media_field(fields[LXMF.FIELD_IMAGE])
                            if data:
                                size = len(data)
                                ext = ConversationMessage._ext_from_media_format(fmt, data)
                                names.append(("file", "image"+ext, size))
                        if LXMF.FIELD_AUDIO in fields:
                            fmt, data = ConversationMessage._unpack_media_field(fields[LXMF.FIELD_AUDIO])
                            if data:
                                size = len(data)
                                ext = ConversationMessage._ext_from_media_format(fmt, data, is_audio=True)
                                names.append(("file", "audio"+ext, size))
                        self._cached_has_attachments = True
                        self._cached_attachment_names = names

                if not found_in_fields:
                    att_dir = self._attachment_dir()
                    if att_dir and os.path.isdir(att_dir):
                        manifest = self._read_attachment_manifest(att_dir)
                        if manifest and "files" in manifest and len(manifest["files"]) > 0:
                            names = []
                            for entry in manifest["files"]:
                                names.append(("file", entry["name"], entry.get("size", 0)))
                            self._cached_has_attachments = True
                            self._cached_attachment_names = names
                        else:
                            self._cached_has_attachments = False
                            self._cached_attachment_names = []
                    else:
                        self._cached_has_attachments = False
                        self._cached_attachment_names = []

            try:
                app = nomadnet.NomadNetworkApp.get_shared_instance()
                ConversationMessage.extract_attachments_from_lxm(self.lxm, app)
                ConversationMessage.strip_attachments_from_file(self.file_path, app)
            except Exception:
                pass

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
        if self.timestamp is not None:
            return self.timestamp
        if not self.loaded:
            self.load()
        return self.timestamp

    def get_title(self):
        if self._cached_title is not None:
            return self._cached_title
        if not self.loaded:
            self.load()
        return self._cached_title if self._cached_title is not None else ""

    def get_content(self):
        if self._cached_content is not None:
            return self._cached_content
        if not self.loaded:
            self.load()
        return self._cached_content if self._cached_content is not None else ""

    def get_hash(self):
        if self._cached_hash is not None:
            return self._cached_hash
        if not self.loaded:
            self.load()
        return self._cached_hash

    def get_state(self):
        if self._cached_state is not None:
            return self._cached_state
        if not self.loaded:
            self.load()
        return self._cached_state

    def get_transport_encryption(self):
        if self._cached_transport_encryption is not None:
            return self._cached_transport_encryption
        if not self.loaded:
            self.load()
        return self._cached_transport_encryption

    def get_transport_encrypted(self):
        if self._cached_transport_encrypted is not None:
            return self._cached_transport_encrypted
        if not self.loaded:
            self.load()
        return self._cached_transport_encrypted

    def signature_validated(self):
        if self._cached_signature_validated is not None:
            return self._cached_signature_validated
        if not self.loaded:
            self.load()
        return self._cached_signature_validated

    def get_signature_description(self):
        if self.signature_validated():
            return "Signature Verified"
        else:
            reason = self._cached_unverified_reason
            if reason == LXMF.LXMessage.SOURCE_UNKNOWN:
                return "Unknown Origin"
            elif reason == LXMF.LXMessage.SIGNATURE_INVALID:
                return "Invalid Signature"
            else:
                return "Unknown signature validation failure"

    def get_fields(self):
        if not self.loaded:
            self.load()

        if self.lxm and hasattr(self.lxm, "get_fields"):
            fields = self.lxm.get_fields()
            if fields and isinstance(fields, dict):
                return fields

        return {}

    def has_attachments(self):
        if self._cached_has_attachments is not None:
            return self._cached_has_attachments
        fields = self.get_fields()
        return (
            LXMF.FIELD_FILE_ATTACHMENTS in fields
            or LXMF.FIELD_IMAGE in fields
            or LXMF.FIELD_AUDIO in fields
        )

    def get_file_attachments(self):
        att_dir = self._attachment_dir()
        if att_dir and os.path.isdir(att_dir):
            manifest = self._read_attachment_manifest(att_dir)
            if manifest and "files" in manifest:
                result = []
                for entry in manifest["files"]:
                    fpath = os.path.join(att_dir, entry["stored_name"])
                    if os.path.isfile(fpath):
                        with open(fpath, "rb") as f:
                            result.append([entry["name"], f.read()])
                return result

        fields = self.get_fields()
        return fields.get(LXMF.FIELD_FILE_ATTACHMENTS, [])

    def get_image(self):
        att_dir = self._attachment_dir()
        if att_dir and os.path.isdir(att_dir):
            fpath = os.path.join(att_dir, "image")
            if os.path.isfile(fpath):
                with open(fpath, "rb") as f:
                    return f.read()

        fields = self.get_fields()
        return fields.get(LXMF.FIELD_IMAGE, None)

    def get_audio(self):
        att_dir = self._attachment_dir()
        if att_dir and os.path.isdir(att_dir):
            fpath = os.path.join(att_dir, "audio")
            if os.path.isfile(fpath):
                with open(fpath, "rb") as f:
                    return f.read()

        fields = self.get_fields()
        return fields.get(LXMF.FIELD_AUDIO, None)

    def get_attachment_file_path(self, field_type, field_index=0):
        att_dir = self._attachment_dir()
        if att_dir and os.path.isdir(att_dir):
            manifest = self._read_attachment_manifest(att_dir)
            if manifest and "files" in manifest and field_index < len(manifest["files"]):
                return os.path.join(att_dir, manifest["files"][field_index]["stored_name"])
            # Fallback for old extraction format
            if field_type == "image":
                fpath = os.path.join(att_dir, "image")
                if os.path.isfile(fpath):
                    return fpath
            elif field_type == "audio":
                fpath = os.path.join(att_dir, "audio")
                if os.path.isfile(fpath):
                    return fpath
        return None

    def _attachment_dir(self):
        try:
            app = nomadnet.NomadNetworkApp.get_shared_instance()
            msg_hash = self.get_hash()
            if msg_hash:
                return os.path.join(app.attachmentpath, RNS.hexrep(msg_hash, delimit=False))
        except Exception:
            pass
        return None

    def _read_attachment_manifest(self, att_dir):
        manifest_path = os.path.join(att_dir, "manifest")
        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path, "rb") as f:
                    return msgpack.unpackb(f.read(), raw=False)
            except Exception:
                pass
        return None

    @staticmethod
    def extract_attachments_from_lxm(lxmessage, app):
        if not hasattr(lxmessage, "get_fields"):
            return
        fields = lxmessage.get_fields()
        if not fields or not isinstance(fields, dict):
            return

        has_any = (
            LXMF.FIELD_FILE_ATTACHMENTS in fields
            or LXMF.FIELD_IMAGE in fields
            or LXMF.FIELD_AUDIO in fields
        )
        if not has_any:
            return

        msg_hash_hex = RNS.hexrep(lxmessage.hash, delimit=False)
        att_dir = os.path.join(app.attachmentpath, msg_hash_hex)
        if os.path.isdir(att_dir):
            return

        os.makedirs(att_dir)
        manifest = {"files": []}

        file_attachments = fields.get(LXMF.FIELD_FILE_ATTACHMENTS, [])
        if file_attachments:
            for idx, att in enumerate(file_attachments):
                if isinstance(att, list) and len(att) >= 2:
                    filename = str(att[0])
                    data = att[1] if isinstance(att[1], bytes) else b""
                    stored_name = "file_"+str(idx)
                    with open(os.path.join(att_dir, stored_name), "wb") as f:
                        f.write(data)
                    manifest["files"].append({"name": filename, "stored_name": stored_name, "size": len(data)})

        if LXMF.FIELD_IMAGE in fields:
            fmt, data = ConversationMessage._unpack_media_field(fields[LXMF.FIELD_IMAGE])
            if data:
                ext = ConversationMessage._ext_from_media_format(fmt, data)
                filename = "image" + ext
                stored_name = "file_"+str(len(manifest["files"]))
                with open(os.path.join(att_dir, stored_name), "wb") as f:
                    f.write(data)
                manifest["files"].append({"name": filename, "stored_name": stored_name, "size": len(data)})

        if LXMF.FIELD_AUDIO in fields:
            fmt, data = ConversationMessage._unpack_media_field(fields[LXMF.FIELD_AUDIO])
            if data:
                ext = ConversationMessage._ext_from_media_format(fmt, data, is_audio=True)
                filename = "audio" + ext
                stored_name = "file_"+str(len(manifest["files"]))
                with open(os.path.join(att_dir, stored_name), "wb") as f:
                    f.write(data)
                manifest["files"].append({"name": filename, "stored_name": stored_name, "size": len(data)})

        with open(os.path.join(att_dir, "manifest"), "wb") as f:
            f.write(msgpack.packb(manifest))

    @staticmethod
    def _unpack_media_field(field_data):
        """Normalize FIELD_IMAGE/FIELD_AUDIO which can be raw bytes or [format, bytes].
        Format element can be a string ('webp') or integer (LXMF audio mode constant)."""
        if isinstance(field_data, bytes):
            return None, field_data
        elif isinstance(field_data, list) and len(field_data) >= 2 and isinstance(field_data[1], bytes):
            return field_data[0], field_data[1]
        return None, None

    @staticmethod
    def _detect_image_ext(data):
        if not isinstance(data, bytes) or len(data) < 12:
            return ".bin"
        if data[:8] == b'\x89PNG\r\n\x1a\n':
            return ".png"
        elif data[:3] == b'\xff\xd8\xff':
            return ".jpg"
        elif data[:4] == b'GIF8':
            return ".gif"
        elif data[:4] == b'RIFF' and data[8:12] == b'WEBP':
            return ".webp"
        elif data[:4] == b'\x00\x00\x00\x1c' or data[:4] == b'\x00\x00\x00\x18':
            return ".heic"
        return ".bin"

    @staticmethod
    def _detect_audio_ext(data):
        if not isinstance(data, bytes) or len(data) < 12:
            return ".bin"
        if data[:4] == b'OggS':
            return ".ogg"
        elif data[:2] == b'\xff\xfb' or data[:3] == b'ID3':
            return ".mp3"
        elif data[:4] == b'RIFF' and data[8:12] == b'WAVE':
            return ".wav"
        elif data[:4] == b'fLaC':
            return ".flac"
        return ".bin"

    @staticmethod
    def _ext_from_media_format(fmt, data, is_audio=False):
        """Derive file extension from format identifier and data.
        fmt can be a string ('webp'), an integer (LXMF audio mode), or None."""
        if isinstance(fmt, str) and len(fmt) > 0:
            return "." + fmt.lower().strip(".")
        if isinstance(fmt, int) and is_audio:
            if fmt >= 16 and fmt <= 25:
                return ".ogg"
            elif fmt >= 1 and fmt <= 9:
                return ".c2"
        if is_audio:
            return ConversationMessage._detect_audio_ext(data)
        return ConversationMessage._detect_image_ext(data)

    @staticmethod
    def strip_attachments_from_file(file_path, app):
        try:
            with open(file_path, "rb") as f:
                container = msgpack.unpackb(f.read(), strict_map_key=False)

            lxmf_bytes = container[b"lxmf_bytes"] if b"lxmf_bytes" in container else container.get("lxmf_bytes")
            if lxmf_bytes is None:
                return

            dest_len = LXMF.LXMessage.DESTINATION_LENGTH
            sig_len  = LXMF.LXMessage.SIGNATURE_LENGTH
            header_len = 2 * dest_len + sig_len

            header = lxmf_bytes[:header_len]
            payload_bytes = lxmf_bytes[header_len:]
            payload = msgpack.unpackb(payload_bytes, strict_map_key=False)

            if len(payload) < 4 or not isinstance(payload[3], dict):
                return

            fields = payload[3]
            attachment_keys = [LXMF.FIELD_FILE_ATTACHMENTS, LXMF.FIELD_IMAGE, LXMF.FIELD_AUDIO]
            if not any(k in fields for k in attachment_keys):
                return

            # Compute message hash matching LXMF's logic
            if len(payload) > 4:
                hash_payload = msgpack.packb(payload[:4])
            else:
                hash_payload = payload_bytes
            msg_hash = RNS.Identity.full_hash(lxmf_bytes[:2*dest_len] + hash_payload)
            msg_hash_hex = RNS.hexrep(msg_hash, delimit=False)

            att_dir = os.path.join(app.attachmentpath, msg_hash_hex)
            if not os.path.isdir(att_dir):
                return

            for k in attachment_keys:
                if k in fields:
                    del fields[k]

            new_lxmf_bytes = header + msgpack.packb(payload)
            key = b"lxmf_bytes" if b"lxmf_bytes" in container else "lxmf_bytes"
            container[key] = new_lxmf_bytes

            with open(file_path, "wb") as f:
                f.write(msgpack.packb(container))

        except Exception as e:
            RNS.log("Error stripping attachments from LXM file: "+str(e), RNS.LOG_ERROR)

    def to_index_entry(self):
        return {
            "timestamp": self.timestamp,
            "sort_timestamp": self.sort_timestamp,
            "state": self._cached_state,
            "title": self._cached_title,
            "content": self._cached_content,
            "source_hash": self._cached_source_hash,
            "transport_encrypted": self._cached_transport_encrypted,
            "transport_encryption": self._cached_transport_encryption,
            "signature_validated": self._cached_signature_validated,
            "unverified_reason": self._cached_unverified_reason,
            "method": self._cached_method,
            "has_attachments": self._cached_has_attachments,
            "attachment_names": self._cached_attachment_names,
        }

    def restore_from_index(self, entry):
        self.timestamp = entry.get("timestamp")
        self.sort_timestamp = entry.get("sort_timestamp", self.sort_timestamp)
        self._cached_state = entry.get("state")
        self._cached_title = entry.get("title")
        self._cached_content = entry.get("content")
        self._cached_source_hash = entry.get("source_hash")
        self._cached_transport_encrypted = entry.get("transport_encrypted")
        self._cached_transport_encryption = entry.get("transport_encryption")
        self._cached_signature_validated = entry.get("signature_validated")
        self._cached_unverified_reason = entry.get("unverified_reason")
        self._cached_method = entry.get("method")
        self._cached_has_attachments = entry.get("has_attachments")
        self._cached_attachment_names = entry.get("attachment_names")

    @staticmethod
    def read_index(conversation_path):
        index_path = os.path.join(conversation_path, ".index")
        if os.path.isfile(index_path):
            try:
                with open(index_path, "rb") as f:
                    return msgpack.unpackb(f.read(), raw=False)
            except Exception:
                pass
        return {}

    @staticmethod
    def write_index(conversation_path, messages):
        index_path = os.path.join(conversation_path, ".index")
        index = {}
        if os.path.isfile(index_path):
            try:
                with open(index_path, "rb") as f:
                    index = msgpack.unpackb(f.read(), raw=False)
            except Exception:
                index = {}

        for msg in messages:
            if msg._cached_state is not None:
                filename = os.path.basename(msg.file_path)
                index[filename] = msg.to_index_entry()

        try:
            with open(index_path, "wb") as f:
                f.write(msgpack.packb(index))
        except Exception as e:
            RNS.log("Error writing conversation index: "+str(e), RNS.LOG_ERROR)