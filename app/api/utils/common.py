import logging
import os
from pathlib import Path
from typing import IO, Optional, Union

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("healthcare-platform")

# When AWS_ENDPOINT_URL is set (MinIO locally), boto3 routes to that endpoint.
# When unset (real AWS), the default AWS endpoint is used automatically.
def _s3_client() -> boto3.client:
    kwargs = {}
    endpoint_url = os.getenv("AWS_ENDPOINT_URL")
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    return boto3.client("s3", **kwargs)


def common_logger(message: str, level: str = "info") -> None:
    getattr(logger, level.lower(), logger.info)(message)


def upload_to_s3(
    source: Union[str, IO[bytes]],
    bucket_name: str,
    object_name: Optional[str] = None,
) -> bool:
    s3_client = _s3_client()

    try:
        if isinstance(source, str):
            if object_name is None:
                object_name = Path(source).name
            s3_client.upload_file(source, bucket_name, object_name)
            common_logger(f"Uploaded {source} to s3://{bucket_name}/{object_name}")
        else:
            if object_name is None:
                raise ValueError("object_name is required when source is a file-like object")
            s3_client.upload_fileobj(source, bucket_name, object_name)
            common_logger(f"Streamed upload to s3://{bucket_name}/{object_name}")
        return True
    except FileNotFoundError:
        common_logger(f"File not found: {source}", level="error")
        return False
    except NoCredentialsError:
        common_logger("AWS credentials not available", level="error")
        return False
    except ClientError as e:
        common_logger(f"S3 upload failed: {e}", level="error")
        return False
