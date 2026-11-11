"""Meta's Graph API for every app of the Meta connector: the app, Facebook login (OAuth) and long-lived tokens, the
user's Pages with their Instagram accounts, webhooks, conversations and their messages (history), sending, profiles,
an Instagram account's posts. Plain functions around ``requests``; errors raise ``GraphError``."""
import hashlib
import hmac
import json
from urllib.parse import urlencode

import requests

VERSION = "v21.0"
BASE = "https://graph.facebook.com/%s" % VERSION
DIALOG = "https://www.facebook.com/%s/dialog/oauth" % VERSION
TIMEOUT = 30
# the connector's own (the Pages, their Instagram accounts and posts); apps add theirs (meta.connector._meta_scopes)
SCOPES = ["pages_show_list", "pages_read_engagement", "business_management", "instagram_basic"]
PAGE_FIELDS = ["messages", "messaging_postbacks", "message_deliveries", "message_reads", "message_echoes",
               "message_reactions"]
INSTAGRAM_FIELDS = ["messages", "messaging_postbacks", "message_reactions", "messaging_seen"]
# posting (an app's Posting use, e.g. Marketing): a photo post on the Page, a picture on Instagram
POST_SCOPES = {"facebook": ["pages_manage_posts"], "instagram": ["instagram_content_publish"]}
# what the login asks for when an app posts: the posting permissions and the reading ones they need
POSTING_SCOPES = ["pages_show_list", "pages_read_engagement", "pages_manage_posts", "instagram_basic",
                  "instagram_content_publish"]
# the token or its permissions are the problem: connect again
AUTH_CODES = {190, 102, 10, 200, 3, 463, 467}
# "sent outside of allowed window" (Messenger, Instagram)
WINDOW_SUBCODES = {2018278, 2534022}


class GraphError(Exception):
    def __init__(self, message, code=None, subcode=None):
        super().__init__(message)
        self.code = code
        self.subcode = subcode

    @property
    def auth(self):
        return self.code in AUTH_CODES and self.subcode not in WINDOW_SUBCODES

    @property
    def window(self):
        """Outside the time Meta allows an answer."""
        return self.subcode in WINDOW_SUBCODES


def _call(method, path, token=None, params=None, data=None, files=None, json_body=None, timeout=TIMEOUT):
    params = dict(params or {})
    if token:
        params["access_token"] = token
    url = path if path.startswith("http") else BASE + path
    try:
        response = requests.request(method, url, params=params, data=data, files=files, json=json_body,
                                    timeout=timeout)
    except requests.RequestException as error:
        raise GraphError("Meta cannot be reached: %s" % error) from error
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.status_code >= 400 or (isinstance(payload, dict) and "error" in payload):
        error = (payload or {}).get("error") or {}
        message = error.get("error_user_msg") or error.get("message") or "HTTP %s" % response.status_code
        raise GraphError("Meta: %s" % message, code=error.get("code"), subcode=error.get("error_subcode"))
    return payload


def _pages(path, token, params, limit=None):
    """Every item of a paginated list (``limit``: stop after that many)."""
    out, url = [], path
    while url:
        payload = _call("GET", url, token, params=params)
        out += payload.get("data", [])
        if limit and len(out) >= limit:
            return out[:limit]
        url = (payload.get("paging") or {}).get("next")
        params, token = None, None  # the next page's address carries them
    return out


# ------------------------------------------------------------------ the app and the login
def app_token(app_id, app_secret):
    return "%s|%s" % (app_id, app_secret)


def app_info(app_id, app_secret):
    """The app's name (and a check of its ID and secret)."""
    return _call("GET", "/%s" % app_id, app_token(app_id, app_secret), params={"fields": "id,name"})


def login_url(app_id, redirect_uri, state, config_id=None, scopes=None):
    params = {"client_id": app_id, "redirect_uri": redirect_uri, "state": state, "response_type": "code"}
    if config_id:
        params["config_id"] = config_id
    else:
        params["scope"] = ",".join(scopes or SCOPES)
    return "%s?%s" % (DIALOG, urlencode(params))


def exchange_code(app_id, app_secret, redirect_uri, code):
    """The login's code -> a short-lived user token."""
    return _call("GET", "/oauth/access_token", params={
        "client_id": app_id, "client_secret": app_secret, "redirect_uri": redirect_uri, "code": code})["access_token"]


