from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from app.converters.swagger_to_rdf import SwaggerToRDFConverter
import io
import json

router = APIRouter()

@router.get("/" , summary="Testing")
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
        rdf_content = converter.convert_to_rdf()

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
        raise HTTPException(status_code=500, detail="Internal server error.")
