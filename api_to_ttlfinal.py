import json
import requests
from urllib.parse import quote, urljoin
from typing import Dict, List, Any, Optional, Set
import sys

class APIToTTL:
    def __init__(self, base_uri: str = "http://example.org/api"):
        self.service_url = base_uri.rstrip('/')
        self.base_uri = base_uri
        self.ttl_content: List[str] = []
        self.processed_refs: Set[str] = set()
        self.external_docs: Dict[str, Any] = {}
        self.current_file = None
        self.max_recursion_depth = 10  # Add recursion depth limit
        self.prefixes = {
            'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
            'rdfs': 'http://www.w3.org/2000/01/rdf-schema#',
            'owl': 'http://www.w3.org/2002/07/owl#',
            'xsd': 'http://www.w3.org/2001/XMLSchema#',
            'api': f'{self.base_uri}#',
            'service': f'{self.service_url}#'
        }
        self.swagger_doc = None

    def _write_prefixes(self) -> None:
        for prefix, uri in self.prefixes.items():
            self.ttl_content.append(f'@prefix {prefix}: <{uri}> .')
        self.ttl_content.append('')

    def _write_ontology_header(self) -> None:
        info = self.swagger_doc.get('info', {})
        title = info.get('title', 'API Ontology')
        description = info.get('description', '')
        
        self.ttl_content.extend([
            f'<{self.base_uri}> a owl:Ontology ;',
            f'    rdfs:label "{self._escape_string(title)}"^^xsd:string ;',
            f'    rdfs:comment "{self._escape_string(description)}"^^xsd:string .',
            ''
        ])

    def _write_base_classes(self) -> None:
        """Write main API classes based on tags"""
        for tag in self.swagger_doc.get('tags', []):
            class_name = self._sanitize_name(tag['name'])
            description = tag.get('description', '')
            
            self.ttl_content.extend([
                f'api:{class_name} a owl:Class ;',
                f'    rdfs:label "{tag["name"]}"@en ;',
                f'    rdfs:comment """{description}"""@en ;',
                '    .',
                ''
            ])

    def _process_paths(self) -> None:
        for path, path_item in self.swagger_doc.get('paths', {}).items():
            for method, operation in path_item.items():
                if method in ['get', 'post', 'put', 'delete', 'patch']:
                    tags = operation.get('tags', [])
                    for tag in tags:
                        self._process_operation(path, method, operation, tag)

    def _process_operation(self, path: str, method: str, operation: Dict[str, Any], tag: str) -> None:
        operation_id = operation.get('operationId', f"{method}_{self._sanitize_name(path)}")
        description = operation.get('description', '')

        # Create operation class
        operation_class = f"{tag}_{operation_id}"
        self._add_class(
            operation_class,
            description,
            [tag]  # Operation is subclass of main API class
        )

        # Process parameters if any
        if operation.get('parameters'):
            self._process_parameters(operation_class, operation['parameters'])

        # Process request body if present
        if 'requestBody' in operation:
            self._process_request_body(operation_class, operation['requestBody'])

        # Process responses
        self._process_responses(operation_class, operation.get('responses', {}))

    def _process_parameters(self, operation_class: str, parameters: List[Dict[str, Any]]) -> None:
        params_class = f"{operation_class}_Parameters"
        self._add_class(
            params_class,
            "Parameters",
            [operation_class]
        )

        for param in parameters:
            param_name = param['name']
            param_class = f"{params_class}_{self._sanitize_name(param_name)}"
            
            # Create parameter class
            self._add_class(
                param_class,
                param.get('description', ''),
                [params_class]
            )

            # Add parameter properties
            self._add_data_property(
                'name',
                param_class,
                'xsd:string',
                is_required=True,
                value=param_name
            )
            
            self._add_data_property(
                'in',
                param_class,
                'xsd:string',
                is_required=True,
                value=param.get('in', '')
            )

            self._add_data_property(
                'required',
                param_class,
                'xsd:boolean',
                value=str(param.get('required', False)).lower()
            )

            # Process schema if present
            if 'schema' in param:
                self._process_schema_attributes(param_class, param['schema'])

    def _process_request_body(self, operation_class: str, request_body: Dict[str, Any]) -> None:
        if 'content' in request_body:
            for content_type, content_def in request_body['content'].items():
                request_class = f"{operation_class}_Request"
                
                # Create request class
                self._add_class(
                    request_class,
                    request_body.get('description', ''),
                    [operation_class]
                )

                # Process schema
                if 'schema' in content_def:
                    schema = content_def['schema']
                    if '$ref' in schema:
                        ref_schema = self._resolve_schema_ref(schema['$ref'])
                        self._process_schema_attributes(request_class, ref_schema)
                    else:
                        self._process_schema_attributes(request_class, schema)

                # Process examples
                if 'examples' in content_def:
                    self._process_examples(request_class, content_def['examples'])

    def _process_responses(self, operation_class: str, responses: Dict[str, Any]) -> None:
        for status_code, response in responses.items():
            response_class = f"{operation_class}_Response_{status_code}"
            
            # Create response class
            self._add_class(
                response_class,
                response.get('description', ''),
                [operation_class]
            )

            # Process response content
            if 'content' in response:
                for content_type, content_def in response['content'].items():
                    if 'schema' in content_def:
                        self._process_schema_attributes(response_class, content_def['schema'])
                    if 'examples' in content_def:
                        self._process_examples(response_class, content_def['examples'])

    def _process_examples(self, parent_class: str, examples: Dict[str, Any]) -> None:
        for example_name, example in examples.items():
            example_class = f"{parent_class}_Example_{self._sanitize_name(example_name)}"
            
            self._add_class(
                example_class,
                example.get('description', ''),
                [parent_class]
            )

            if 'value' in example:
                self._add_data_property(
                    'value',
                    example_class,
                    'xsd:string',
                    value=json.dumps(example['value'])
                )

    def _process_schema_attributes(self, class_name: str, schema: Dict[str, Any], depth: int = 0) -> None:
        # Add depth parameter and check
        if depth >= self.max_recursion_depth:
            print(f"Warning: Maximum recursion depth reached for class {class_name}")
            return

        if 'properties' in schema:
            required_props = schema.get('required', [])
            
            for prop_name, prop_def in schema['properties'].items():
                is_required = prop_name in required_props

                if '$ref' in prop_def:
                    ref = prop_def['$ref']
                    # Skip if we've already processed this reference at this depth
                    ref_key = f"{ref}_{depth}"
                    if ref_key in self.processed_refs:
                        continue
                    self.processed_refs.add(ref_key)
                    
                    ref_schema = self._resolve_schema_ref(ref)
                    ref_class = f"{class_name}_{prop_name}"
                    self._add_class(ref_class, '', [class_name])
                    self._process_schema_attributes(ref_class, ref_schema, depth + 1)
                    self._add_object_property(prop_name, class_name, ref_class, is_required=is_required)
                elif prop_def.get('type') == 'object':
                    nested_class = f"{class_name}_{prop_name}"
                    self._add_class(nested_class, prop_def.get('description', ''), [class_name])
                    if 'properties' in prop_def:
                        self._process_schema_attributes(nested_class, prop_def, depth + 1)
                    self._add_object_property(prop_name, class_name, nested_class, is_required=is_required)
                elif prop_def.get('type') == 'array':
                    self._process_array_property(class_name, prop_name, prop_def, is_required, depth)
                else:
                    self._add_data_property(
                        prop_name,
                        class_name,
                        self._map_type_to_xsd(prop_def.get('type', 'string'), prop_def.get('format')),
                        prop_def.get('description', ''),
                        is_required=is_required
                    )

    def _process_array_property(self, class_name: str, prop_name: str, 
                              array_def: Dict[str, Any], is_required: bool, depth: int = 0) -> None:
        items = array_def.get('items', {})
        if '$ref' in items:
            ref = items['$ref']
            # Skip if we've already processed this reference at this depth
            ref_key = f"{ref}_{depth}"
            if ref_key not in self.processed_refs:
                self.processed_refs.add(ref_key)
                ref_schema = self._resolve_schema_ref(ref)
                ref_class = f"{class_name}_{prop_name}_Item"
                self._add_class(ref_class, '', [class_name])
                self._process_schema_attributes(ref_class, ref_schema, depth + 1)
                self._add_object_property(
                    prop_name,
                    class_name,
                    ref_class,
                    is_required=is_required,
                    is_collection=True
                )
        else:
            self._add_data_property(
                prop_name,
                class_name,
                self._map_type_to_xsd(items.get('type', 'string'), items.get('format')),
                array_def.get('description', ''),
                is_required=is_required,
                is_collection=True
            )

    def _resolve_schema_ref(self, ref: str) -> Dict[str, Any]:
        if not ref:
            return {}
        
        if not ref.startswith('#'):
            if '://' in ref:
                base_url = ref.split('#')[0]
                ref_path = ref.split('#')[1] if '#' in ref else ''
                
                if base_url not in self.external_docs:
                    try:
                        response = requests.get(base_url)
                        self.external_docs[base_url] = response.json()
                    except Exception as e:
                        print(f"Error fetching external reference {base_url}: {str(e)}")
                        return {}
                
                current_doc = self.external_docs[base_url]
            else:
                if self.current_file:
                    base_path = '/'.join(self.current_file.split('/')[:-1])
                    full_path = urljoin(base_path + '/', ref.split('#')[0])
                    ref_path = ref.split('#')[1] if '#' in ref else ''
                    
                    if full_path not in self.external_docs:
                        try:
                            with open(full_path, 'r') as f:
                                self.external_docs[full_path] = json.load(f)
                        except Exception as e:
                            print(f"Error reading external file {full_path}: {str(e)}")
                            return {}
                    
                    current_doc = self.external_docs[full_path]
                else:
                    return {}
        else:
            current_doc = self.swagger_doc
            ref_path = ref[1:]
        
        if ref_path:
            parts = ref_path.split('/')
            for part in parts:
                if part:
                    current_doc = current_doc.get(part, {})
        
        return current_doc

    def _add_class(self, class_name: str, description: Optional[str] = None, 
                  super_classes: List[str] = None) -> None:
        class_id = self._sanitize_name(class_name)
        
        class_def = [f'api:{class_id} a owl:Class ;']
        
        if super_classes:
            for super_class in super_classes:
                super_id = self._sanitize_name(super_class)
                class_def.append(f'    rdfs:subClassOf api:{super_id} ;')
        
        class_def.append(f'    rdfs:label "{class_name}"@en ;')
        
        if description:
            class_def.append(f'    rdfs:comment """{description}"""@en ;')
        
        class_def[-1] = class_def[-1].rstrip(' ;') + ' .'
        class_def.append('')
        
        self.ttl_content.extend(class_def)

    def _add_object_property(self, prop_name: str, domain: str, range_class: str,
                           description: Optional[str] = None, is_required: bool = False,
                           is_collection: bool = False) -> None:
        prop_id = self._sanitize_name(f"has_{prop_name}")
        domain_id = self._sanitize_name(domain)
        range_id = self._sanitize_name(range_class)
        
        lines = [f'api:{prop_id} a owl:ObjectProperty ;']
        
        if is_collection:
            lines.extend([
                f'    rdfs:domain api:{domain_id} ;',
                '    rdfs:range api:Collection ;',
                f'    api:collectionItemType api:{range_id}'
            ])
        else:
            lines.extend([
                f'    rdfs:domain api:{domain_id} ;',
                f'    rdfs:range api:{range_id}'
            ])

        if description:
            lines[-1] += ' ;'
            lines.append(f'    rdfs:comment "{self._escape_string(description)}"^^xsd:string')

        if is_required:
            lines[-1] += ' ;'
            lines.append('    owl:minCardinality "1"^^xsd:nonNegativeInteger')

        lines[-1] += ' .'
        lines.append('')
        
        self.ttl_content.extend(lines)

    def _add_data_property(self, prop_name: str, domain: str, range_type: str,
                          description: Optional[str] = None, is_required: bool = False,
                          is_collection: bool = False, value: Optional[str] = None) -> None:
        prop_id = self._sanitize_name(prop_name)
        domain_id = self._sanitize_name(domain)
        
        lines = [f'api:{prop_id} a owl:DatatypeProperty ;']
        
        if is_collection:
            lines.extend([
                f'    rdfs:domain api:{domain_id} ;',
                '    rdfs:range api:Collection ;',
                f'    api:collectionItemType {range_type}'
            ])
        else:
            lines.extend([
                f'    rdfs:domain api:{domain_id} ;',
                f'    rdfs:range {range_type}'
            ])

        if description:
            lines[-1] += ' ;'
            lines.append(f'    rdfs:comment "{self._escape_string(description)}"^^xsd:string')

        if is_required:
            lines[-1] += ' ;'
            lines.append('    owl:minCardinality "1"^^xsd:nonNegativeInteger')

        if value is not None:
            lines[-1] += ' ;'
            lines.append(f'    rdf:value "{self._escape_string(str(value))}"^^xsd:string')

        lines[-1] += ' .'
        lines.append('')
        
        self.ttl_content.extend(lines)

    def _sanitize_name(self, name: str) -> str:
        """Properly sanitize names for TTL format by removing spaces"""
        if name is None:
            return ""
        # Remove spaces, then handle other special characters
        name = name.replace(' ', '')
        return quote(name.replace('/', '_').replace('{', '').replace('}', ''))

    def _map_type_to_xsd(self, swagger_type: str, format_: Optional[str] = None) -> str:
        type_mapping = {
            'string': {
                None: 'xsd:string',
                'date': 'xsd:date',
                'date-time': 'xsd:dateTime',
                'byte': 'xsd:base64Binary',
                'binary': 'xsd:base64Binary',
                'password': 'xsd:string',
                'email': 'xsd:string',
                'uuid': 'xsd:string',
                'uri': 'xsd:anyURI'
            },
            'integer': {
                None: 'xsd:integer',
                'int32': 'xsd:int',
                'int64': 'xsd:long'
            },
            'number': {
                None: 'xsd:decimal',
                'float': 'xsd:float',
                'double': 'xsd:double'
            },
            'boolean': {
                None: 'xsd:boolean'
            },
            'object': {
                None: 'xsd:anyType'
            }
        }
        
        type_formats = type_mapping.get(swagger_type, {})
        return type_formats.get(format_, type_formats.get(None, 'xsd:string'))

    def _escape_string(self, text: str) -> str:
        """Properly escape strings for TTL format"""
        if text is None:
            return ""
        return text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

    def convert_swagger(self, swagger_doc: Dict[str, Any]) -> str:
        self.swagger_doc = swagger_doc
        
        # Write prefixes
        self._write_prefixes()
        
        # Write ontology header
        self._write_ontology_header()
        
        # Write base classes from tags
        self._write_base_classes()
        
        # Process paths and operations
        self._process_paths()
        
        # Process components/schemas
        if 'components' in swagger_doc and 'schemas' in swagger_doc['components']:
            for schema_name, schema in swagger_doc['components']['schemas'].items():
                if schema_name not in self.processed_refs:
                    self.processed_refs.add(schema_name)
                    self._add_class(schema_name, schema.get('description', ''))
                    self._process_schema_attributes(schema_name, schema)
        
        return '\n'.join(self.ttl_content)

    def write_class(self, class_name: str, comment: str = "") -> None:
        """Write a class definition to the TTL file"""
        sanitized_name = self._sanitize_name(class_name)
        self._write_line(f"api:{sanitized_name} a owl:Class ;")
        self._write_line(f'    rdfs:label "{class_name}"@en ;')
        self._write_line(f'    rdfs:comment """{comment}"""@en ;')
        self._write_line("    .")
        self._write_line("")

def process_swagger_file(file_path: str, base_uri: str = "http://example.org/api") -> str:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            swagger_doc = json.load(f)
        
        # Basic validation
        if 'openapi' not in swagger_doc and 'swagger' not in swagger_doc:
            raise ValueError("Invalid OpenAPI/Swagger document: version not specified")
        
        if 'info' not in swagger_doc:
            raise ValueError("Invalid OpenAPI/Swagger document: missing info section")
        
        if 'paths' not in swagger_doc:
            raise ValueError("Invalid OpenAPI/Swagger document: missing paths section")
        
        converter = APIToTTL(base_uri)
        return converter.convert_swagger(swagger_doc)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in Swagger file: {str(e)}")
    except Exception as e:
        raise Exception(f"Error converting Swagger to TTL: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python api_to_ttl.py <swagger_file> <base_uri>")
        sys.exit(1)
    
    try:
        ttl_content = process_swagger_file(sys.argv[1], sys.argv[2])
        output_file = sys.argv[1].rsplit('.', 1)[0] + '.ttl'
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(ttl_content)
        print(f"Successfully generated ontology: {output_file}")
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)