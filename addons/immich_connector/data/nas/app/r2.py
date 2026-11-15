"""Cloudflare R2 client: the S3-compatible API signed with AWS Signature Version 4.

Pure Python on top of ``requests``: no boto3. Large files go up in parts (multipart upload) and are streamed from
disk, so memory stays flat whatever the file size. Every upload sends the SHA-256 of what it sends; R2 refuses a
body that does not match, so a stored object is exactly the bytes that were read.

This module names no Odoo model: ``cloudflare.r2`` (models/connector.py) builds a client from the saved settings.
"""
import datetime
import hashlib
import hmac
import logging
import os
import re
from urllib.parse import quote
from xml.etree import ElementTree

import requests

_logger = logging.getLogger(__name__)

EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
SINGLE_PUT_MAX = 64 * 1024 * 1024  # above this, multipart
PART_SIZE = 64 * 1024 * 1024  # R2: 5 MiB .. 5 GiB per part, all but the last the same size
READ_CHUNK = 1024 * 1024
TIMEOUT = (15, 300)
S3_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"


class R2Error(Exception):
    """An R2 call that did not succeed: ``status`` is the HTTP status (0 = no answer), ``code`` the S3 error code."""

    def __init__(self, message, status=0, code=""):
        super().__init__(message)
        self.status = status
        self.code = code


def _sha256_file(path, start=0, length=None):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        f.seek(start)
        left = length
        while True:
            n = READ_CHUNK if left is None else min(READ_CHUNK, left)
            if n <= 0:
                break
            chunk = f.read(n)
            if not chunk:
                break
            h.update(chunk)
            if left is not None:
                left -= len(chunk)
    return h.hexdigest()


class _FileSlice:
    """``length`` bytes of ``path`` from ``start`` as a sized, readable body: requests streams it with a plain
    Content-Length (a generator would be sent chunked, which S3/R2 refuse next to a Content-Length)."""

    def __init__(self, path, start, length):
        self._f = open(path, "rb")
        self._f.seek(start)
        self._left = length
        self._length = length

    def __len__(self):
        return self._length

    def read(self, n=-1):
        if self._left <= 0:
            self._f.close()
            return b""
        n = self._left if n is None or n < 0 else min(n, self._left)
        chunk = self._f.read(n)
        self._left -= len(chunk)
        if not chunk or self._left <= 0:
            self._f.close()
        return chunk

    def close(self):
        self._f.close()


def _file_slice(path, start, length):
    return _FileSlice(path, start, length)


def _uri_encode(value, safe="-_.~"):
    return quote(value, safe=safe)


def sign_v4(method, host, path, query, headers, payload_sha256, access_key, secret_key, region, service, now):
    """Return the ``Authorization`` header for a request (AWS Signature Version 4).

    ``path`` is the already-encoded request path, ``query`` a dict of query parameters (unencoded), ``headers`` the
    headers to sign (``host`` and ``x-amz-*`` must be among them). ``now`` is a UTC datetime.
    """
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    day = now.strftime("%Y%m%d")
    canon_query = "&".join(
        "%s=%s" % (_uri_encode(str(k)), _uri_encode(str(v))) for k, v in sorted((query or {}).items()))
    lower = {k.lower().strip(): " ".join(str(v).strip().split()) for k, v in headers.items()}
    signed = ";".join(sorted(lower))
    canon_headers = "".join("%s:%s\n" % (k, lower[k]) for k in sorted(lower))
    canonical = "\n".join([method, path, canon_query, canon_headers, signed, payload_sha256])
    scope = "%s/%s/%s/aws4_request" % (day, region, service)
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])

    def _h(key, msg):
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    key = _h(_h(_h(_h(("AWS4" + secret_key).encode(), day), region), service), "aws4_request")
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    return "AWS4-HMAC-SHA256 Credential=%s/%s, SignedHeaders=%s, Signature=%s" % (access_key, scope, signed, signature)


