"""The shared Google client: one per (app, account). It refreshes the account's access token, keeps to a rate (per
second, per day), retries what Google says to retry (429, 5xx: backoff, Retry-After) and turns every failure into a
``GoogleError``. Apps never call Google another way (google.connector.client())."""
import base64
import json
import threading
import time
from collections import deque

import requests

TOKEN_URL = "https://oauth2.googleapis.com/token"
TIMEOUT = 30
RETRIES = 3

_rate_lock = threading.Lock()
_recent = {}  # (database, account id, app code) -> deque of call times (this process)


class GoogleError(Exception):
    """A Google call that did not succeed. ``auth``: the sign-in is no longer valid (connect again);
    ``retryable``: try later; ``missing_scopes``: the access the account still has to grant."""

    def __init__(self, message, status=None, auth=False, retryable=False, missing_scopes=(), code=None):
        super().__init__(message)
        self.code = code  # Google's own error code (e.g. invalid_grant)
        self.status = status
        self.auth = auth
        self.retryable = retryable
        self.missing_scopes = tuple(missing_scopes)


def token_request(data):
    """Google's token endpoint (code exchange, refresh): the JSON answer, or GoogleError."""
    try:
        response = requests.post(TOKEN_URL, data=data, timeout=TIMEOUT)
    except requests.RequestException as error:
        raise GoogleError("Google cannot be reached: %s" % error, retryable=True) from error
    payload = response.json() if response.content else {}
    if response.status_code != 200:
        raise GoogleError("Google sign-in refused: %s" % (payload.get("error_description") or payload.get("error")
                                                           or response.status_code),
                          status=response.status_code, auth=True, code=payload.get("error"))
    return payload


def email_from_id_token(id_token):
    """The Google address in the id_token Google's token endpoint returned (straight from Google over TLS)."""
    try:
        payload = (id_token or "").split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError):
        return ""
    return claims.get("email") or ""


class GoogleClient:
    """Calls to Google for one app with one account's token (google.connector.client()); an app that needs no
    account (Maps) calls with the API key instead (``key``, sent as the ``key`` parameter, no token)."""

    def __init__(self, account, app, per_second=5, per_day=2500, sleep=time.sleep, key=None):
        self.account = account
        self.app = app
        self.key = key
        self.per_second = max(1, int(per_second or 5))
        self.per_day = max(1, int(per_day or 2500))
        self.sleep = sleep

    # rate
    def _wait_turn(self):
        key = (self.app.env.cr.dbname, self.account.id if self.account else 0, self.app.code)
        while True:
            with _rate_lock:
                calls = _recent.setdefault(key, deque())
                now = time.monotonic()
                while calls and now - calls[0] > 1.0:
                    calls.popleft()
                if len(calls) < self.per_second:
                    calls.append(now)
                    break
                wait = 1.0 - (now - calls[0])
            self.sleep(max(wait, 0.01))
        if not self.app._google_count_call(self.per_day):
            raise GoogleError("The daily limit of Google calls for %s is reached." % self.app.label, status=429,
                              retryable=True)

    # calls
    def request(self, method, url, params=None, json_body=None, data=None, headers=None, raw=False, timeout=None):
        """``json_body``: sent as JSON; ``data``: a form or bytes. Returns the parsed JSON (dict), or the bytes
        when ``raw`` or not JSON."""
        last = None
        refreshed = False
        for attempt in range(RETRIES + 1):
            self._wait_turn()
            if self.key:
                call_params, call_headers = dict(params or {}, key=self.key), dict(headers or {})
            else:
                call_params = params
                call_headers = dict(headers or {}, Authorization="Bearer %s" % self.account._google_token())
            try:
                response = requests.request(method, url, params=call_params, json=json_body, data=data,
                                            timeout=timeout or TIMEOUT, headers=call_headers)
            except requests.RequestException as error:
                last = GoogleError("Google cannot be reached: %s" % self._hide_key(str(error)), retryable=True)
                self.sleep(2 ** attempt)
                continue
            if response.status_code == 401 and not refreshed and not self.key:
                refreshed = True
                self.account._google_forget_access_token()  # expired early: refresh once and try again
                continue
            if response.status_code in (429, 500, 502, 503, 504):
                last = self._error(response)
                retry_after = response.headers.get("Retry-After", "")
                self.sleep(float(retry_after) if retry_after.isdigit() else 2 ** attempt)
                continue
            if response.status_code >= 400:
                error = self._error(response)
                error.args = (self._hide_key(str(error)),) + error.args[1:]
                raise error
            if raw or not response.content:
                return response.content if raw else {}
            try:
                return response.json()
            except ValueError:
                return response.content
        raise last or GoogleError("Google did not answer.", retryable=True)

    def _hide_key(self, text):
        """The API key never goes into an error, a log or a message."""
        return text.replace(self.key, "***") if self.key else text

    def get(self, url, params=None, **kwargs):
        return self.request("GET", url, params=params, **kwargs)

    def post(self, url, json=None, data=None, **kwargs):  # noqa: A002 - the API's own word
        return self.request("POST", url, json_body=json, data=data, **kwargs)

    def put(self, url, json=None, data=None, **kwargs):  # noqa: A002
        return self.request("PUT", url, json_body=json, data=data, **kwargs)

    def patch(self, url, json=None, data=None, **kwargs):  # noqa: A002
        return self.request("PATCH", url, json_body=json, data=data, **kwargs)

    def delete(self, url, **kwargs):
        return self.request("DELETE", url, **kwargs)

    @staticmethod
    def _error(response):
        try:
            body = response.json()
            error = body.get("error")
            message = (error.get("message") if isinstance(error, dict) else error) or json.dumps(body)[:300]
        except ValueError:
            message = response.text[:300]
        status = response.status_code
        return GoogleError("Google error %s: %s" % (status, message), status=status, auth=status == 401,
                           retryable=status in (429, 500, 502, 503, 504))
