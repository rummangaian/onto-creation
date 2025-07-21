import requests
from typing import BinaryIO, Dict

CMS_UPLOAD_URL = "https://ig.gov-cloud.ai/mobius-content-service/v1.0/content/upload?filePath=KYA"

def upload_to_cms(
    file_stream: BinaryIO,
    bearer_token: str
) -> Dict[str, str]:
    """
    Uploads RDF file to CMS. CMS URL is hardcoded. fileName field is posted as empty string ("").
    Returns CMS asset metadata (id and url).
    """
    try:
        headers = {
            "Authorization": f"Bearer {bearer_token}"
        }

        files = {
            "file": ("swagger.rdf", file_stream, "application/rdf+xml"),
            "fileName": (None, "")
        }


        response = requests.post(CMS_UPLOAD_URL, headers=headers, files=files)
        response.raise_for_status()

        data = response.json()
        return {
            "id": data.get("id", ""),
            "url": data.get("url", "") or data.get("cdnUrl", "")
        }

    except requests.RequestException as e:
        raise RuntimeError(f"CMS upload failed: {str(e)}")
    except Exception as e:
        raise RuntimeError(f"Upload error: {str(e)}")
