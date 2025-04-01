# Swagger to RDF Converter

## Overview
The `swaggertordf.py` script converts Swagger/OpenAPI JSON files into RDF/XML ontology format. This enhanced script captures the full structure of the API, including endpoints, parameters, request bodies, responses, and security schemes, to support potential roundtrip conversions.

## Requirements
- Python 3.x
- Required Python packages (if any, list them here)

## Usage
To run the script, use the following command:
```bash
python3 swaggertordf.py <input_swagger.json> <output_rdf.xml>
```

### Example
To convert a Swagger/OpenAPI JSON file located at `/home/gaian/Downloads/api-docs-holacracy.json` to RDF/XML format, use the following command:

```bash
python3 swaggertordf.py /home/gaian/Downloads/api-docs-holacracy.json /home/gaian/Downloads/pientityservices_latest1046.rdf
```

## Input
- **Input File**: A Swagger/OpenAPI JSON file that describes the API.

## Output
- **Output File**: An RDF/XML file that represents the API ontology.

## License
Specify the license under which your project is distributed.

## Contributing
If you would like to contribute to this project, please fork the repository and submit a pull request.

## Contact
For any inquiries, please contact [Your Name](mailto: gangavarapu.s@mobiusdtaas.ai).
