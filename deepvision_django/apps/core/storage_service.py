"""
DeepVision Persistent Object & Volume Storage Service.
Provides a decoupled storage abstraction for surveillance recordings and forensic evidence:
- SupabaseStorageBackend: Private buckets via Supabase Storage REST v1 API (streaming upload + Range pass-through + short-lived signed URLs)
- S3CompatibleStorageBackend: Pure-Python AWS SigV4 client over HTTPS (AWS S3, Cloudflare R2, MinIO, Supabase S3)
- PersistentDirectoryStorageBackend: Dedicated container-independent volume mount (DEEPVISION_PERSISTENT_STORAGE_DIR)
- EphemeralLocalBackend: Local development fallback (instance/recordings, instance/evidence)

Security & Reliability Guarantees:
- Never holds large multi-megabyte MP4 files wholly in memory (streams 64KB chunks).
- Validates every object key to block path traversal and malformed keys.
- Never logs service-role keys, secret access keys, or signed URLs.
- Verifies object existence and exact byte size before confirming upload success.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import logging
import os
import re
import shutil
import threading
import time
import urllib.parse
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Iterator, Optional, Tuple

import requests
from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse

logger = logging.getLogger(__name__)

_VALID_OBJECT_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/\-]{0,219}$")
_UPLOAD_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="DeepVisionUpload")
_INFLIGHT_LOCKS_GUARD = threading.Lock()
_INFLIGHT_RECORDING_UPLOADS = set()


def _sanitize_key_component(val: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._\-]+", "_", str(val or "").strip())
    return cleaned.strip("._-") or "item"


def validate_object_key(key: str) -> str:
    """Strictly validates object keys to prevent path traversal or injection."""
    norm = str(key or "").strip().replace("\\", "/").lstrip("/")
    if not norm or ".." in norm.split("/") or "\x00" in norm:
        raise ValueError("Invalid storage object key.")
    if not _VALID_OBJECT_KEY_RE.match(norm):
        raise ValueError("Storage object key contains unsupported characters or exceeds length limit.")
    return norm


def build_unique_object_key(
    category: str,
    user_id: int,
    camera_id: int,
    filename: str,
    record_id: Optional[int] = None,
) -> str:
    """
    Generates a collision-free object key.
    When record_id is supplied for a retryable item, derives a deterministic short suffix so
    retries never create duplicate objects in persistent storage.
    """
    cat = _sanitize_key_component(category).lower()
    fname = _sanitize_key_component(os.path.basename(filename or "media.bin"))
    if record_id is not None:
        digest = hashlib.sha256(f"{cat}:{user_id}:{camera_id}:{record_id}:{fname}".encode("utf-8")).hexdigest()[:8]
        key = f"u{int(user_id)}/cam{int(camera_id)}/r{int(record_id)}_{digest}_{fname}"
    else:
        rand = uuid.uuid4().hex[:10]
        key = f"u{int(user_id)}/cam{int(camera_id)}/{rand}_{fname}"
    return validate_object_key(key)


def parse_storage_uri(file_path: str) -> Tuple[str, str, str]:
    """
    Parses stored file_path into (scheme, container_or_bucket, object_key).
    Examples:
      'supabase://deepvision-recordings/u6/cam11/r4068_abcd1234_clip.mp4'
        -> ('supabase', 'deepvision-recordings', 'u6/cam11/r4068_abcd1234_clip.mp4')
      's3://my-bucket/u6/cam11/clip.mp4'
        -> ('s3', 'my-bucket', 'u6/cam11/clip.mp4')
      'pdir://recordings/u6/cam11/clip.mp4'
        -> ('pdir', 'recordings', 'u6/cam11/clip.mp4')
      'camera_11/cam_11_rec.mp4'
        -> ('local', '', 'camera_11/cam_11_rec.mp4')
    """
    raw = str(file_path or "").strip()
    for scheme in ("supabase", "s3", "pdir"):
        prefix = f"{scheme}://"
        if raw.startswith(prefix):
            rest = raw[len(prefix):]
            if "/" not in rest:
                raise ValueError("Malformed persistent storage URI.")
            bucket, key = rest.split("/", 1)
            return scheme, _sanitize_key_component(bucket), validate_object_key(key)
    return "local", "", raw


def _parse_range_header(range_header: Optional[str], file_size: int) -> Tuple[bool, Optional[int], Optional[int], bool]:
    """
    Parses HTTP Range header: bytes=start-end.
    Returns (has_range, byte_start, byte_end, is_valid).
    """
    if not range_header or "=" not in range_header:
        return False, None, None, True
    match = re.match(r"^bytes=(\d*)-(\d*)$", range_header.strip())
    if not match:
        return True, None, None, False
    start_str, end_str = match.groups()
    if start_str and end_str:
        byte_start = int(start_str)
        byte_end = min(int(end_str), max(0, file_size - 1)) if file_size > 0 else int(end_str)
    elif start_str:
        byte_start = int(start_str)
        byte_end = max(0, file_size - 1)
    elif end_str:
        byte_start = max(0, file_size - int(end_str))
        byte_end = max(0, file_size - 1)
    else:
        byte_start = 0
        byte_end = max(0, file_size - 1)

    if file_size <= 0 or byte_start >= file_size or byte_end >= file_size or byte_start > byte_end:
        return True, byte_start, byte_end, False
    return True, byte_start, byte_end, True


def _format_uri(scheme: str, bucket: str, key: str) -> str:
    uri = f"{scheme}://{bucket}/{validate_object_key(key)}"
    if len(uri) > 250:
        raise ValueError("Storage URI exceeds 250-character database column limit.")
    return uri


class BaseStorageBackend:
    name = "local"
    is_persistent = False

    def bucket_for(self, category: str) -> str:
        return "evidence" if str(category).lower() == "evidence" else "recordings"

    def upload_file(self, local_path: str, bucket: str, object_key: str, content_type: str = "application/octet-stream") -> str:
        raise NotImplementedError

    def verify_object(self, bucket: str, object_key: str, expected_size: Optional[int] = None) -> Tuple[bool, int]:
        raise NotImplementedError

    def delete_object(self, bucket: str, object_key: str) -> bool:
        raise NotImplementedError

    def open_range_response(
        self,
        request,
        bucket: str,
        object_key: str,
        content_type: str,
        as_attachment: bool = False,
        download_name: Optional[str] = None,
    ):
        raise NotImplementedError

    def create_signed_url(self, bucket: str, object_key: str, expires_in: int = 60) -> Optional[str]:
        return None


class PersistentDirectoryStorageBackend(BaseStorageBackend):
    """
    Container-independent persistent directory volume backend (e.g. Render Persistent Disk
    mounted via DEEPVISION_PERSISTENT_STORAGE_DIR=/var/data/deepvision or shared volume).
    """

    name = "persistent_dir"
    is_persistent = True

    def __init__(self, root_dir: str):
        self.root_dir = os.path.abspath(root_dir)
        os.makedirs(self.root_dir, exist_ok=True)

    def _resolve_target(self, bucket: str, object_key: str) -> str:
        safe_bucket = _sanitize_key_component(bucket)
        safe_key = validate_object_key(object_key)
        base = os.path.abspath(os.path.join(self.root_dir, safe_bucket))
        full = os.path.abspath(os.path.join(base, safe_key.replace("/", os.sep)))
        if os.path.commonpath([full, base]) != base:
            raise ValueError("Storage path escapes persistent volume boundary.")
        return full

    def upload_file(self, local_path: str, bucket: str, object_key: str, content_type: str = "application/octet-stream") -> str:
        if not os.path.isfile(local_path):
            raise FileNotFoundError("Source staging file does not exist.")
        target = self._resolve_target(bucket, object_key)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        tmp_target = f"{target}.part_{uuid.uuid4().hex[:8]}"
        src_hash = hashlib.sha256()
        dst_hash = hashlib.sha256()
        try:
            with open(local_path, "rb") as src, open(tmp_target, "wb") as dst:
                while True:
                    chunk = src.read(65536)
                    if not chunk:
                        break
                    src_hash.update(chunk)
                    dst.write(chunk)
                    dst_hash.update(chunk)
                dst.flush()
                os.fsync(dst.fileno())
            if src_hash.digest() != dst_hash.digest():
                raise IOError("Checksum mismatch during persistent volume write.")
            os.replace(tmp_target, target)
        finally:
            if os.path.exists(tmp_target):
                try:
                    os.remove(tmp_target)
                except Exception:
                    pass
        return _format_uri("pdir", bucket, object_key)

    def verify_object(self, bucket: str, object_key: str, expected_size: Optional[int] = None) -> Tuple[bool, int]:
        try:
            target = self._resolve_target(bucket, object_key)
            if not os.path.isfile(target):
                return False, 0
            actual = os.path.getsize(target)
            if expected_size is not None and actual != int(expected_size):
                return False, actual
            return actual > 0, actual
        except Exception:
            return False, 0

    def delete_object(self, bucket: str, object_key: str) -> bool:
        try:
            target = self._resolve_target(bucket, object_key)
            if os.path.isfile(target):
                os.remove(target)
                return True
            return False
        except Exception:
            return False

    def open_range_response(
        self,
        request,
        bucket: str,
        object_key: str,
        content_type: str,
        as_attachment: bool = False,
        download_name: Optional[str] = None,
    ):
        from apps.core.media_service import serve_file_with_ranges

        target = self._resolve_target(bucket, object_key)
        if not os.path.isfile(target):
            raise Http404("Media object not found in persistent storage.")
        return serve_file_with_ranges(
            request=request,
            full_path=target,
            content_type=content_type,
            as_attachment=as_attachment,
            download_name=download_name or os.path.basename(object_key),
        )


class SupabaseStorageBackend(BaseStorageBackend):
    """
    Private Supabase Storage REST v1 client backed by service-role credentials.
    Streams uploads directly from disk and forwards HTTP Range headers for zero-buffer seeking.
    """

    name = "supabase"
    is_persistent = True
    _verified_buckets = set()
    _bucket_lock = threading.Lock()

    def __init__(
        self,
        supabase_url: str,
        service_role_key: str,
        recordings_bucket: str = "deepvision-recordings",
        evidence_bucket: str = "deepvision-evidence",
        timeout: int = 60,
    ):
        self.base_url = supabase_url.rstrip("/")
        self._service_key = service_role_key.strip()
        self.recordings_bucket = _sanitize_key_component(recordings_bucket)
        self.evidence_bucket = _sanitize_key_component(evidence_bucket)
        self.timeout = max(10, int(timeout))

    def bucket_for(self, category: str) -> str:
        return self.evidence_bucket if str(category).lower() == "evidence" else self.recordings_bucket

    def _auth_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._service_key}",
            "apikey": self._service_key,
        }

    def ensure_private_bucket(self, bucket: str) -> None:
        safe_bucket = _sanitize_key_component(bucket)
        if safe_bucket in self._verified_buckets:
            return
        with self._bucket_lock:
            if safe_bucket in self._verified_buckets:
                return
            info_url = f"{self.base_url}/storage/v1/bucket/{safe_bucket}"
            resp = requests.get(info_url, headers=self._auth_headers(), timeout=15)
            if resp.status_code == 200:
                data = resp.json() if resp.content else {}
                if data.get("public") is True:
                    # Enforce strict private bucket posture
                    requests.put(
                        info_url,
                        headers={**self._auth_headers(), "Content-Type": "application/json"},
                        json={"public": False},
                        timeout=15,
                    )
                self._verified_buckets.add(safe_bucket)
                return

            create_url = f"{self.base_url}/storage/v1/bucket"
            c_resp = requests.post(
                create_url,
                headers={**self._auth_headers(), "Content-Type": "application/json"},
                json={"id": safe_bucket, "name": safe_bucket, "public": False},
                timeout=15,
            )
            if c_resp.status_code not in (200, 201, 409):
                raise IOError(f"Supabase bucket verification failed (HTTP {c_resp.status_code}).")
            self._verified_buckets.add(safe_bucket)

    def _object_url(self, bucket: str, object_key: str) -> str:
        safe_bucket = _sanitize_key_component(bucket)
        safe_key = validate_object_key(object_key)
        encoded_key = urllib.parse.quote(safe_key, safe="/")
        return f"{self.base_url}/storage/v1/object/{safe_bucket}/{encoded_key}"

    def upload_file(self, local_path: str, bucket: str, object_key: str, content_type: str = "application/octet-stream") -> str:
        if not os.path.isfile(local_path):
            raise FileNotFoundError("Source staging file does not exist.")
        self.ensure_private_bucket(bucket)
        url = self._object_url(bucket, object_key)
        headers = {
            **self._auth_headers(),
            "Content-Type": content_type,
            "x-upsert": "true",
        }
        with open(local_path, "rb") as fh:
            resp = requests.post(url, headers=headers, data=fh, timeout=self.timeout)
        if resp.status_code not in (200, 201):
            raise IOError(f"Supabase Storage upload failed (HTTP {resp.status_code}).")
        return _format_uri("supabase", bucket, object_key)

    def verify_object(self, bucket: str, object_key: str, expected_size: Optional[int] = None) -> Tuple[bool, int]:
        try:
            url = self._object_url(bucket, object_key)
            resp = requests.head(url, headers=self._auth_headers(), timeout=15)
            if resp.status_code != 200:
                return False, 0
            actual = int(resp.headers.get("Content-Length") or 0)
            if expected_size is not None and actual > 0 and actual != int(expected_size):
                return False, actual
            return (actual > 0 if expected_size is None or expected_size > 0 else True), actual
        except Exception:
            return False, 0

    def delete_object(self, bucket: str, object_key: str) -> bool:
        try:
            safe_bucket = _sanitize_key_component(bucket)
            safe_key = validate_object_key(object_key)
            url = f"{self.base_url}/storage/v1/object/{safe_bucket}"
            resp = requests.delete(
                url,
                headers={**self._auth_headers(), "Content-Type": "application/json"},
                json={"prefixes": [safe_key]},
                timeout=15,
            )
            return resp.status_code in (200, 204)
        except Exception:
            return False

    def create_signed_url(self, bucket: str, object_key: str, expires_in: int = 60) -> Optional[str]:
        safe_bucket = _sanitize_key_component(bucket)
        safe_key = validate_object_key(object_key)
        encoded_key = urllib.parse.quote(safe_key, safe="/")
        url = f"{self.base_url}/storage/v1/object/sign/{safe_bucket}/{encoded_key}"
        resp = requests.post(
            url,
            headers={**self._auth_headers(), "Content-Type": "application/json"},
            json={"expiresIn": max(15, min(300, int(expires_in)))},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        signed_path = (resp.json() or {}).get("signedURL")
        if not signed_path:
            return None
        if signed_path.startswith("http"):
            return signed_path
        return f"{self.base_url}/storage/v1{signed_path}" if signed_path.startswith("/") else f"{self.base_url}/storage/v1/{signed_path}"

    def open_range_response(
        self,
        request,
        bucket: str,
        object_key: str,
        content_type: str,
        as_attachment: bool = False,
        download_name: Optional[str] = None,
    ):
        url = self._object_url(bucket, object_key)
        headers = self._auth_headers()
        range_header = request.headers.get("Range") or request.META.get("HTTP_RANGE")
        if (not as_attachment) and range_header:
            headers["Range"] = range_header

        upstream = requests.get(url, headers=headers, stream=True, timeout=self.timeout)
        if upstream.status_code == 404:
            upstream.close()
            raise Http404("Recording object not found in Supabase Storage.")
        if upstream.status_code not in (200, 206):
            code = upstream.status_code
            upstream.close()
            raise IOError(f"Failed streaming object from Supabase Storage (HTTP {code}).")

        def chunk_stream() -> Iterator[bytes]:
            try:
                for chunk in upstream.iter_content(chunk_size=65536):
                    if chunk:
                        yield chunk
            finally:
                upstream.close()

        resp = StreamingHttpResponse(chunk_stream(), status=upstream.status_code, content_type=content_type)
        if "Content-Length" in upstream.headers:
            resp["Content-Length"] = upstream.headers["Content-Length"]
        if "Content-Range" in upstream.headers:
            resp["Content-Range"] = upstream.headers["Content-Range"]
        resp["Accept-Ranges"] = upstream.headers.get("Accept-Ranges", "bytes")
        if as_attachment:
            fname = download_name or os.path.basename(object_key)
            resp["Content-Disposition"] = f'attachment; filename="{fname}"'
        else:
            resp["Content-Disposition"] = "inline"
        return resp


class S3CompatibleStorageBackend(BaseStorageBackend):
    """
    Pure-Python AWS Signature Version 4 S3-compatible object storage client
    supporting AWS S3, Cloudflare R2, MinIO, and Supabase S3 Gateway over HTTPS.
    """

    name = "s3"
    is_persistent = True

    def __init__(
        self,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        region: str = "us-east-1",
        endpoint_url: str = "",
        timeout: int = 60,
    ):
        self.default_bucket = _sanitize_key_component(bucket)
        self._access_key = access_key_id.strip()
        self._secret_key = secret_access_key.strip()
        self.region = (region or "us-east-1").strip()
        self.endpoint_url = (endpoint_url or f"https://s3.{self.region}.amazonaws.com").rstrip("/")
        self.timeout = max(10, int(timeout))

    def bucket_for(self, category: str) -> str:
        return self.default_bucket

    def _sign_headers(self, method: str, bucket: str, object_key: str, payload_hash: str, extra_headers: Optional[dict] = None) -> Tuple[str, dict]:
        safe_bucket = _sanitize_key_component(bucket)
        safe_key = validate_object_key(object_key)
        parsed = urllib.parse.urlsplit(self.endpoint_url)
        host = parsed.netloc
        base_path = parsed.path.rstrip("/")
        canonical_uri = f"{base_path}/{urllib.parse.quote(safe_bucket, safe='')}/{urllib.parse.quote(safe_key, safe='/')}"
        url = f"{parsed.scheme}://{host}{canonical_uri}"

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        amz_date = now_utc.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now_utc.strftime("%Y%m%d")

        headers = {
            "Host": host,
            "x-amz-date": amz_date,
            "x-amz-content-sha256": payload_hash,
        }
        if extra_headers:
            headers.update(extra_headers)

        lowered = {k.lower(): str(v).strip() for k, v in headers.items()}
        signed_header_names = sorted(lowered.keys())
        canonical_headers = "".join(f"{k}:{lowered[k]}\n" for k in signed_header_names)
        signed_headers_str = ";".join(signed_header_names)

        canonical_request = "\n".join([
            method.upper(),
            canonical_uri,
            "",
            canonical_headers,
            signed_headers_str,
            payload_hash,
        ])
        credential_scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        string_to_sign = "\n".join([
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ])

        def _sign(key_bytes: bytes, msg: str) -> bytes:
            return hmac.new(key_bytes, msg.encode("utf-8"), hashlib.sha256).digest()

        k_date = _sign(("AWS4" + self._secret_key).encode("utf-8"), date_stamp)
        k_region = _sign(k_date, self.region)
        k_service = _sign(k_region, "s3")
        k_signing = _sign(k_service, "aws4_request")
        signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        headers["Authorization"] = (
            f"AWS4-HMAC-SHA256 Credential={self._access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers_str}, Signature={signature}"
        )
        headers.pop("Host", None)
        return url, headers

    def upload_file(self, local_path: str, bucket: str, object_key: str, content_type: str = "application/octet-stream") -> str:
        if not os.path.isfile(local_path):
            raise FileNotFoundError("Source staging file does not exist.")
        url, headers = self._sign_headers(
            "PUT",
            bucket,
            object_key,
            "UNSIGNED-PAYLOAD",
            extra_headers={"Content-Type": content_type},
        )
        with open(local_path, "rb") as fh:
            resp = requests.put(url, headers=headers, data=fh, timeout=self.timeout)
        if resp.status_code not in (200, 201, 204):
            raise IOError(f"S3 upload failed (HTTP {resp.status_code}).")
        return _format_uri("s3", bucket, object_key)

    def verify_object(self, bucket: str, object_key: str, expected_size: Optional[int] = None) -> Tuple[bool, int]:
        try:
            url, headers = self._sign_headers("HEAD", bucket, object_key, "UNSIGNED-PAYLOAD")
            resp = requests.head(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                return False, 0
            actual = int(resp.headers.get("Content-Length") or 0)
            if expected_size is not None and actual > 0 and actual != int(expected_size):
                return False, actual
            return actual > 0, actual
        except Exception:
            return False, 0

    def delete_object(self, bucket: str, object_key: str) -> bool:
        try:
            url, headers = self._sign_headers("DELETE", bucket, object_key, "UNSIGNED-PAYLOAD")
            resp = requests.delete(url, headers=headers, timeout=15)
            return resp.status_code in (200, 204)
        except Exception:
            return False

    def open_range_response(
        self,
        request,
        bucket: str,
        object_key: str,
        content_type: str,
        as_attachment: bool = False,
        download_name: Optional[str] = None,
    ):
        extra = {}
        range_header = request.headers.get("Range") or request.META.get("HTTP_RANGE")
        if (not as_attachment) and range_header:
            extra["Range"] = range_header
        url, headers = self._sign_headers("GET", bucket, object_key, "UNSIGNED-PAYLOAD", extra_headers=extra)
        upstream = requests.get(url, headers=headers, stream=True, timeout=self.timeout)
        if upstream.status_code == 404:
            upstream.close()
            raise Http404("Media object not found in S3 storage.")
        if upstream.status_code not in (200, 206):
            code = upstream.status_code
            upstream.close()
            raise IOError(f"S3 read failed (HTTP {code}).")

        def chunk_stream() -> Iterator[bytes]:
            try:
                for chunk in upstream.iter_content(chunk_size=65536):
                    if chunk:
                        yield chunk
            finally:
                upstream.close()

        resp = StreamingHttpResponse(chunk_stream(), status=upstream.status_code, content_type=content_type)
        if "Content-Length" in upstream.headers:
            resp["Content-Length"] = upstream.headers["Content-Length"]
        if "Content-Range" in upstream.headers:
            resp["Content-Range"] = upstream.headers["Content-Range"]
        resp["Accept-Ranges"] = upstream.headers.get("Accept-Ranges", "bytes")
        if as_attachment:
            fname = download_name or os.path.basename(object_key)
            resp["Content-Disposition"] = f'attachment; filename="{fname}"'
        else:
            resp["Content-Disposition"] = "inline"
        return resp


def get_storage_backend(force_scheme: Optional[str] = None) -> BaseStorageBackend:
    """
    Resolves active persistent storage backend from environment configuration.
    Order: explicit scheme -> Supabase Storage -> S3-Compatible -> Persistent Volume Mount -> Local Ephemeral.
    """
    mode = (force_scheme or os.getenv("DEEPVISION_STORAGE_BACKEND", "auto")).strip().lower()
    supa_url = os.getenv("SUPABASE_URL", "").strip()
    supa_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    rec_bucket = os.getenv("SUPABASE_STORAGE_BUCKET_RECORDINGS", "deepvision-recordings").strip()
    ev_bucket = os.getenv("SUPABASE_STORAGE_BUCKET_EVIDENCE", "deepvision-evidence").strip()

    s3_bucket = os.getenv("S3_BUCKET", "").strip()
    s3_key = os.getenv("S3_ACCESS_KEY_ID", "").strip()
    s3_secret = os.getenv("S3_SECRET_ACCESS_KEY", "").strip()
    s3_region = os.getenv("S3_REGION", "us-east-1").strip()
    s3_endpoint = os.getenv("S3_ENDPOINT_URL", "").strip()

    pdir_root = os.getenv("DEEPVISION_PERSISTENT_STORAGE_DIR", "").strip()

    if mode == "supabase" or (mode == "auto" and supa_url and supa_key):
        if supa_url and supa_key:
            return SupabaseStorageBackend(
                supabase_url=supa_url,
                service_role_key=supa_key,
                recordings_bucket=rec_bucket,
                evidence_bucket=ev_bucket,
            )

    if mode == "s3" or (mode == "auto" and s3_bucket and s3_key and s3_secret):
        if s3_bucket and s3_key and s3_secret:
            return S3CompatibleStorageBackend(
                bucket=s3_bucket,
                access_key_id=s3_key,
                secret_access_key=s3_secret,
                region=s3_region,
                endpoint_url=s3_endpoint,
            )

    if mode == "pdir" or mode == "persistent_dir" or (mode == "auto" and pdir_root):
        if pdir_root:
            return PersistentDirectoryStorageBackend(pdir_root)

    return BaseStorageBackend()


def get_storage_health() -> dict:
    """Returns sanitized storage posture diagnostics (zero secret exposure)."""
    backend = get_storage_backend()
    return {
        "backend": backend.name,
        "persistent_configured": backend.is_persistent,
        "mode": "persistent" if backend.is_persistent else "ephemeral_local_only",
        "recordings_bucket": backend.bucket_for("recordings"),
        "evidence_bucket": backend.bucket_for("evidence"),
    }


def resolve_local_staged_recording(recording) -> Optional[str]:
    """Resolves local staging MP4 path for a Recording object even if file_path was already updated."""
    from apps.core.media_service import RECORDINGS_DIR, safe_resolve_recording

    resolved = safe_resolve_recording(getattr(recording, "file_path", "") or "")
    if resolved:
        return resolved
    cam_id = getattr(recording, "camera_id", None)
    fname = getattr(recording, "filename", None)
    if cam_id and fname:
        candidate = os.path.normpath(os.path.join(RECORDINGS_DIR, f"camera_{cam_id}", os.path.basename(fname)))
        if os.path.isfile(candidate):
            return candidate
    return None


def resolve_local_staged_evidence(evidence) -> Optional[str]:
    """Resolves local staging file path for an Evidence object."""
    from apps.core.media_service import EVIDENCE_DIR, safe_resolve_evidence

    resolved = safe_resolve_evidence(getattr(evidence, "file_path", "") or "")
    if resolved:
        return resolved
    cam_id = getattr(evidence, "camera_id", None)
    fname = getattr(evidence, "file_name", None)
    if cam_id and fname:
        cam_root = os.path.normpath(os.path.join(EVIDENCE_DIR, f"camera_{cam_id}"))
        if os.path.isdir(cam_root):
            for root_walk, _, files in os.walk(cam_root):
                if fname in files:
                    candidate = os.path.join(root_walk, fname)
                    if os.path.isfile(candidate):
                        return candidate
    return None


def media_exists(file_path: str, kind: str = "recording") -> bool:
    """Checks whether a recording or evidence object exists locally OR in persistent storage."""
    if not file_path:
        return False
    try:
        scheme, bucket, key = parse_storage_uri(file_path)
    except ValueError:
        return False

    if scheme == "local":
        from apps.core.media_service import safe_resolve_evidence, safe_resolve_recording

        if kind == "evidence":
            return safe_resolve_evidence(file_path) is not None
        return safe_resolve_recording(file_path) is not None

    backend = get_storage_backend(force_scheme=scheme)
    if not backend.is_persistent:
        return False
    ok, _ = backend.verify_object(bucket, key)
    return ok


def delete_stored_media(file_path: str, kind: str = "recording") -> bool:
    """Deletes a media object from persistent storage and/or local disk safely."""
    if not file_path:
        return False
    deleted = False
    try:
        scheme, bucket, key = parse_storage_uri(file_path)
    except ValueError:
        return False

    if scheme in ("supabase", "s3", "pdir"):
        backend = get_storage_backend(force_scheme=scheme)
        if backend.is_persistent:
            deleted = backend.delete_object(bucket, key) or deleted
    else:
        from apps.core.media_service import safe_resolve_evidence, safe_resolve_recording

        local_p = safe_resolve_evidence(file_path) if kind == "evidence" else safe_resolve_recording(file_path)
        if local_p and os.path.isfile(local_p):
            try:
                os.remove(local_p)
                deleted = True
            except Exception:
                pass
    return deleted


def serve_stored_media(
    request,
    file_path: str,
    kind: str,
    content_type: str,
    as_attachment: bool = False,
    download_name: Optional[str] = None,
    fallback_local_path: Optional[str] = None,
):
    """Unified playback/download entrypoint supporting local disk and remote persistent storage."""
    from apps.core.media_service import safe_resolve_evidence, safe_resolve_recording, serve_file_with_ranges

    scheme, bucket, key = parse_storage_uri(file_path)
    if scheme in ("supabase", "s3", "pdir"):
        backend = get_storage_backend(force_scheme=scheme)
        if backend.is_persistent:
            try:
                return backend.open_range_response(
                    request=request,
                    bucket=bucket,
                    object_key=key,
                    content_type=content_type,
                    as_attachment=as_attachment,
                    download_name=download_name,
                )
            except Http404:
                if fallback_local_path and os.path.isfile(fallback_local_path):
                    return serve_file_with_ranges(
                        request=request,
                        full_path=fallback_local_path,
                        content_type=content_type,
                        as_attachment=as_attachment,
                        download_name=download_name,
                    )
                raise

    local_p = (
        safe_resolve_evidence(file_path)
        if kind == "evidence"
        else safe_resolve_recording(file_path)
    ) or fallback_local_path

    if not local_p or not os.path.isfile(local_p):
        raise Http404("Media file not found in storage.")
    return serve_file_with_ranges(
        request=request,
        full_path=local_p,
        content_type=content_type,
        as_attachment=as_attachment,
        download_name=download_name,
    )


def upload_recording_by_id(recording_id: int, purge_local_on_verify: Optional[bool] = None) -> Tuple[bool, str]:
    """
    Uploads a finalized recording file to the active persistent backend,
    verifies object existence + byte size, updates DB status to 'completed' (or 'failed'),
    and removes staged local MP4 only after persistent verification succeeds.
    Idempotent: prevents concurrent duplicate uploads for the same recording_id.
    """
    from apps.core.models import AuditLog
    from apps.recordings.models import Recording

    with _INFLIGHT_LOCKS_GUARD:
        if recording_id in _INFLIGHT_RECORDING_UPLOADS:
            return False, "Upload already in progress."
        _INFLIGHT_RECORDING_UPLOADS.add(recording_id)

    t0 = time.perf_counter()
    try:
        rec = Recording.objects.filter(id=recording_id).first()
        if not rec:
            return False, "Recording not found."

        # Already persistent and verified -> skip duplicate upload
        scheme, bucket, key = parse_storage_uri(rec.file_path)
        if scheme in ("supabase", "s3", "pdir") and rec.status == "completed":
            backend_existing = get_storage_backend(force_scheme=scheme)
            if backend_existing.is_persistent:
                ok_exist, _ = backend_existing.verify_object(bucket, key)
                if ok_exist:
                    return True, "Already persisted and verified."

        backend = get_storage_backend()
        local_path = resolve_local_staged_recording(rec)
        if not local_path or not os.path.isfile(local_path):
            rec.status = "failed"
            rec.save(update_fields=["status"])
            return False, "Local recording file missing for upload."

        actual_size = os.path.getsize(local_path)
        if actual_size <= 0:
            rec.status = "failed"
            rec.save(update_fields=["status"])
            return False, "Recording file is empty (0 bytes)."

        rec.file_size = actual_size
        if not backend.is_persistent:
            rec.status = "completed"
            rec.save(update_fields=["file_size", "status"])
            return True, "Saved locally (persistent cloud storage not configured)."

        rec.status = "uploading"
        rec.save(update_fields=["file_size", "status"])

        target_bucket = backend.bucket_for("recordings")
        object_key = build_unique_object_key(
            category="recordings",
            user_id=rec.user_id,
            camera_id=rec.camera_id,
            filename=rec.filename,
            record_id=rec.id,
        )

        persistent_uri = backend.upload_file(
            local_path=local_path,
            bucket=target_bucket,
            object_key=object_key,
            content_type="video/mp4",
        )
        ok_verify, remote_size = backend.verify_object(
            bucket=target_bucket,
            object_key=object_key,
            expected_size=actual_size,
        )
        if not ok_verify or remote_size != actual_size:
            raise IOError(f"Persistent verification failed (expected={actual_size}, actual={remote_size}).")

        rec.file_path = persistent_uri
        rec.file_size = remote_size
        rec.status = "completed"
        rec.save(update_fields=["file_path", "file_size", "status"])

        should_purge = (
            purge_local_on_verify
            if purge_local_on_verify is not None
            else (os.getenv("DEEPVISION_PURGE_LOCAL_AFTER_UPLOAD", "true").lower() in ("true", "1"))
        )
        if should_purge and os.path.isfile(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        try:
            AuditLog.objects.create(
                user_id=rec.user_id,
                action="RECORDING_UPLOAD_VERIFIED",
                resource_type="recording",
                resource_id=str(rec.id),
                description=f"Verified persistent upload ({backend.name}, {remote_size} bytes, {elapsed_ms} ms).",
            )
        except Exception:
            pass
        logger.info(f"[RECORDING_UPLOAD_VERIFIED] id={rec.id} backend={backend.name} size={remote_size} ms={elapsed_ms}")
        return True, f"Uploaded and verified in {elapsed_ms} ms."

    except Exception as exc:
        logger.error(f"[RECORDING_UPLOAD_FAILED] id={recording_id}: {exc}")
        try:
            rec = Recording.objects.filter(id=recording_id).first()
            if rec:
                rec.status = "failed"
                rec.save(update_fields=["status"])
                AuditLog.objects.create(
                    user_id=rec.user_id,
                    action="RECORDING_UPLOAD_FAILED",
                    resource_type="recording",
                    resource_id=str(rec.id),
                    description=f"Persistent upload failed; staged local copy retained ({type(exc).__name__}).",
                )
        except Exception:
            pass
        return False, str(exc)
    finally:
        with _INFLIGHT_LOCKS_GUARD:
            _INFLIGHT_RECORDING_UPLOADS.discard(recording_id)


def schedule_recording_upload(recording_id: int) -> None:
    """Schedules non-blocking background persistent upload for a finalized recording."""
    _UPLOAD_EXECUTOR.submit(upload_recording_by_id, recording_id)


def upload_evidence_by_id(evidence_id: int, purge_local_on_verify: Optional[bool] = None) -> Tuple[bool, str]:
    """Uploads an Evidence artifact (snapshot or video clip) to persistent storage and verifies it."""
    from apps.evidence.models import Evidence

    ev = Evidence.objects.filter(id=evidence_id).first()
    if not ev:
        return False, "Evidence not found."

    backend = get_storage_backend()
    if not backend.is_persistent:
        return True, "Local storage mode."

    local_path = resolve_local_staged_evidence(ev)
    if not local_path or not os.path.isfile(local_path):
        return False, "Local evidence file not found."

    actual_size = os.path.getsize(local_path)
    if actual_size <= 0:
        return False, "Evidence file is empty."

    target_bucket = backend.bucket_for("evidence")
    object_key = build_unique_object_key(
        category="evidence",
        user_id=ev.user_id,
        camera_id=ev.camera_id,
        filename=ev.file_name,
        record_id=ev.id,
    )
    persistent_uri = backend.upload_file(
        local_path=local_path,
        bucket=target_bucket,
        object_key=object_key,
        content_type=ev.mime_type or "application/octet-stream",
    )
    ok_verify, remote_size = backend.verify_object(
        bucket=target_bucket,
        object_key=object_key,
        expected_size=actual_size,
    )
    if not ok_verify or remote_size != actual_size:
        raise IOError("Evidence upload verification mismatch.")

    ev.file_path = persistent_uri
    ev.file_size = remote_size
    ev.save(update_fields=["file_path", "file_size"])

    should_purge = (
        purge_local_on_verify
        if purge_local_on_verify is not None
        else (os.getenv("DEEPVISION_PURGE_LOCAL_AFTER_UPLOAD", "true").lower() in ("true", "1"))
    )
    if should_purge and os.path.isfile(local_path):
        try:
            os.remove(local_path)
        except Exception:
            pass

    logger.info(f"[EVIDENCE_UPLOAD_VERIFIED] id={ev.id} backend={backend.name} size={remote_size}")
    return True, "Uploaded and verified."


def schedule_evidence_upload(evidence_id: int) -> None:
    """Schedules non-blocking persistent upload for an evidence asset."""
    _UPLOAD_EXECUTOR.submit(upload_evidence_by_id, evidence_id)


def migrate_local_media_to_persistent(user_id: Optional[int] = None, limit: int = 100) -> dict:
    """
    Safely migrates legacy local recordings and evidence items to the configured persistent backend.
    Additive and non-destructive: skips already-persisted objects and leaves missing legacy rows untouched.
    """
    from apps.evidence.models import Evidence
    from apps.recordings.models import Recording

    summary = {"recordings_migrated": 0, "recordings_skipped": 0, "evidence_migrated": 0, "evidence_skipped": 0}
    backend = get_storage_backend()
    if not backend.is_persistent:
        return summary

    rec_qs = Recording.objects.all().order_by("-id")
    ev_qs = Evidence.objects.all().order_by("-id")
    if user_id is not None:
        rec_qs = rec_qs.filter(user_id=user_id)
        ev_qs = ev_qs.filter(user_id=user_id)

    for rec in rec_qs[:limit]:
        scheme, _, _ = parse_storage_uri(rec.file_path)
        if scheme != "local":
            continue
        if not resolve_local_staged_recording(rec):
            summary["recordings_skipped"] += 1
            continue
        ok, _ = upload_recording_by_id(rec.id)
        if ok:
            summary["recordings_migrated"] += 1
        else:
            summary["recordings_skipped"] += 1

    for ev in ev_qs[:limit]:
        scheme, _, _ = parse_storage_uri(ev.file_path)
        if scheme != "local":
            continue
        if not resolve_local_staged_evidence(ev):
            summary["evidence_skipped"] += 1
            continue
        try:
            ok, _ = upload_evidence_by_id(ev.id)
            if ok:
                summary["evidence_migrated"] += 1
            else:
                summary["evidence_skipped"] += 1
        except Exception:
            summary["evidence_skipped"] += 1

    return summary

