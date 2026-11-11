import datetime
import hashlib
import os
import tempfile
from unittest.mock import MagicMock, patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged

from ..models import r2 as r2mod
from ..models.r2 import R2Client, R2Error, sign_v4


@tagged("post_install", "-at_install")
class TestSignatureV4(TransactionCase):

    def test_aws_documented_example(self):
        """The GET Object example from the AWS Signature V4 documentation (examplebucket, test.txt, Range 0-9)."""
        auth = sign_v4(
            "GET", "examplebucket.s3.amazonaws.com", "/test.txt", {},
            {"host": "examplebucket.s3.amazonaws.com", "range": "bytes=0-9",
             "x-amz-content-sha256": r2mod.EMPTY_SHA256, "x-amz-date": "20130524T000000Z"},
            r2mod.EMPTY_SHA256, "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "us-east-1", "s3", datetime.datetime(2013, 5, 24, tzinfo=datetime.timezone.utc))
        self.assertEqual(
            auth,
            "AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request, "
            "SignedHeaders=host;range;x-amz-content-sha256;x-amz-date, "
            "Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41")


def _resp(status=200, content=b"", headers=None):
    r = MagicMock()
    r.status_code = status
    r.content = content
    r.text = content.decode(errors="replace")
    r.headers = headers or {}
    r.iter_content = lambda n: [content]
    return r


@tagged("post_install", "-at_install")
class TestR2Client(TransactionCase):

    def _client(self, responses):
        session = MagicMock()
        session.request.side_effect = responses
        return R2Client("acc123", "KEY", "SECRET", "bucket", session=session), session

    def test_endpoint_and_put_bytes(self):
        c, s = self._client([_resp()])
        digest = c.put_bytes("a/b c.txt", b"hello")
        self.assertEqual(digest, hashlib.sha256(b"hello").hexdigest())
        method, url = s.request.call_args[0][:2]
        headers = s.request.call_args[1]["headers"]
        self.assertEqual(method, "PUT")
        self.assertEqual(url, "https://acc123.r2.cloudflarestorage.com/bucket/a/b%20c.txt")
        self.assertEqual(headers["x-amz-content-sha256"], digest)
        self.assertTrue(headers["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=KEY/"))
        self.assertIn("/auto/s3/aws4_request", headers["Authorization"])

    def test_error_is_parsed(self):
        c, _s = self._client([_resp(403, b"<Error><Code>AccessDenied</Code><Message>Access Denied</Message></Error>")])
        with self.assertRaises(R2Error) as e:
            c.put_bytes("x", b"1")
        self.assertEqual(e.exception.status, 403)
        self.assertEqual(e.exception.code, "AccessDenied")

    def test_head_missing_is_none(self):
        c, _s = self._client([_resp(404)])
        self.assertIsNone(c.head("nope"))

    def test_list_pages(self):
        ns = 'xmlns="http://s3.amazonaws.com/doc/2006-03-01/"'
        page1 = ('<ListBucketResult %s><IsTruncated>true</IsTruncated><NextContinuationToken>t+2/=</NextContinuationToken>'
                 '<Contents><Key>a</Key><Size>1</Size><ETag>"e1"</ETag></Contents></ListBucketResult>' % ns).encode()
        page2 = ('<ListBucketResult %s><IsTruncated>false</IsTruncated>'
                 '<Contents><Key>b</Key><Size>2</Size><ETag>"e2"</ETag></Contents></ListBucketResult>' % ns).encode()
        c, s = self._client([_resp(content=page1), _resp(content=page2)])
        self.assertEqual([o["key"] for o in c.list("")], ["a", "b"])
        self.assertEqual(s.request.call_args[1]["params"]["continuation-token"], "t+2/=")

    def test_multipart_upload(self):
        old = (r2mod.SINGLE_PUT_MAX, r2mod.PART_SIZE)
        r2mod.SINGLE_PUT_MAX, r2mod.PART_SIZE = 10, 8
        try:
            data = os.urandom(20)
            with tempfile.NamedTemporaryFile(delete=False) as f:
                f.write(data)
            start = _resp(content=b'<InitiateMultipartUploadResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
                                  b'<UploadId>U1</UploadId></InitiateMultipartUploadResult>')
            c, s = self._client([start, _resp(headers={"ETag": '"p1"'}), _resp(headers={"ETag": '"p2"'}),
                                 _resp(headers={"ETag": '"p3"'}), _resp()])
            self.assertEqual(c.put_file("big.bin", f.name), hashlib.sha256(data).hexdigest())
            calls = s.request.call_args_list
            self.assertEqual(len(calls), 5)  # start, 3 parts (8+8+4), complete
            self.assertEqual(calls[1][1]["params"], {"partNumber": "1", "uploadId": "U1"})
            body = calls[4][1]["data"].decode()
            self.assertIn("<PartNumber>3</PartNumber><ETag>\"p3\"</ETag>", body)
        finally:
            r2mod.SINGLE_PUT_MAX, r2mod.PART_SIZE = old
            os.unlink(f.name)


@tagged("post_install", "-at_install")
class TestConnectorSettings(TransactionCase):

    def test_not_configured(self):
        self.assertFalse(self.env["cloudflare.r2"].is_configured())
        with self.assertRaises(UserError):
            self.env["cloudflare.r2"].client()

    def test_configured_client_uses_saved_bucket(self):
        ICP = self.env["ir.config_parameter"].sudo()
        for k, v in {"account_id": "acc", "r2_access_key_id": "k", "r2_secret_access_key": "s",
                     "r2_bucket": "mtbg-backups"}.items():
            ICP.set_param("cloudflare_connector." + k, v)
        self.assertTrue(self.env["cloudflare.r2"].is_configured())
        c = self.env["cloudflare.r2"].client()
        self.assertEqual((c.bucket, c.endpoint), ("mtbg-backups", "https://acc.r2.cloudflarestorage.com"))
        self.assertEqual(self.env["cloudflare.r2"].client("other").bucket, "other")

    def test_non_admin_refused(self):
        user = self.env["res.users"].create({"name": "Plain", "login": "cf_plain_user",
                                             "group_ids": [(6, 0, [self.env.ref("base.group_user").id])]})
        with self.assertRaises(AccessError):
            self.env["cloudflare.r2"].with_user(user).client()

    def test_secrets_hidden_from_non_admins(self):
        fields_ = self.env["res.config.settings"]._fields
        for name in ("cloudflare_api_token", "cloudflare_r2_access_key_id", "cloudflare_r2_secret_access_key"):
            self.assertEqual(fields_[name].groups, "base.group_system")


@tagged("post_install", "-at_install")
class TestPurge(TransactionCase):

    def setUp(self):
        super().setUp()
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("cloudflare_connector.zone_id", "ZONE")
        ICP.set_param("cloudflare_connector.api_token", "PURGE")

    def _answer(self, success=True, status=200, headers=None):
        a = MagicMock(status_code=status, headers=headers or {})
        a.json.return_value = {"success": success, "errors": [] if success else [{"message": "Bad token"}]}
        return a

    def test_everything(self):
        from ..models import connector
        with patch.object(connector.requests, "post", return_value=self._answer()) as post:
            res = self.env["cloudflare.api"].sudo().purge(everything=True)
        self.assertEqual(res, {"ok": True, "requests": 1, "error": ""})
        self.assertEqual(post.call_args[0][0], "https://api.cloudflare.com/client/v4/zones/ZONE/purge_cache")
        self.assertEqual(post.call_args[1]["json"], {"purge_everything": True})
        self.assertEqual(post.call_args[1]["headers"]["Authorization"], "Bearer PURGE")

    def test_batches_of_30(self):
        from ..models import connector
        urls = ["https://www.example.com/p%s" % i for i in range(65)]
        with patch.object(connector.requests, "post", return_value=self._answer()) as post:
            res = self.env["cloudflare.api"].sudo().purge(urls=urls, prefixes=["www.example.com/tours"])
        self.assertTrue(res["ok"])
        sizes = [len(c[1]["json"].get("files", c[1]["json"].get("prefixes", []))) for c in post.call_args_list]
        self.assertEqual(sizes, [30, 30, 5, 1])

    def test_rate_limit_waits_and_retries(self):
        from ..models import connector
        answers = [self._answer(False, 429, {"Retry-After": "1"}), self._answer()]
        with patch.object(connector.requests, "post", side_effect=answers) as post, \
                patch.object(connector.time, "sleep") as sleep:
            res = self.env["cloudflare.api"].sudo().purge(everything=True)
        self.assertTrue(res["ok"])
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(1.0)

    def test_refused_and_unreachable_never_raise(self):
        from ..models import connector
        with patch.object(connector.requests, "post", return_value=self._answer(False, 403)):
            res = self.env["cloudflare.api"].sudo().purge(everything=True)
        self.assertEqual((res["ok"], res["error"]), (False, "Cloudflare refused: Bad token"))
        with patch.object(connector.requests, "post", side_effect=connector.requests.ConnectionError("down")):
            res = self.env["cloudflare.api"].sudo().purge(everything=True)
        self.assertFalse(res["ok"])
        self.assertIn("could not be reached", res["error"])

    def test_not_set_up(self):
        self.env["ir.config_parameter"].sudo().set_param("cloudflare_connector.api_token", "")
        res = self.env["cloudflare.api"].sudo().purge(everything=True)
        self.assertFalse(res["ok"])
        self.assertIn("Set up Cloudflare", res["error"])


@tagged("post_install", "-at_install")
class TestPresign(TransactionCase):

    def test_aws_documented_presigned_url(self):
        """The presigned GET example from the AWS Signature V4 documentation (examplebucket, test.txt, 86400 s)."""
        q = r2mod.presign_v4("examplebucket.s3.amazonaws.com", "/test.txt", "AKIAIOSFODNN7EXAMPLE",
                             "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "us-east-1", "s3",
                             datetime.datetime(2013, 5, 24, tzinfo=datetime.timezone.utc), 86400)
        self.assertTrue(q.endswith(
            "X-Amz-Signature=aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404"), q)

    def test_client_link(self):
        c = R2Client("acc", "KEY", "SECRET", "bucket")
        url = c.presign_get("snapshots/db/x.dump", 3600, filename="x.dump")
        self.assertTrue(url.startswith("https://acc.r2.cloudflarestorage.com/bucket/snapshots/db/x.dump?"))
        self.assertIn("X-Amz-Expires=3600", url)
        self.assertIn("response-content-disposition=attachment%3B%20filename%3D%22x.dump%22", url)
        self.assertIn("X-Amz-Signature=", url)
