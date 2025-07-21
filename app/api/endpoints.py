from fastapi import APIRouter, UploadFile, File, HTTPException , Header
from fastapi.responses import StreamingResponse
from app.converters.openapi_to_rdf import SwaggerToRDFConverter
from app.converters.openapi_to_ttl import OpenAPIToTTL
from app.utils.cms_uploader import upload_to_cms
import io
import json
import logging
import tempfile

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/", summary="Testing")
async def test():
    return "Endpoint is working fine"

from fastapi import APIRouter, UploadFile, File, HTTPException, Header

from fastapi import Header

@router.post("/convert-swagger/rdf", summary="Convert OpenAPI JSON to RDF and return RDF file")
async def convert_openapi(
    openapi_file: UploadFile = File(...),
    authorization: str = Header(..., alias="Authorization")
):
    try:
        openapi_bytes = await openapi_file.read()

        # Parse JSON
        try:
            swagger_data = json.loads(openapi_bytes)
        except Exception as e:
            raise HTTPException(status_code=400, detail="Invalid JSON file.") from e

        # Convert Swagger to RDF
        converter = SwaggerToRDFConverter(swagger_data)
        converter.convert()
        rdf_content = converter.serialize()

        # Prepare RDF stream
        rdf_file = io.BytesIO(rdf_content.encode("utf-8"))

        # Remove "Bearer " prefix if present
        token = authorization.replace("Bearer ", "")

        # Upload to CMS
        cms_response = upload_to_cms(
            file_stream=rdf_file,
            bearer_token=token
        )

        return cms_response

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in convert_openapi")
        raise HTTPException(status_code=500, detail="Internal server error.")


async def convert_openapi(
    openapi_file: UploadFile = File(...),
    cms_token: str = Header(..., alias="cms_token")
):
    if not openapi_file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Input must be a JSON file.")
    try:
        openapi_bytes = await openapi_file.read()
        try:
            swagger_data = json.loads(openapi_bytes)
        except Exception as e:
            raise HTTPException(status_code=400, detail="Invalid JSON file.") from e

        converter = SwaggerToRDFConverter(swagger_data)
        converter.convert()
        rdf_content = converter.serialize()

        rdf_file = io.BytesIO(rdf_content.encode("utf-8"))

        cms_response = upload_to_cms(
            file_stream=rdf_file,
            bearer_token=cms_token
        )

        return cms_response  
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in convert_openapi")
        raise HTTPException(status_code=500, detail="Internal server error.")

@router.post("/convert-swagger/ttl", summary="Convert OpenAPI JSON to Turtle (TTL)")
async def convert_to_ttl(openapi_file: UploadFile = File(...),
                        authorization: str = Header(..., alias="Authorization")):
    if not openapi_file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Input must be a .json Swagger/OpenAPI file")

    try:
        openapi_bytes = await openapi_file.read()
        swagger_data = json.loads(openapi_bytes)

        converter = OpenAPIToTTL(base_uri="http://example.org/api")
        ttl_content = converter.convert_swagger(swagger_data)

        # Prepare file for download
        ttl_stream = io.BytesIO(ttl_content.encode("utf-8"))
        
        token = authorization.replace("Bearer ", "")
        
        cms_response = upload_to_cms(
            file_stream=ttl_stream,
            bearer_token=token
        )

        return cms_response

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
    
@router.post("/content-extractor" , summary="Extracts Content from all format of the file")
async def extract_file_content(file: UploadFile = File(...)):
    suffix = "." + file.filename.split(".")[-1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
        temp.write(await file.read())
        temp.flush()
        temp_path = temp.name

    content = extract_content(temp_path)
    if content is None or not content.strip():
        raise HTTPException(status_code=400, detail="File type not supported or extraction failed.")

    return {"filename": file.filename, "content": content}