def long_lived(app_id, app_secret, token):
    """A user token -> a long-lived one: (token, seconds left or None). Page tokens read with it never expire."""
    result = _call("GET", "/oauth/access_token", params={
        "grant_type": "fb_exchange_token", "client_id": app_id, "client_secret": app_secret,
        "fb_exchange_token": token})
    return result["access_token"], result.get("expires_in")


def debug_token(app_id, app_secret, token):
    """{"is_valid", "expires_at", "scopes", "user_id", ...} of a token."""
    return _call("GET", "/debug_token", app_token(app_id, app_secret), params={"input_token": token}).get("data", {})


def me(token):
    return _call("GET", "/me", token, params={"fields": "id,name"})


def pages(user_token):
    """The Pages the user manages, with their tokens and Instagram professional accounts."""
    fields = ("id,name,access_token,tasks,picture{url},"
              "instagram_business_account{id,username,name,profile_picture_url}")
    return _pages("/me/accounts", user_token, {"fields": fields, "limit": 100})


# ------------------------------------------------------------------ webhooks
def set_app_webhook(app_id, app_secret, obj, callback_url, verify_token, fields):
    """The app's webhook for ``obj`` ("page" or "instagram")."""
    return _call("POST", "/%s/subscriptions" % app_id, app_token(app_id, app_secret), data={
        "object": obj, "callback_url": callback_url, "verify_token": verify_token, "fields": ",".join(fields),
        "include_values": "true"})


def subscribe_page(page_id, page_token, fields=PAGE_FIELDS):
    """The Page sends its (and its Instagram account's) message events to the app."""
    return _call("POST", "/%s/subscribed_apps" % page_id, page_token, data={"subscribed_fields": ",".join(fields)})


def page_info(page_id, page_token):
    return _call("GET", "/%s" % page_id, page_token, params={"fields": "id,name"})


# ------------------------------------------------------------------ conversations (history and catch-up)
MESSAGE_FIELDS = ("id,created_time,from,to,message,sticker,shares{link,name},story,is_unsupported,"
                  "attachments{id,mime_type,name,size,file_url,image_data{url},video_data{url}}")


def _too_much(error):
    """Meta's "Please reduce the amount of data you're asking for" (code 1): ask for fewer at a time."""
    return error.code == 1 or "reduce the amount of data" in str(error).lower()