def presign_v4(host, path, access_key, secret_key, region, service, now, expires, extra_query=None):
    """A presigned GET URL's query string (AWS Signature Version 4, query-string signing, UNSIGNED-PAYLOAD)."""
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    day = now.strftime("%Y%m%d")
    scope = "%s/%s/%s/aws4_request" % (day, region, service)
    query = dict(extra_query or {})
    query.update({"X-Amz-Algorithm": "AWS4-HMAC-SHA256", "X-Amz-Credential": "%s/%s" % (access_key, scope),
                  "X-Amz-Date": amz_date, "X-Amz-Expires": str(int(expires)), "X-Amz-SignedHeaders": "host"})
    canon_query = "&".join("%s=%s" % (_uri_encode(k), _uri_encode(str(v))) for k, v in sorted(query.items()))
    canonical = "\n".join(["GET", path, canon_query, "host:%s\n" % host, "host", "UNSIGNED-PAYLOAD"])
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])

    def _h(key, msg):
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    key = _h(_h(_h(_h(("AWS4" + secret_key).encode(), day), region), service), "aws4_request")
    return canon_query + "&X-Amz-Signature=" + hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()


class R2Client:
    """One R2 bucket. ``account_id`` gives the endpoint ``https://<account_id>.r2.cloudflarestorage.com``."""

    region = "auto"
    service = "s3"

    def __init__(self, account_id, access_key_id, secret_access_key, bucket, endpoint=None, session=None):
        if not (account_id or endpoint) or not access_key_id or not secret_access_key or not bucket:
            raise R2Error("R2 is not set up: account ID, access key, secret and bucket are all needed")
        self.endpoint = (endpoint or "https://%s.r2.cloudflarestorage.com" % account_id).rstrip("/")
        self.host = re.sub(r"^https?://", "", self.endpoint).split("/")[0]
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.bucket = bucket
        self.session = session or requests.Session()

    # ------------------------------------------------------------------ low level
    def _path(self, key=""):
        return "/%s/%s" % (_uri_encode(self.bucket), _uri_encode(key.lstrip("/"), safe="-_.~/")) if key \
            else "/%s" % _uri_encode(self.bucket)

    def _request(self, method, key="", query=None, body=None, payload_sha256=EMPTY_SHA256, headers=None,
                 stream=False, ok=(200,)):
        now = datetime.datetime.now(datetime.timezone.utc)
        path = self._path(key)
        sign_headers = {"host": self.host, "x-amz-content-sha256": payload_sha256,
                        "x-amz-date": now.strftime("%Y%m%dT%H%M%SZ")}
        for k, v in (headers or {}).items():
            sign_headers[k.lower()] = v
        auth = sign_v4(method, self.host, path, query, sign_headers, payload_sha256, self.access_key_id,
                       self.secret_access_key, self.region, self.service, now)
        send = dict(sign_headers, Authorization=auth)
        send.pop("host")
        try:
            resp = self.session.request(method, self.endpoint + path, params=query, data=body, headers=send,
                                        timeout=TIMEOUT, stream=stream)
        except requests.RequestException as e:
            raise R2Error("R2 did not answer: %s" % e) from e
        if resp.status_code not in ok:
            code, message = "", (resp.text or "")[:500]
            try:
                root = ElementTree.fromstring(resp.content)
                code = root.findtext("Code") or ""
                message = root.findtext("Message") or message
            except ElementTree.ParseError:
                pass
            raise R2Error("R2 %s %s: %s %s" % (method, key or self.bucket, resp.status_code, message or code),
                          resp.status_code, code)
        return resp

    # ------------------------------------------------------------------ objects
    def put_bytes(self, key, data, content_type="application/octet-stream"):
        """Store ``data`` (bytes) at ``key``; returns its SHA-256 (hex)."""
        digest = hashlib.sha256(data).hexdigest()
        self._request("PUT", key, body=data, payload_sha256=digest,
                      headers={"content-type": content_type, "content-length": str(len(data))})
        return digest

    def put_file(self, key, path, content_type="application/octet-stream"):
        """Upload the file at ``path`` to ``key`` (streamed; multipart above 64 MiB); returns its SHA-256 (hex)."""
        size = os.path.getsize(path)
        if size <= SINGLE_PUT_MAX:
            digest = _sha256_file(path)
            self._request("PUT", key, body=_file_slice(path, 0, size), payload_sha256=digest,
                          headers={"content-type": content_type, "content-length": str(size)})
            return digest
        return self._put_multipart(key, path, size, content_type)

    def _put_multipart(self, key, path, size, content_type):
        resp = self._request("POST", key, query={"uploads": ""}, headers={"content-type": content_type})
        upload_id = ElementTree.fromstring(resp.content).findtext(S3_NS + "UploadId") \
            or ElementTree.fromstring(resp.content).findtext("UploadId")
        if not upload_id:
            raise R2Error("R2 did not start the upload of %s" % key)
        whole = hashlib.sha256()
        parts = []
        try:
            number, start = 1, 0
            while start < size:
                length = min(PART_SIZE, size - start)
                part_digest = _sha256_file(path, start, length)
                with open(path, "rb") as f:  # the whole-file digest, read once alongside the parts
                    f.seek(start)
                    left = length
                    while left > 0:
                        chunk = f.read(min(READ_CHUNK, left))
                        if not chunk:
                            break
                        whole.update(chunk)
                        left -= len(chunk)
                r = self._request("PUT", key, query={"partNumber": str(number), "uploadId": upload_id},
                                  body=_file_slice(path, start, length), payload_sha256=part_digest,
                                  headers={"content-length": str(length)})
                parts.append((number, r.headers.get("ETag", "")))
                number += 1
                start += length
            xml = "<CompleteMultipartUpload>%s</CompleteMultipartUpload>" % "".join(
                "<Part><PartNumber>%d</PartNumber><ETag>%s</ETag></Part>" % (n, etag) for n, etag in parts)
            body = xml.encode()
            self._request("POST", key, query={"uploadId": upload_id}, body=body,
                          payload_sha256=hashlib.sha256(body).hexdigest(),
                          headers={"content-type": "application/xml", "content-length": str(len(body))})
        except Exception:
            try:
                self._request("DELETE", key, query={"uploadId": upload_id}, ok=(200, 204))
            except R2Error:
                _logger.warning("R2: could not abort the upload of %s", key)
            raise
        return whole.hexdigest()

    def get_file(self, key, path):
        """Download ``key`` into ``path``; returns its SHA-256 (hex)."""
        resp = self._request("GET", key, stream=True)
        h = hashlib.sha256()
        tmp = path + ".part"
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(READ_CHUNK):
                f.write(chunk)
                h.update(chunk)
        os.replace(tmp, path)
        return h.hexdigest()

    def get_bytes(self, key):
        return self._request("GET", key).content

    def presign_get(self, key, expires=3600, filename=None):
        """A private download link to ``key`` that works for ``expires`` seconds (max 7 days), no login needed.
        ``filename``: the name the browser saves it under."""
        expires = max(1, min(int(expires), 7 * 24 * 3600))
        extra = {"response-content-disposition": 'attachment; filename="%s"' % filename} if filename else None
        query = presign_v4(self.host, self._path(key), self.access_key_id, self.secret_access_key, self.region,
                           self.service, datetime.datetime.now(datetime.timezone.utc), expires, extra)
        return "%s%s?%s" % (self.endpoint, self._path(key), query)

    def head(self, key):
        """The object's size and ETag, or None when it does not exist."""
        try:
            r = self._request("HEAD", key)
        except R2Error as e:
            if e.status == 404:
                return None
            raise
        return {"size": int(r.headers.get("Content-Length") or 0), "etag": r.headers.get("ETag", "").strip('"')}

    def delete(self, key):
        self._request("DELETE", key, ok=(200, 204))

    def list(self, prefix=""):
        """Every object under ``prefix``: a list of dicts (key, size, etag, modified)."""
        out, token = [], None
        while True:
            q = {"list-type": "2", "max-keys": "1000"}
            if prefix:
                q["prefix"] = prefix
            if token:
                q["continuation-token"] = token
            root = ElementTree.fromstring(self._request("GET", query=q).content)
            for c in list(root.iter(S3_NS + "Contents")) + list(root.iter("Contents")):
                out.append({
                    "key": c.findtext(S3_NS + "Key") or c.findtext("Key"),
                    "size": int(c.findtext(S3_NS + "Size") or c.findtext("Size") or 0),
                    "etag": (c.findtext(S3_NS + "ETag") or c.findtext("ETag") or "").strip('"'),
                    "modified": c.findtext(S3_NS + "LastModified") or c.findtext("LastModified"),
                })
            truncated = (root.findtext(S3_NS + "IsTruncated") or root.findtext("IsTruncated") or "") == "true"
            token = root.findtext(S3_NS + "NextContinuationToken") or root.findtext("NextContinuationToken")
            if not truncated or not token:
                return out

    def check(self):
        """Write, read back and delete a small probe object: what Test connection does."""
        key = "_cloudflare_connector_check/%s.txt" % datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y%m%dT%H%M%S%f")
        data = b"cloudflare_connector check"
        self.put_bytes(key, data, "text/plain")
        try:
            if self.get_bytes(key) != data:
                raise R2Error("R2 returned different bytes for the check object")
        finally:
            self.delete(key)
        return True
