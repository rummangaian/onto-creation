from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from app.converters.openapi_to_rdf import SwaggerToRDFConverter
from app.converters.openapi_to_ttl import OpenAPIToTTL
import io
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/", summary="Testing")
async def test():
    return "Endpoint is working fine"

@router.post("/convert-swagger/rdf", summary="Convert OpenAPI JSON to RDF and return RDF file")
async def convert_openapi(openapi_file: UploadFile = File(...)):
    if not openapi_file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Input must be a JSON file.")
    try:
        openapi_bytes = await openapi_file.read()
        try:
            swagger_data = json.loads(openapi_bytes)
        except Exception as e:
            raise HTTPException(status_code=400, detail="Invalid JSON file.") from e

        converter = SwaggerToRDFConverter(swagger_data)
        converter.convert()  # Build the RDF graph
        rdf_content = converter.serialize()  # Serialize it to RDF/XML string

        rdf_file = io.BytesIO(rdf_content.encode("utf-8"))
        response = StreamingResponse(
            rdf_file,
            media_type="application/rdf+xml",
            headers={"Content-Disposition": "attachment; filename=output.rdf"}
        )
        return response
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error in convert_openapi")
        raise HTTPException(status_code=500, detail="Internal server error.")

@router.post("/convert-swagger/ttl", summary="Convert OpenAPI JSON to Turtle (TTL)")
async def convert_to_ttl(openapi_file: UploadFile = File(...)):
    if not openapi_file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Input must be a .json Swagger/OpenAPI file")

    try:
        openapi_bytes = await openapi_file.read()
        swagger_data = json.loads(openapi_bytes)

        converter = OpenAPIToTTL(base_uri="http://example.org/api")
        ttl_content = converter.convert_swagger(swagger_data)

        # Prepare file for download
        ttl_stream = io.BytesIO(ttl_content.encode("utf-8"))
        return StreamingResponse(
            ttl_stream,
            media_type="text/turtle",
            headers={"Content-Disposition": "attachment; filename=api.ttl"}
        )

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")