def _shrinking(fetch, limit):
    """``fetch(limit)``, with half the limit again (down to 1) while Meta says it is too much."""
    while True:
        try:
            return fetch(limit)
        except GraphError as error:
            if not _too_much(error) or limit <= 1:
                raise
            limit = max(1, limit // 2)


def conversations(page_id, page_token, platform, after=None, limit=None):
    """One page of the Page's conversations on ``platform`` (messenger / instagram), newest first:
    (conversations, cursor of the next page or None). Small pages (Instagram's are heavy for Meta)."""
    def fetch(size):
        params = {"platform": platform, "fields": "id,updated_time,participants", "limit": size}
        if after:
            params["after"] = after
        return _call("GET", "/%s/conversations" % page_id, page_token, params=params)
    payload = _shrinking(fetch, limit or (10 if platform == "instagram" else 25))
    cursors = (payload.get("paging") or {})
    return payload.get("data", []), (cursors.get("cursors") or {}).get("after") if cursors.get("next") else None


def conversation_messages(conversation_id, page_token, after=None, limit=None):
    """One page of a conversation's messages, newest first: (messages, cursor of the next page or None), read
    from the conversation's own messages list (not nested in the conversation: lighter for Meta). Instagram gives
    the content of the 20 newest messages only."""
    def fetch(size):
        params = {"fields": MESSAGE_FIELDS, "limit": size}
        if after:
            params["after"] = after
        return _call("GET", "/%s/messages" % conversation_id, page_token, params=params)
    payload = _shrinking(fetch, limit or 20)
    paging = payload.get("paging") or {}
    return payload.get("data", []), (paging.get("cursors") or {}).get("after") if paging.get("next") else None


def message(message_id, page_token):
    return _call("GET", "/%s" % message_id, page_token, params={"fields": MESSAGE_FIELDS})


def profile(user_id, page_token, platform):
    """The customer's name (and username on Instagram); {} when Meta does not tell."""
    fields = "name,username,profile_pic" if platform == "instagram" else "first_name,last_name,name,profile_pic"
    try:
        return _call("GET", "/%s" % user_id, page_token, params={"fields": fields})
    except GraphError:
        return {}


# ------------------------------------------------------------------ sending
def send(page_id, page_token, recipient_id, text=None, file=None, reply_to=None, tag=None, reply_to_top=False):
    """Send text or one file ({name, mimetype, data}) to ``recipient_id`` (PSID / IGSID). Returns the message id.

    ``reply_to`` (a message id) quotes the message answered. Instagram wants it next to ``message``
    (``reply_to_top``, on text or a file); otherwise it goes inside the text ``message``, as before."""
    body = {"recipient": json.dumps({"id": recipient_id}),
            "messaging_type": "MESSAGE_TAG" if tag else "RESPONSE"}
    if tag:
        body["tag"] = tag
    if reply_to and reply_to_top:
        body["reply_to"] = json.dumps({"mid": reply_to})
    files = None
    if file:
        mimetype = file.get("mimetype") or "application/octet-stream"
        kind = next((k for prefix, k in (("image/", "image"), ("video/", "video"), ("audio/", "audio"))
                     if mimetype.startswith(prefix)), "file")
        body["message"] = json.dumps({"attachment": {"type": kind, "payload": {"is_reusable": False}}})
        files = {"filedata": (file["name"], file["data"], mimetype)}
    else:
        message_body = {"text": text}
        if reply_to and not reply_to_top:
            message_body["reply_to"] = {"mid": reply_to}
        body["message"] = json.dumps(message_body)
    result = _call("POST", "/%s/messages" % page_id, page_token, data=body, files=files, timeout=120)
    return result.get("message_id")


# ------------------------------------------------------------------ Instagram posts
MEDIA_FIELDS = ("id,caption,media_type,media_url,thumbnail_url,permalink,timestamp,"
                "children{media_type,media_url,thumbnail_url}")


def instagram_account(ig_id, page_token):
    """An Instagram professional account's profile (with its Page's token): username, name, photo, followers, posts."""
    return _call("GET", "/%s" % ig_id, page_token,
                 params={"fields": "id,username,name,profile_picture_url,followers_count,media_count"})


def media(ig_id, page_token, limit=24):
    """The newest posts of an Instagram professional account (with its Page's token), newest first."""
    return _call("GET", "/%s/media" % ig_id, page_token, params={"fields": MEDIA_FIELDS, "limit": limit}).get("data", [])


def download(url):
    """An attachment's bytes and type (Meta's file addresses need no token)."""
    try:
        response = requests.get(url, timeout=120)
    except requests.RequestException as error:
        raise GraphError("Meta cannot be reached: %s" % error) from error
    if response.status_code >= 400:
        raise GraphError("Meta refused the file (%s)." % response.status_code)
    return response.content, (response.headers.get("Content-Type") or "").split(";")[0] or None


def signature_ok(app_secret, body, header):
    """X-Hub-Signature-256 of a webhook call, checked with the app secret."""
    if not app_secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len("sha256="):])


def page_photo_post(page_id, page_token, image_url, caption):
    """A photo post on the Page (the picture at ``image_url``, a public address): {"id", "post_id"}."""
    return _call("POST", "/%s/photos" % page_id, page_token, data={"url": image_url, "caption": caption or ""})


def page_photo_story(page_id, page_token, image_url):
    """A photo story on the Page: the picture uploaded unpublished, then posted as a story. {"post_id", ...}."""
    photo = _call("POST", "/%s/photos" % page_id, page_token, data={"url": image_url, "published": "false"})
    return _call("POST", "/%s/photo_stories" % page_id, page_token, data={"photo_id": photo["id"]})


def ig_publish(ig_id, page_token, image_url, caption, wait=2.0, tries=5, story=False):
    """A picture posted on the Instagram account: Meta's two steps, a media container (the picture at ``image_url``,
    public) then its publishing (once Meta has it ready). {"id"} of the post. ``story``: an Instagram story (no
    caption: a story shows none)."""
    import time
    data = {"image_url": image_url, "media_type": "STORIES"} if story else {"image_url": image_url,
                                                                            "caption": caption or ""}
    container = _call("POST", "/%s/media" % ig_id, page_token, data=data)
    for attempt in range(tries):
        try:
            return _call("POST", "/%s/media_publish" % ig_id, page_token, data={"creation_id": container["id"]})
        except GraphError as error:
            # "Media ID is not available" / not ready yet: a moment more
            if attempt == tries - 1 or error.code not in (9007, 2207027, None):
                raise
            time.sleep(wait)
    return {}


def permalink(object_id, page_token):
    """The public address of a post (Page post or Instagram media), or ""."""
    try:
        payload = _call("GET", "/%s" % object_id, page_token, params={"fields": "permalink_url,permalink"})
    except GraphError:
        return ""
    return payload.get("permalink_url") or payload.get("permalink") or ""
