# Registry of terminal-side image data
# 
# Tracks which image payloads have been transmitted to the terminal (Kitty
# image ids), de-duplicates identical image data across widgets (one payload
# transmitted once, placed many times), and counts live widget references so
# that orphaned data can be evicted from the terminal's buffers.
# 
# This module only tracks *state*; all protocol output is performed by
# ImageScreen, which reads and updates the store.
# 
# Eviction:
# 
# - Automatic, widgets unregister when closed/destroyed; the screen evicts
#   (deletes from the terminal) any registered data with no live references.
# - Explicit, the browser can call ImageScreen.purge_images() on page
#   navigation to drop everything at once.

DEFAULT_IMAGE_ID_MAX = 2 ** 32 - 1  # Protocol limit for image ids

class ImageStore(object):
    def __init__(self):
        self._entries = {}  # content key -> {"image_id", "data", "refs", "transmitted"}
        self._next_image_id = 1

    #############
    # Lifecycle #
    #############

    # Registers image data and returns (key, is_new).
    # If identical data is already registered, the existing entry is
    # reused (de-duplication) and its reference count is incremented.
    def register(self, key, data):
        entry = self._entries.get(key)
        if entry is None:
            image_id = self._next_image_id
            self._next_image_id += 1
            if image_id > DEFAULT_IMAGE_ID_MAX: raise OverflowError("image id space exhausted")
            entry = { "image_id": image_id, "data": data,
                      "refs": 0, "transmitted": False }
            self._entries[key] = entry
            is_new = True
        else: is_new = False

        entry["refs"] += 1
        return key, is_new

    # Decrements the reference count of registered data
    def unregister(self, key):
        entry = self._entries.get(key)
        if entry is None: return
        entry["refs"] = max(0, entry["refs"] - 1)

    ###########
    # Queries #
    ###########

    def entry_for(self, key): return self._entries.get(key)

    def transmitted(self): return [key for key, entry in self._entries.items() if entry["transmitted"]]

    # Returns [(key, image_id), ...] for entries with no live
    # widget references that are still present in the terminal.
    def evict_orphans(self):
        return [ (key, entry["image_id"])
                 for key, entry in self._entries.items()
                 if entry["refs"] == 0 and entry["transmitted"] ]

    ############
    # Mutation #
    ############

    def mark_transmitted(self, key):
        entry = self._entries.get(key)
        if entry is not None:
            entry["transmitted"] = True

    def mark_all_untransmitted(self):
        for entry in self._entries.values():
            entry["transmitted"] = False

    # Drops the entry for evicted data (frees the payload bytes)
    def evict(self, key): self._entries.pop(key, None)

    # Forgets all state (used by tests)
    def reset(self):
        self._entries.clear()
        self._next_image_id = 1

# Module-level singleton shared by widgets and the screen.
image_store = ImageStore()
