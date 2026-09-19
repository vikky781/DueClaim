"""/api/v1/uploads — the OCR accelerator.

Flow: presign -> browser PUTs straight to S3 -> extract runs Textract
AnalyzeExpense on the object and returns PROPOSED invoice fields with
confidence. Nothing here touches DynamoDB; the user reviews the proposal in
the manual form and that form's POST is the only path that persists.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Any, Protocol
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..auth import get_current_user_sub
from ..ocr import ExtractedField, map_expense_document

router = APIRouter(prefix="/api/v1/uploads")

PRESIGN_TTL_SECONDS = 300
ALLOWED_CONTENT_TYPES: dict[str, str] = {"image/jpeg": "jpg", "image/png": "png", "application/pdf": "pdf"}
_KEY = re.compile(r"^uploads/(?P<sub>[^/]+)/(?P<name>[0-9a-f]{32})\.(?P<ext>jpg|png|pdf)$")


class ObjectMissing(Exception):
    """The presigned upload never happened (or S3 is not yet consistent)."""


class UnsupportedDocument(Exception):
    """Textract could not read the object (bad image, encrypted PDF, too many pages...)."""


class UploadsBackend(Protocol):
    def presign_put(self, key: str, content_type: str, expires_in: int) -> str: ...
    def analyze_expense(self, key: str) -> dict[str, Any]: ...
    def put_object(self, key: str, data: bytes, content_type: str) -> None: ...
    def presign_get(self, key: str, expires_in: int) -> str: ...


class AwsUploads:
    def __init__(self, bucket: str, region: str) -> None:
        self._bucket = bucket
        # s3v4 + virtual-hosted addressing so the presigned host is the REGIONAL
        # endpoint (bucket.s3.ap-south-1.amazonaws.com). With the default config
        # botocore emits the legacy global host and S3 answers a 307 redirect,
        # which a browser's CORS PUT cannot follow.
        self._s3 = boto3.client(
            "s3", region_name=region, config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"})
        )
        self._textract = boto3.client("textract", region_name=region)

    def presign_put(self, key: str, content_type: str, expires_in: int) -> str:
        return self._s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": self._bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires_in,
            HttpMethod="PUT",
        )

    def put_object(self, key: str, data: bytes, content_type: str) -> None:
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)

    def presign_get(self, key: str, expires_in: int) -> str:
        return self._s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key, "ResponseContentDisposition": "inline"},
            ExpiresIn=expires_in,
        )

    def analyze_expense(self, key: str) -> dict[str, Any]:
        try:
            return self._textract.analyze_expense(Document={"S3Object": {"Bucket": self._bucket, "Name": key}})
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("InvalidS3ObjectException",):
                raise ObjectMissing(key) from exc
            if code in ("UnsupportedDocumentException", "BadDocumentException", "DocumentTooLargeException"):
                raise UnsupportedDocument(key) from exc
            raise


@lru_cache(maxsize=1)
def _default_backend() -> AwsUploads:
    bucket = os.environ.get("UPLOAD_BUCKET")
    if not bucket:
        raise RuntimeError("UPLOAD_BUCKET environment variable is not set")
    return AwsUploads(bucket, os.environ.get("AWS_REGION", "ap-south-1"))


def get_uploads_backend() -> UploadsBackend:
    """FastAPI dependency. Tests override this with a fake."""
    return _default_backend()


# --- schemas -----------------------------------------------------------------


class PresignRequest(BaseModel):
    content_type: str
    filename: str | None = None  # informational only; never used in the key


class PresignResponse(BaseModel):
    url: str
    key: str
    headers: dict[str, str]
    expires_in: int


class FieldRead(BaseModel):
    value: str | None
    confidence: float | None
    raw: str | None
    source: str | None


class ExtractionResponse(BaseModel):
    key: str
    invoice_number: FieldRead
    invoice_date: FieldRead
    buyer_name: FieldRead
    amount: FieldRead
    fields_seen: list[str]


def _field(f: ExtractedField) -> FieldRead:
    return FieldRead(value=f.value, confidence=f.confidence, raw=f.raw, source=f.source)


# --- routes ------------------------------------------------------------------


@router.post("/presign", response_model=PresignResponse)
def presign_upload(
    req: PresignRequest,
    sub: str = Depends(get_current_user_sub),
    backend: UploadsBackend = Depends(get_uploads_backend),
) -> PresignResponse:
    ext = ALLOWED_CONTENT_TYPES.get(req.content_type)
    if not ext:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unsupported content type {req.content_type!r}. Upload a JPEG, PNG or PDF.",
        )
    key = f"uploads/{sub}/{uuid4().hex}.{ext}"
    url = backend.presign_put(key, req.content_type, PRESIGN_TTL_SECONDS)
    return PresignResponse(url=url, key=key, headers={"Content-Type": req.content_type}, expires_in=PRESIGN_TTL_SECONDS)


@router.post("/{key:path}/extract", response_model=ExtractionResponse)
def extract_invoice(
    key: str,
    sub: str = Depends(get_current_user_sub),
    backend: UploadsBackend = Depends(get_uploads_backend),
) -> ExtractionResponse:
    m = _KEY.match(key)
    if not m or m.group("sub") != sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")
    try:
        response = backend.analyze_expense(key)
    except ObjectMissing as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The file has not finished uploading. Try again in a moment.",
        ) from exc
    except UnsupportedDocument as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Textract could not read this file. Try a clearer photo or a single-page PDF.",
        ) from exc
    extracted = map_expense_document(response)
    return ExtractionResponse(
        key=key,
        invoice_number=_field(extracted.invoice_number),
        invoice_date=_field(extracted.invoice_date),
        buyer_name=_field(extracted.buyer_name),
        amount=_field(extracted.amount),
        fields_seen=extracted.fields_seen,
    )
