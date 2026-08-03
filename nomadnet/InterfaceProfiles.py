import os
import threading

import RNS
import RNS.vendor.umsgpack as msgpack


class InterfaceProfiles:
    VERSION = 1

    def __init__(self, app):
        self.app = app
        self.path = os.path.join(app.storagepath, "interface_profiles.msgpack")
        self._lock = threading.Lock()
        self.profiles = []
        self.load()

    def load(self):
        self.profiles = []
        self.default_members = None
        try:
            if not os.path.isfile(self.path):
                return
            with open(self.path, "rb") as f:
                data = msgpack.unpackb(f.read())
            if not isinstance(data, dict):
                return
            clean = []
            seen = set()
            for p in data.get("profiles") or []:
                if not isinstance(p, dict):
                    continue
                pid = str(p.get("id") or "")
                if not pid or pid in seen:
                    continue
                members = [str(m) for m in (p.get("members") or []) if isinstance(m, (str, bytes))]
                clean.append({"id": pid, "name": str(p.get("name") or ""), "members": members})
                seen.add(pid)
            self.profiles = clean
            dm = data.get("default_members")
            self.default_members = [str(m) for m in dm] if isinstance(dm, list) else None
        except Exception as e:
            RNS.log("Could not load interface profiles: "+str(e), RNS.LOG_ERROR)
            self.profiles = []
            self.default_members = None

    def save(self):
        with self._lock:
            tmp = self.path + ".tmp"
            try:
                payload = {
                    "version": InterfaceProfiles.VERSION,
                    "profiles": [{"id": p["id"], "name": p["name"], "members": list(p["members"])} for p in self.profiles],
                    "default_members": self.default_members,
                }
                with open(tmp, "wb") as f:
                    f.write(msgpack.packb(payload))
                    f.flush()
                    try: os.fsync(f.fileno())
                    except Exception: pass
                os.replace(tmp, self.path)
            except Exception as e:
                RNS.log("Could not save interface profiles: "+str(e), RNS.LOG_ERROR)
                try: os.remove(tmp)
                except Exception: pass

    def _interfaces(self):
        try:
            return self.app.rns.config["interfaces"]
        except Exception:
            return {}

    def interface_names(self):
        try:
            return list(self._interfaces().keys())
        except Exception:
            return []

    def _is_enabled(self, iface):
        return str(iface.get("enabled")).lower() not in ('false', 'off', 'no', '0') and \
               str(iface.get("interface_enabled")).lower() not in ('false', 'off', 'no', '0')

    def enabled_set(self):
        interfaces = self._interfaces()
        result = set()
        for name in interfaces:
            try:
                if self._is_enabled(interfaces[name]):
                    result.add(name)
            except Exception:
                pass
        return result

    def get(self, pid):
        for p in self.profiles:
            if p["id"] == pid:
                return p
        return None

    def members_existing(self, p):
        existing = set(self.interface_names())
        return set(m for m in p["members"] if m in existing)

    def active_profile_id(self):
        enabled = self.enabled_set()
        for p in self.profiles:
            if self.members_existing(p) == enabled:
                return p["id"]
        return None

    def profiles_for(self, iface_name):
        return [p for p in self.profiles if iface_name in p["members"]]

    def label_for(self, iface_name):
        names = [p["name"] or p["id"] for p in self.profiles_for(iface_name)]
        return ", ".join(names) if names else None

    def member_count(self, p):
        return len(self.members_existing(p))

    def _new_id(self):
        while True:
            pid = os.urandom(4).hex()
            if not self.get(pid):
                return pid

    def create(self, name):
        pid = self._new_id()
        self.profiles.append({"id": pid, "name": name or "Profile", "members": []})
        self.save()
        return pid

    def save_current_as_profile(self, name):
        pid = self.create(name)
        self.set_members(pid, sorted(self.enabled_set()))
        return pid

    def rename(self, pid, name):
        p = self.get(pid)
        if p is not None and name:
            p["name"] = name
            self.save()

    def delete(self, pid):
        self.profiles = [p for p in self.profiles if p["id"] != pid]
        self.save()

    def set_members(self, pid, members):
        p = self.get(pid)
        if p is not None:
            valid = set(self.interface_names())
            seen = set()
            ordered = []
            for m in members:
                if m in valid and m not in seen:
                    ordered.append(m)
                    seen.add(m)
            p["members"] = ordered
            self.save()

    def set_interface_profiles(self, iface_name, profile_ids):
        pset = set(profile_ids)
        for p in self.profiles:
            if p["id"] in pset:
                if iface_name not in p["members"]:
                    p["members"].append(iface_name)
            elif iface_name in p["members"]:
                p["members"] = [m for m in p["members"] if m != iface_name]
        self.save()

    def _apply_members(self, members):
        existing = set(self.interface_names())
        members = set(m for m in members if m in existing)
        interfaces = self._interfaces()
        try:
            for name in interfaces:
                value = "true" if name in members else "false"
                interfaces[name]["interface_enabled"] = value
                if "enabled" in interfaces[name]:
                    interfaces[name]["enabled"] = value
            self.app.rns.config.write()
            return True
        except Exception as e:
            RNS.log("Could not apply interface profile: "+str(e), RNS.LOG_ERROR)
            return False

    def select_profile(self, pid):
        p = self.get(pid)
        if p is None:
            return False
        return self._apply_members(self.members_existing(p))

    def select_default(self):
        if self.default_members is None:
            return False
        return self._apply_members(set(self.default_members))

    def update_default_if_custom(self):
        # Remember the live enabled-set as "Default" whenever it matches no named
        # profile -- i.e. it's the user's manual setup. Only relevant once profiles exist.
        if not self.profiles:
            return
        enabled = self.enabled_set()
        matches_named = any(self.members_existing(p) == enabled for p in self.profiles)
        if matches_named and self.default_members is not None:
            return
        new_default = sorted(enabled)
        if self.default_members != new_default:
            self.default_members = new_default
            self.save()

    def remove_interface(self, iface_name):
        changed = False
        for p in self.profiles:
            if iface_name in p["members"]:
                p["members"] = [m for m in p["members"] if m != iface_name]
                changed = True
        if changed:
            self.save()

    def rename_interface(self, old_name, new_name):
        changed = False
        for p in self.profiles:
            if old_name in p["members"]:
                p["members"] = [new_name if m == old_name else m for m in p["members"]]
                changed = True
        if changed:
            self.save()

    def prune(self):
        valid = set(self.interface_names())
        changed = False
        for p in self.profiles:
            pruned = [m for m in p["members"] if m in valid]
            if len(pruned) != len(p["members"]):
                p["members"] = pruned
                changed = True
        if changed:
            self.save()
