"""A small Immich client (public mode: Immich reachable from the internet, an API key): albums create, read and
rename, and the server's version for Test connection. Immich's REST API, ``x-api-key`` header."""
import requests

TIMEOUT = 15


class ImmichError(Exception):
    pass


class ImmichClient:

    def __init__(self, base_url, api_key, session=None):
        if not base_url or not api_key:
            raise ImmichError("Immich is not set up: its URL and an API key are needed")
        self.base = base_url.rstrip("/")
        self.api_key = api_key
        self.session = session or requests.Session()

    def _call(self, method, path, json=None):
        try:
            r = self.session.request(method, self.base + "/api" + path, json=json, timeout=TIMEOUT,
                                     headers={"x-api-key": self.api_key, "Accept": "application/json"})
        except requests.RequestException as error:
            raise ImmichError("Immich could not be reached: %s" % error) from error
        if r.status_code >= 400:
            raise ImmichError("Immich answered %s: %s" % (r.status_code, (r.text or "")[:200]))
        return r.json() if r.content else {}

    def ping(self):
        """{"version": "x.y.z"} (the key is checked by a call that needs it)."""
        self._call("GET", "/albums?shared=false")
        info = self._call("GET", "/server/version")
        return {"version": "%s.%s.%s" % (info.get("major", "?"), info.get("minor", "?"), info.get("patch", "?"))}

    def album_create(self, name, description=""):
        """A new album: {"id", "name"}."""
        data = self._call("POST", "/albums", json={"albumName": name, "description": description or ""})
        return {"id": data.get("id"), "name": data.get("albumName")}

    def album_get(self, album_id):
        data = self._call("GET", "/albums/%s?withoutAssets=true" % album_id)
        return {"id": data.get("id"), "name": data.get("albumName"), "count": data.get("assetCount", 0),
                "description": data.get("description") or ""}

    def album_rename(self, album_id, name):
        data = self._call("PATCH", "/albums/%s" % album_id, json={"albumName": name})
        return {"id": data.get("id"), "name": data.get("albumName")}
