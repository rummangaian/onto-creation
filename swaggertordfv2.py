#!/usr/bin/env python3
"""
enhanced_swagger_to_rdf.py - Convert Swagger/OpenAPI JSON to RDF/XML ontology
with comprehensive relationship modeling for roundtrip transformation

This enhanced script creates a more detailed ontology representation that captures
the full structure of the API including endpoints, parameters, request bodies,
responses, and security schemes to support potential roundtrip conversions.

Usage:
    python enhanced_swagger_to_rdf.py <input_swagger.json> <output_rdf.xml>
"""

import json
import sys
import os
import re
import html
import argparse
import traceback
from datetime import datetime
from urllib.parse import urlparse


class EnhancedSwaggerToRDFConverter:
    """Converts Swagger/OpenAPI JSON to RDF/XML ontology format with comprehensive relationship modeling."""
    
    def __init__(self, swagger_data):
        """Initialize with parsed Swagger/OpenAPI JSON data."""
        self.swagger_data = swagger_data
        
        # Extract the base info
        self.api_title = self.swagger_data.get('info', {}).get('title', 'API').strip()
        self.api_description = self.swagger_data.get('info', {}).get('description', '').strip()
        self.api_version = self.swagger_data.get('info', {}).get('version', '1.0').strip()
        
        # Namespace and prefix configs
        self.base_uri = f"https://w3id.org/api/{self.sanitize_for_uri(self.api_title)}/"
        self.ontology_version_uri = f"{self.base_uri}{self.api_version}/"
        
        # Track objects to prevent duplicates
        self.classes = set()
        self.object_properties = set()
        self.data_properties = set()
        self.individuals = set()
        self.annotation_properties = set()
        
        # Track controller-specific elements
        self.controllers = {}
        
        # Track endpoints, parameters, request bodies, and responses
        self.endpoints = {}
        self.request_bodies = {}
        self.responses = {}
        self.parameters = {}
        
        # Track schema classes identified from request bodies and responses
        self.request_body_schemas = {}
        self.response_schemas = {}
        
        # Track HTTP method classes
        self.http_methods = {}
        
        # Map of $ref pointers to resolved schemas for caching
        self.resolved_refs = {}
        
    def extract_controllers_and_endpoints(self):
        """Extract API controllers from tags and endpoints from paths with their relationships."""
        try:
            # First, identify all unique tags used in the paths
            used_tags = set()
            # Also track all endpoints found in the API
            endpoints = {}
            
            for path, path_item in self.swagger_data.get('paths', {}).items():
                for method, operation in path_item.items():
                    if method.lower() not in ['get', 'post', 'put', 'delete', 'patch', 'options', 'head']:
                        continue

                    # Generate a unique endpoint ID
                    endpoint_id = self.sanitize_for_uri(f"{method}-{path}")
                    operation_id = operation.get('operationId', endpoint_id)
                    
                    # Extract all tags associated with this endpoint
                    operation_tags = operation.get('tags', [])
                    for tag in operation_tags:
                        used_tags.add(tag)
                    
                    # Store the endpoint details
                    endpoints[endpoint_id] = {
                        'path': path,
                        'method': method.upper(),
                        'operationId': operation_id,
                        'tags': operation_tags,
                        'summary': operation.get('summary', ''),
                        'description': operation.get('description', ''),
                        'parameters': operation.get('parameters', []),
                        'requestBody': operation.get('requestBody', None),
                        'responses': operation.get('responses', {})
                    }
                    
                    # Process parameters for this endpoint
                    path_params = self.extract_path_parameters(path)
                    for path_param in path_params:
                        # Check if parameter is already defined
                        param_defined = False
                        for param in operation.get('parameters', []):
                            if param.get('name') == path_param and param.get('in') == 'path':
                                param_defined = True
                                break
                        
                        # If parameter not defined, add it to our tracking
                        if not param_defined:
                            param_id = self.sanitize_for_uri(f"{endpoint_id}-param-{path_param}")
                            self.parameters[param_id] = {
                                'name': path_param,
                                'in': 'path',
                                'required': True,
                                'endpoint': endpoint_id,
                                'schema': {'type': 'string'},
                                'description': f'Path parameter {path_param} for {path}'
                            }
                    
                    # Process defined parameters
                    for param in operation.get('parameters', []):
                        param_id = self.sanitize_for_uri(f"{endpoint_id}-param-{param.get('name')}")
                        self.parameters[param_id] = {
                            'name': param.get('name'),
                            'in': param.get('in'),
                            'required': param.get('required', False),
                            'endpoint': endpoint_id,
                            'schema': param.get('schema', {'type': 'string'}),
                            'description': param.get('description', f"Parameter {param.get('name')} for {path}")
                        }
                    
                    # Process request body if present
                    if 'requestBody' in operation:
                        req_body = operation['requestBody']
                        req_body_id = self.sanitize_for_uri(f"{endpoint_id}-request-body")
                        
                        content_schemas = {}
                        for content_type, content_def in req_body.get('content', {}).items():
                            if 'schema' in content_def:
                                schema = content_def['schema']
                                schema_id = None
                                
                                # Extract schema reference if present
                                if '$ref' in schema:
                                    ref = schema['$ref']
                                    schema_id = ref.split('/')[-1]
                                    # Add to request body schemas for this endpoint
                                    if schema_id not in self.request_body_schemas:
                                        self.request_body_schemas[schema_id] = []
                                    if endpoint_id not in self.request_body_schemas[schema_id]:
                                        self.request_body_schemas[schema_id].append(endpoint_id)
                                
                                content_schemas[content_type] = schema_id or 'object'
                        
                        self.request_bodies[req_body_id] = {
                            'endpoint': endpoint_id,
                            'required': req_body.get('required', False),
                            'content': content_schemas,
                            'description': req_body.get('description', f"Request body for {path} {method}")
                        }
                        
                        # Update endpoint with reference to request body
                        endpoints[endpoint_id]['requestBodyId'] = req_body_id
                    
                    # Process responses
                    for status_code, response in operation.get('responses', {}).items():
                        resp_id = self.sanitize_for_uri(f"{endpoint_id}-response-{status_code}")
                        
                        content_schemas = {}
                        for content_type, content_def in response.get('content', {}).items():
                            if 'schema' in content_def:
                                schema = content_def['schema']
                                schema_id = None
                                
                                # Extract schema reference if present
                                if '$ref' in schema:
                                    ref = schema['$ref']
                                    schema_id = ref.split('/')[-1]
                                    # Add to response schemas for this endpoint
                                    if schema_id not in self.response_schemas:
                                        self.response_schemas[schema_id] = []
                                    if endpoint_id not in self.response_schemas[schema_id]:
                                        self.response_schemas[schema_id].append(endpoint_id)
                                
                                content_schemas[content_type] = schema_id or 'object'
                        
                        self.responses[resp_id] = {
                            'endpoint': endpoint_id,
                            'statusCode': status_code,
                            'content': content_schemas,
                            'description': response.get('description', f"Response {status_code} for {path} {method}")
                        }
                        
                        # Update endpoint responses
                        if 'responseIds' not in endpoints[endpoint_id]:
                            endpoints[endpoint_id]['responseIds'] = []
                        endpoints[endpoint_id]['responseIds'].append(resp_id)

            # Initialize all controllers found in operations
            controllers = {}
            for tag in used_tags:
                controllers[tag] = {
                    'description': '',  # Will be updated if found in tags section
                    'endpoints': []  # This will hold the endpoints associated with this tag
                }

            # Update with descriptions from tags section if available
            for tag_def in self.swagger_data.get('tags', []):
                tag_name = tag_def.get('name', '')
                tag_desc = tag_def.get('description', '')
                if tag_name in controllers:
                    controllers[tag_name]['description'] = tag_desc

            # Associate endpoints with their controllers based on tags
            for endpoint_id, endpoint in endpoints.items():
                for tag in endpoint['tags']:
                    if tag in controllers:
                        if endpoint_id not in controllers[tag]['endpoints']:
                            controllers[tag]['endpoints'].append(endpoint_id)

            self.controllers = controllers
            self.endpoints = endpoints
            
            print(f"Extracted {len(self.controllers)} controllers with {len(self.endpoints)} endpoints")
            print(f"Found {len(self.parameters)} parameters, {len(self.request_bodies)} request bodies, and {len(self.responses)} responses")

        except Exception as e:
            print(f"Error in extract_controllers_and_endpoints: {e}")
            print(traceback.format_exc())
            raise

    def generate_base_classes(self):
        """Generate foundational base classes for the ontology."""
        classes_output = """

        <!-- 
        ///////////////////////////////////////////////////////////////////////////////////////
        //
        // Base Classes
        //
        ///////////////////////////////////////////////////////////////////////////////////////
        -->
    """
        # Define API as the root class
        api_class_uri = "http://www.w3.org/2002/07/owl#API"
        api_class_def = """
        <owl:Class rdf:about="http://www.w3.org/2002/07/owl#API">
            <rdfs:label xml:lang="en">API</rdfs:label>
            <rdfs:comment xml:lang="en">Root class for all API-related concepts</rdfs:comment>
        </owl:Class>
    """
        classes_output += api_class_def
        
    #     # Define OWL:Class as a subclass of API for proper hierarchy
    #     owl_class_def = """
    #     <owl:Class rdf:about="http://www.w3.org/2002/07/owl#API">
    #         <rdfs:label xml:lang="en">Any Class</rdfs:label>
    #         <rdfs:comment xml:lang="en">RDF Class</rdfs:comment>
    #         <rdfs:subClassOf rdf:resource="http://www.w3.org/2002/07/owl#API"/>
    #     </owl:Class>
    # """
    #     classes_output += owl_class_def
        
        return classes_output    

    def extract_path_parameters(self, path):
        """Extract parameter names from path template like /path/{param1}/subpath/{param2}."""
        # Find all segments like {paramName}
        param_matches = re.findall(r'\{([^{}]+)\}', path)
        return param_matches
    
    def sanitize_for_uri(self, text):
        """Convert text to a form suitable for use in URIs."""
        if not text:
            return "unnamed"
            
        # Remove special characters, replace spaces and slashes with hyphens
        sanitized = re.sub(r'[^a-zA-Z0-9\-_]', '', str(text).replace(' ', '-').replace('/', '-').lower())
        # Ensure we don't have double hyphens
        sanitized = re.sub(r'-+', '-', sanitized)
        # Remove leading/trailing hyphens
        sanitized = sanitized.strip('-')
        
        if not sanitized:
            return "unnamed"
            
        return sanitized
    
    def sanitize_text(self, text):
        """Sanitize text for XML output."""
        if text is None:
            return ""
        if not isinstance(text, str):
            text = str(text)
        return html.escape(text)
    
    def resolve_ref(self, ref):
        """Resolve a JSON reference ($ref) to the actual schema."""
        if ref in self.resolved_refs:
            return self.resolved_refs[ref]
            
        if not ref.startswith('#/'):
            # External references not supported in this version
            return None
            
        path_parts = ref.replace('#/', '').split('/')
        schema = self.swagger_data
        
        try:
            for part in path_parts:
                schema = schema[part]
            
            self.resolved_refs[ref] = schema
            return schema
        except (KeyError, TypeError):
            return None
        
    def generate_http_method_classes(self):
        """Generate classes for HTTP methods (GET, POST, PUT, DELETE, PATCH, etc.)."""
        classes_output = """

        <!-- 
        ///////////////////////////////////////////////////////////////////////////////////////
        //
        // HTTP Method Classes
        //
        ///////////////////////////////////////////////////////////////////////////////////////
        -->
    """
        # Define the base HTTP Method class
        method_class_uri = f"{self.base_uri}HttpMethod"
        method_class_name = "HttpMethod"
        
        # Add to our set of classes
        self.classes.add(method_class_name)
        
        # Create the base HTTP Method class
        class_def = f"""
        <owl:Class rdf:about="{method_class_uri}">
            <rdfs:label xml:lang="en">HTTP Method</rdfs:label>
            <rdfs:comment xml:lang="en">Base class for all HTTP methods</rdfs:comment>
        </owl:Class>
    """
        classes_output += class_def
        
        # Create subclasses for different HTTP methods
        http_methods = {
            "GET": "GetMethod",
            "POST": "PostMethod",
            "PUT": "PutMethod",
            "DELETE": "DeleteMethod",
            "PATCH": "PatchMethod",
            "OPTIONS": "OptionsMethod",
            "HEAD": "HeadMethod"
        }
        
        for method, class_name in http_methods.items():
            method_uri = f"{self.base_uri}{class_name}"
            
            # Add to our set of classes
            self.classes.add(class_name)
            
            method_def = f"""
        <owl:Class rdf:about="{method_uri}">
            <rdfs:label xml:lang="en">{class_name}</rdfs:label>
            <rdfs:comment xml:lang="en">HTTP {method} method</rdfs:comment>
            <rdfs:subClassOf rdf:resource="{method_class_uri}"/>
        </owl:Class>
    """
            classes_output += method_def
        
        return classes_output, http_methods

    
    def convert_to_rdf(self):
        """Convert the Swagger JSON to RDF/XML format."""
        try:
            # Extract controllers and endpoints first
            self.extract_controllers_and_endpoints()
            
            rdf_output = self.generate_rdf_header()
            
            # Add annotation properties
            rdf_output += self.generate_annotation_properties()

            # Generate base classes (API and OWL:Class)
            rdf_output += self.generate_base_classes()

            # Generate Title Class as the root
            rdf_output += self.generate_title_class()
            
            # Generate HTTP Method classes
            http_method_classes, self.http_methods = self.generate_http_method_classes()
            rdf_output += http_method_classes
            
            # Generate controller classes
            rdf_output += self.generate_controller_classes()
            
            # Generate endpoint classes
            rdf_output += self.generate_endpoint_classes()
            
            # Generate parameter classes
            rdf_output += self.generate_parameter_classes()
            
            # Generate request body classes
            rdf_output += self.generate_request_body_classes()
            
            # Generate response classes
            rdf_output += self.generate_response_classes()
            
            # Process schemas to create schema classes
            schema_classes = self.generate_schema_classes()
            
            # Process schemas to create object properties
            object_props = self.generate_object_properties()
            
            # Process schemas to create data properties
            data_props = self.generate_data_properties()
            
            # Add the properties to the output
            rdf_output += schema_classes
            rdf_output += object_props
            rdf_output += data_props
            
            # Add individuals from examples and enums
            rdf_output += self.generate_individuals()
            
            # Close the RDF document
            rdf_output += '\n</rdf:RDF>'
            
            return rdf_output
        except Exception as e:
            print(f"Error in convert_to_rdf: {e}")
            print(traceback.format_exc())
            raise
    
    def generate_rdf_header(self):
        """Generate the RDF/XML header with namespace declarations."""
        current_date = datetime.now().strftime('%Y-%m-%d')
        server_url = "#"
        
        if 'servers' in self.swagger_data and self.swagger_data['servers']:
            server_url = self.swagger_data['servers'][0].get('url', '#')
        
        header = f"""<?xml version="1.0"?>
<rdf:RDF xmlns="{self.base_uri}"
     xml:base="{self.base_uri}"
     xmlns:dc="http://purl.org/dc/elements/1.1/"
     xmlns:ns="http://creativecommons.org/ns#"
     xmlns:owl="http://www.w3.org/2002/07/owl#"
     xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
     xmlns:xml="http://www.w3.org/XML/1998/namespace"
     xmlns:xsd="http://www.w3.org/2001/XMLSchema#"
     xmlns:api="{self.base_uri}"
     xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
     xmlns:skos="http://www.w3.org/2004/02/skos/core#"
     xmlns:vann="http://purl.org/vocab/vann/"
     xmlns:terms="http://purl.org/dc/terms/"
     xmlns:o2o="https://karlhammar.com/owl2oas/o2o.owl#"
     xmlns:cc="http://creativecommons.org/ns#">
    <owl:Ontology rdf:about="{self.base_uri}">
        <owl:versionIRI rdf:resource="{self.ontology_version_uri}"/>
        <dc:creator>Enhanced Swagger to RDF Converter</dc:creator>
        <dc:description xml:lang="en">{self.sanitize_text(self.api_description)}</dc:description>
        <dc:publisher>Generated from Swagger/OpenAPI</dc:publisher>
        <dc:title xml:lang="en">{self.sanitize_text(self.api_title)} API Ontology</dc:title>
        <terms:modified>{current_date}</terms:modified>
        <vann:preferredNamespacePrefix>api</vann:preferredNamespacePrefix>
        <vann:preferredNamespaceUri>{self.base_uri}</vann:preferredNamespaceUri>
        <rdfs:seeAlso rdf:resource="{self.sanitize_text(server_url)}"/>
        <owl:versionInfo rdf:datatype="http://www.w3.org/2001/XMLSchema#string">{self.sanitize_text(self.api_version)}</owl:versionInfo>
        <cc:license rdf:resource="https://creativecommons.org/licenses/by/4.0/"/>
    </owl:Ontology>
"""
        return header
    
    def generate_annotation_properties(self):
        """Generate common annotation properties used in the ontology."""
        # Define important annotation properties for our ontology
        annotations = [
            "http://purl.org/dc/elements/1.1/description",
            "http://purl.org/dc/elements/1.1/title",
            "http://www.w3.org/2000/01/rdf-schema#seeAlso",
            "http://purl.org/dc/elements/1.1/example",
            "http://purl.org/dc/elements/1.1/required",
            "http://purl.org/dc/elements/1.1/format",
            "http://purl.org/dc/elements/1.1/pattern",
            "http://purl.org/dc/elements/1.1/method",
            "http://purl.org/dc/elements/1.1/path",
            "https://karlhammar.com/owl2oas/o2o.owl#endpoint",
            "https://karlhammar.com/owl2oas/o2o.owl#included",
            "http://purl.org/dc/elements/1.1/mediaType",
            "http://purl.org/dc/elements/1.1/statusCode",
            "http://purl.org/dc/elements/1.1/parameterIn",
            "http://purl.org/dc/elements/1.1/operationId"
        ]
        
        # Add all these to our set of defined annotation properties
        for annotation in annotations:
            if annotation.startswith("http://"):
                annotation_name = annotation.split("/")[-1]
                self.annotation_properties.add(annotation_name)
        
        output = """

    <!-- 
    ///////////////////////////////////////////////////////////////////////////////////////
    //
    // Annotation properties
    //
    ///////////////////////////////////////////////////////////////////////////////////////
     -->
"""
        
        for annotation in annotations:
            output += f"""
    <owl:AnnotationProperty rdf:about="{annotation}"/>"""
            
        return output
    
    def generate_title_class(self):
        """Generate an OWL class for the API title."""
        classes_output = """

    <!-- 
    ///////////////////////////////////////////////////////////////////////////////////////
    //
    // Title Class
    //
    ///////////////////////////////////////////////////////////////////////////////////////
    -->
"""
        # Use the stored API title
        clean_title = self.sanitize_for_uri(self.api_title)
        class_uri = f"{self.base_uri}{clean_title}"

        # Add to our set of classes
        self.classes.add(clean_title)

        # Create the class definition
        class_def = f"""
    <owl:Class rdf:about="{class_uri}">
        <rdfs:label xml:lang="en">{self.sanitize_text(self.api_title)}</rdfs:label>
        <dc:description xml:lang="en">{self.sanitize_text(self.api_description)}</dc:description>
        <dc:title xml:lang="en">{self.sanitize_text(self.api_title)}</dc:title>
    </owl:Class>
"""

        classes_output += class_def
        return classes_output

    def generate_controller_classes(self):
        """Generate classes for API controllers based on tags."""
        classes_output = """

    <!-- 
    ///////////////////////////////////////////////////////////////////////////////////////
    //
    // Controller Classes
    //
    ///////////////////////////////////////////////////////////////////////////////////////
    -->
"""
        # Use the API title as the base class
        title_class = self.sanitize_for_uri(self.api_title)
        
        # Create a class for each controller based on tags
        for controller_name, controller_info in self.controllers.items():
            # Sanitize the controller name for use as a class name
            clean_name = self.sanitize_for_uri(controller_name)
            class_uri = f"{self.base_uri}{clean_name}"

            # Add to our set of classes
            self.classes.add(clean_name)

            # Create the class definition
            class_def = f"""
    <owl:Class rdf:about="{class_uri}">
        <rdfs:label xml:lang="en">{self.sanitize_text(controller_name)}</rdfs:label>
        <rdfs:comment xml:lang="en">{self.sanitize_text(controller_info['description'])}</rdfs:comment>
        <dc:description xml:lang="en">API Controller</dc:description>
        <rdfs:subClassOf rdf:resource="{self.base_uri}{title_class}"/>
    </owl:Class>
"""
            
            classes_output += class_def
            
            # Create object property that connects this controller with its endpoints
            has_endpoint_prop = f"has{clean_name}Endpoint"
            if has_endpoint_prop not in self.object_properties:
                self.object_properties.add(has_endpoint_prop)
                prop_uri = f"{self.base_uri}{has_endpoint_prop}"
                
                prop_def = f"""
    <owl:ObjectProperty rdf:about="{prop_uri}">
        <rdfs:label xml:lang="en">has {controller_name} endpoint</rdfs:label>
        <rdfs:comment xml:lang="en">Relates {controller_name} controller to its endpoints</rdfs:comment>
        <rdfs:domain rdf:resource="{class_uri}"/>
        <rdfs:range rdf:resource="http://www.w3.org/2002/07/owl#API"/>
    </owl:ObjectProperty>
"""
                classes_output += prop_def
                
        return classes_output

    def generate_endpoint_classes(self):
        """Generate classes for API endpoints with their HTTP methods and paths."""
        classes_output = """

        <!-- 
        ///////////////////////////////////////////////////////////////////////////////////////
        //
        // Endpoint Classes
        //
        ///////////////////////////////////////////////////////////////////////////////////////
        -->
    """
        # Create a class for each endpoint
        for endpoint_id, endpoint in self.endpoints.items():
            # Create a class name based on the operation ID or method+path
            if endpoint.get('operationId'):
                class_name = self.sanitize_for_uri(endpoint['operationId'])
            else:
                class_name = endpoint_id
            
            class_uri = f"{self.base_uri}{class_name}"
            
            # Add to our set of classes
            self.classes.add(class_name)
            
            # Get the controller(s) this endpoint belongs to
            controller_tags = endpoint.get('tags', [])
            
            # Get the HTTP method for this endpoint
            http_method = endpoint['method'].upper()
            http_method_class = self.http_methods.get(http_method)
            
            # Build the class definition
            class_def = f"""
        <owl:Class rdf:about="{class_uri}">
            <rdfs:label xml:lang="en">{endpoint.get('summary') or f"{endpoint['method']} {endpoint['path']}"}</rdfs:label>
            <rdfs:comment xml:lang="en">{self.sanitize_text(endpoint.get('description', ''))}</rdfs:comment>
            <dc:method xml:lang="en">{endpoint['method']}</dc:method>
            <dc:path xml:lang="en">{self.sanitize_text(endpoint['path'])}</dc:path>
            <dc:operationId xml:lang="en">{self.sanitize_text(endpoint.get('operationId', ''))}</dc:operationId>
            <o2o:endpoint>{endpoint['method']} {self.sanitize_text(endpoint['path'])}</o2o:endpoint>
    """
            
            # Add HTTP method relationship
            if http_method_class:
                class_def += f'        <rdfs:subClassOf rdf:resource="{self.base_uri}{http_method_class}"/>\n'
            
            # Add controller relationships
            for tag in controller_tags:
                clean_tag = self.sanitize_for_uri(tag)
                class_def += f'        <rdfs:subClassOf rdf:resource="{self.base_uri}{clean_tag}"/>\n'
            
            # If no tags, make it a direct subclass of the API
            if not controller_tags:
                title_class = self.sanitize_for_uri(self.api_title)
                class_def += f'        <rdfs:subClassOf rdf:resource="{self.base_uri}{title_class}"/>\n'
            
            class_def += "    </owl:Class>\n"
            classes_output += class_def
            
            # Create properties for parameters, request body, and responses
            if endpoint.get('requestBodyId'):
                has_request_prop = f"has{class_name}RequestBody"
                req_body_id = endpoint['requestBodyId'] 
                
                if has_request_prop not in self.object_properties:
                    self.object_properties.add(has_request_prop)
                    prop_uri = f"{self.base_uri}{has_request_prop}"
                    
                    prop_def = f"""
        <owl:ObjectProperty rdf:about="{prop_uri}">
        <rdfs:label xml:lang="en">has request body</rdfs:label>
        <rdfs:comment xml:lang="en">Relates endpoint {class_name} to its request body</rdfs:comment>
        <rdfs:domain rdf:resource="{class_uri}"/>
        <rdfs:range rdf:resource="{self.base_uri}{self.http_methods.get(self.endpoints[endpoint_id]['method'].upper())}"/>
    </owl:ObjectProperty>
    """
                    classes_output += prop_def
            
            # Add response relationships
            if endpoint.get('responseIds'):
                has_response_prop = f"has{class_name}Response"
                
                if has_response_prop not in self.object_properties:
                    self.object_properties.add(has_response_prop)
                    prop_uri = f"{self.base_uri}{has_response_prop}"
                    
                    prop_def = f"""
        <owl:ObjectProperty rdf:about="{prop_uri}">
            <rdfs:label xml:lang="en">has response</rdfs:label>
            <rdfs:comment xml:lang="en">Relates endpoint {class_name} to its responses</rdfs:comment>
            <rdfs:domain rdf:resource="{class_uri}"/>
            <rdfs:range rdf:resource="http://www.w3.org/2002/07/owl#API"/>
        </owl:ObjectProperty>
    """
                    classes_output += prop_def
        
        return classes_output

    def generate_parameter_classes(self):
        """Generate classes for API parameters."""
        classes_output = """

        <!-- 
        ///////////////////////////////////////////////////////////////////////////////////////
        //
        // Parameter Classes
        //
        ///////////////////////////////////////////////////////////////////////////////////////
        -->
    """
        # Create a class for parameters
        param_class_uri = f"{self.base_uri}Parameter"
        param_class_name = "Parameter"
        
        # Add to our set of classes
        self.classes.add(param_class_name)
        
        # Create the base parameter class
        class_def = f"""
        <owl:Class rdf:about="{param_class_uri}">
            <rdfs:label xml:lang="en">Parameter</rdfs:label>
            <rdfs:comment xml:lang="en">Base class for all API parameters</rdfs:comment>
        </owl:Class>
    """
        classes_output += class_def
        
        # Create subclasses for different parameter types
        param_types = {
            "path": "PathParameter",
            "query": "QueryParameter",
            "header": "HeaderParameter",
            "cookie": "CookieParameter"
        }
        
        for param_type, class_name in param_types.items():
            type_uri = f"{self.base_uri}{class_name}"
            
            # Add to our set of classes
            self.classes.add(class_name)
            
            type_def = f"""
        <owl:Class rdf:about="{type_uri}">
            <rdfs:label xml:lang="en">{class_name}</rdfs:label>
            <rdfs:comment xml:lang="en">Parameter that appears in the {param_type}</rdfs:comment>
            <rdfs:subClassOf rdf:resource="{param_class_uri}"/>
        </owl:Class>
    """
            classes_output += type_def
        
        # Now create individual parameter instances
        for param_id, param in self.parameters.items():
            param_name = param.get('name', 'unnamed')
            param_in = param.get('in', 'query')
            endpoint_id = param.get('endpoint', '')
            
            # Extract the HTTP method from the endpoint_id
            http_method = None
            if endpoint_id in self.endpoints:
                http_method = self.endpoints[endpoint_id]['method'].upper()
                http_method_class = self.http_methods.get(http_method)
            
            # Determine the appropriate parameter class
            param_class = param_types.get(param_in, "Parameter")
            
            # Create the parameter instance
            instance_uri = f"{self.base_uri}{param_id}"
            
            instance_def = f"""
        <owl:NamedIndividual rdf:about="{instance_uri}">
            <rdf:type rdf:resource="{self.base_uri}{param_class}"/>
            <rdfs:label xml:lang="en">{self.sanitize_text(param_name)}</rdfs:label>
            <dc:description xml:lang="en">{self.sanitize_text(param.get('description', ''))}</dc:description>
            <dc:parameterIn xml:lang="en">{param_in}</dc:parameterIn>
            <dc:required xml:lang="en">{str(param.get('required', False)).lower()}</dc:required>
    """
            
            # Add HTTP method relationship if available
            if http_method and http_method_class:
                instance_def += f'        <api:belongsToHttpMethod rdf:resource="{self.base_uri}{http_method_class}"/>\n'
            
            # Add schema type if available
            schema = param.get('schema', {})
            if 'type' in schema:
                instance_def += f'        <dc:format xml:lang="en">{self.sanitize_text(schema["type"])}</dc:format>\n'
            
            # Add endpoint relationship
            if endpoint_id and endpoint_id in self.endpoints:
                instance_def += f'        <api:belongsToEndpoint rdf:resource="{self.base_uri}{self.sanitize_for_uri(endpoint_id)}"/>\n'
            
            instance_def += "    </owl:NamedIndividual>\n"
            classes_output += instance_def
        
        # Create the object property that relates endpoints to parameters if not already defined
        belongs_to_endpoint_prop = "belongsToEndpoint"
        if belongs_to_endpoint_prop not in self.object_properties:
            self.object_properties.add(belongs_to_endpoint_prop)
            prop_uri = f"{self.base_uri}{belongs_to_endpoint_prop}"
            
            prop_def = f"""
        <owl:ObjectProperty rdf:about="{prop_uri}">
            <rdfs:label xml:lang="en">belongs to endpoint</rdfs:label>
            <rdfs:comment xml:lang="en">Relates a parameter to its endpoint</rdfs:comment>
            <rdfs:domain rdf:resource="{param_class_uri}"/>
            <rdfs:range rdf:resource="http://www.w3.org/2002/07/owl#API"/>
        </owl:ObjectProperty>
    """
            classes_output += prop_def
        
        return classes_output

    def generate_request_body_classes(self):
        """Generate classes for API request bodies."""
        classes_output = """

        <!-- 
        ///////////////////////////////////////////////////////////////////////////////////////
        //
        // Request Body Classes
        //
        ///////////////////////////////////////////////////////////////////////////////////////
        -->
    """
        # Create a base class for request bodies
        req_body_class_uri = f"{self.base_uri}RequestBody"
        req_body_class_name = "RequestBody"
        
        # Add to our set of classes
        self.classes.add(req_body_class_name)
        
        # Create the base request body class
        class_def = f"""
        <owl:Class rdf:about="{req_body_class_uri}">
            <rdfs:label xml:lang="en">Request Body</rdfs:label>
            <rdfs:comment xml:lang="en">Base class for all API request bodies</rdfs:comment>
        </owl:Class>
    """
        classes_output += class_def
        
        # Now create individual request body instances
        for req_body_id, req_body in self.request_bodies.items():
            endpoint_id = req_body.get('endpoint', '')
            
            # Create the request body instance
            instance_uri = f"{self.base_uri}{req_body_id}"
            
            # Extract the HTTP method from the endpoint_id
            http_method = None
            if endpoint_id in self.endpoints:
                http_method = self.endpoints[endpoint_id]['method'].upper()
                http_method_class = self.http_methods.get(http_method)
            
            instance_def = f"""
        <owl:NamedIndividual rdf:about="{instance_uri}">
            <rdf:type rdf:resource="{req_body_class_uri}"/>
            <rdfs:label xml:lang="en">Request Body for {endpoint_id}</rdfs:label>
            <dc:description xml:lang="en">{self.sanitize_text(req_body.get('description', ''))}</dc:description>
            <dc:required xml:lang="en">{str(req_body.get('required', False)).lower()}</dc:required>
    """
            
            # Add HTTP method relationship if available
            if http_method and http_method_class:
                instance_def += f'        <api:belongsToHttpMethod rdf:resource="{self.base_uri}{http_method_class}"/>\n'
            
            # Add content type information
            for content_type, schema_id in req_body.get('content', {}).items():
                instance_def += f'        <dc:mediaType xml:lang="en">{self.sanitize_text(content_type)}</dc:mediaType>\n'
                
                # Add schema reference if available
                if schema_id and schema_id != 'object' and schema_id in self.swagger_data.get('components', {}).get('schemas', {}):
                    instance_def += f'        <api:hasSchema rdf:resource="{self.base_uri}{schema_id}"/>\n'
            
            # Add endpoint relationship
            if endpoint_id and endpoint_id in self.endpoints:
                instance_def += f'        <api:belongsToEndpoint rdf:resource="{self.base_uri}{self.sanitize_for_uri(endpoint_id)}"/>\n'
            
            instance_def += "    </owl:NamedIndividual>\n"
            classes_output += instance_def
        
        # Create the object property that relates schemas to request bodies if not already defined
        has_schema_prop = "hasSchema"
        if has_schema_prop not in self.object_properties:
            self.object_properties.add(has_schema_prop)
            prop_uri = f"{self.base_uri}{has_schema_prop}"
            
            prop_def = f"""
        <owl:ObjectProperty rdf:about="{prop_uri}">
            <rdfs:label xml:lang="en">has schema</rdfs:label>
            <rdfs:comment xml:lang="en">Relates a request body or response to its schema</rdfs:comment>
            <rdfs:domain rdf:resource="http://www.w3.org/2002/07/owl#API"/>
            <rdfs:range rdf:resource="http://www.w3.org/2002/07/owl#API"/>
        </owl:ObjectProperty>
    """
            classes_output += prop_def
        
        # Create the object property that relates HTTP methods to elements
        belongs_to_http_method_prop = "belongsToHttpMethod"
        if belongs_to_http_method_prop not in self.object_properties:
            self.object_properties.add(belongs_to_http_method_prop)
            prop_uri = f"{self.base_uri}{belongs_to_http_method_prop}"
            
            prop_def = f"""
        <owl:ObjectProperty rdf:about="{prop_uri}">
            <rdfs:label xml:lang="en">belongs to HTTP method</rdfs:label>
            <rdfs:comment xml:lang="en">Relates an element to its HTTP method</rdfs:comment>
            <rdfs:range rdf:resource="{self.base_uri}HttpMethod"/>
        </owl:ObjectProperty>
    """
            classes_output += prop_def
            
        return classes_output

    def generate_response_classes(self):
        """Generate classes for API responses."""
        classes_output = """

        <!-- 
        ///////////////////////////////////////////////////////////////////////////////////////
        //
        // Response Classes
        //
        ///////////////////////////////////////////////////////////////////////////////////////
        -->
    """
        # Create a base class for responses
        resp_class_uri = f"{self.base_uri}Response"
        resp_class_name = "Response"
        
        # Add to our set of classes
        self.classes.add(resp_class_name)
        
        # Create the base response class
        class_def = f"""
        <owl:Class rdf:about="{resp_class_uri}">
            <rdfs:label xml:lang="en">Response</rdfs:label>
            <rdfs:comment xml:lang="en">Base class for all API responses</rdfs:comment>
        </owl:Class>
    """
        classes_output += class_def
        
        # Create subclasses for different response types
        resp_types = {
            "200": "SuccessResponse", 
            "201": "CreatedResponse",
            "400": "BadRequestResponse",
            "401": "UnauthorizedResponse",
            "403": "ForbiddenResponse",
            "404": "NotFoundResponse",
            "500": "ServerErrorResponse"
        }
        
        for status_code, class_name in resp_types.items():
            type_uri = f"{self.base_uri}{class_name}"
            
            # Add to our set of classes
            self.classes.add(class_name)
            
            type_def = f"""
        <owl:Class rdf:about="{type_uri}">
            <rdfs:label xml:lang="en">{class_name}</rdfs:label>
            <rdfs:comment xml:lang="en">Response with status code {status_code}</rdfs:comment>
            <rdfs:subClassOf rdf:resource="{resp_class_uri}"/>
            <dc:statusCode xml:lang="en">{status_code}</dc:statusCode>
        </owl:Class>
    """
            classes_output += type_def
        
        # Now create individual response instances
        for resp_id, response in self.responses.items():
            endpoint_id = response.get('endpoint', '')
            status_code = response.get('statusCode', '200')
            
            # Determine the appropriate response class
            resp_class = resp_types.get(status_code, "Response")
            if resp_class not in self.classes:
                resp_class = "Response"  # Fallback to base class
            
            # Extract the HTTP method from the endpoint_id
            http_method = None
            if endpoint_id in self.endpoints:
                http_method = self.endpoints[endpoint_id]['method'].upper()
                http_method_class = self.http_methods.get(http_method)
            
            # Create the response instance
            instance_uri = f"{self.base_uri}{resp_id}"
            
            instance_def = f"""
        <owl:NamedIndividual rdf:about="{instance_uri}">
            <rdf:type rdf:resource="{self.base_uri}{resp_class}"/>
            <rdfs:label xml:lang="en">Response {status_code} for {endpoint_id}</rdfs:label>
            <dc:description xml:lang="en">{self.sanitize_text(response.get('description', ''))}</dc:description>
            <dc:statusCode xml:lang="en">{status_code}</dc:statusCode>
    """
            
            # Add HTTP method relationship if available
            if http_method and http_method_class:
                instance_def += f'        <api:belongsToHttpMethod rdf:resource="{self.base_uri}{http_method_class}"/>\n'
            
            # Add content type information
            for content_type, schema_id in response.get('content', {}).items():
                instance_def += f'        <dc:mediaType xml:lang="en">{self.sanitize_text(content_type)}</dc:mediaType>\n'
                
                # Add schema reference if available
                if schema_id and schema_id != 'object' and schema_id in self.swagger_data.get('components', {}).get('schemas', {}):
                    instance_def += f'        <api:hasSchema rdf:resource="{self.base_uri}{schema_id}"/>\n'
            
            # Add endpoint relationship
            if endpoint_id and endpoint_id in self.endpoints:
                instance_def += f'        <api:belongsToEndpoint rdf:resource="{self.base_uri}{self.sanitize_for_uri(endpoint_id)}"/>\n'
            
            instance_def += "    </owl:NamedIndividual>\n"
            classes_output += instance_def
            
        return classes_output

    def generate_schema_classes(self):
        """Generate OWL classes from schemas with proper relationships."""
        classes_output = """

    <!-- 
    ///////////////////////////////////////////////////////////////////////////////////////
    //
    // Schema Classes
    //
    ///////////////////////////////////////////////////////////////////////////////////////
    -->
"""
        
        try:
            schemas = self.swagger_data.get('components', {}).get('schemas', {})
            created_classes = set()
            
            # Base URI for the API title
            title_class = self.sanitize_for_uri(self.api_title)
            base_title_uri = f"{self.base_uri}{title_class}"
            
            # Process all schemas
            for schema_name, schema_def in schemas.items():
                if schema_name in created_classes:
                    continue
                
                # Generate full URI for this schema
                schema_uri = f"{self.base_uri}{schema_name}"
                
                # Determine appropriate subclass relationship based on usage
                subclass_uris = []
                
                # Check if this schema is used in request bodies
                if schema_name in self.request_body_schemas:
                    for endpoint_id in self.request_body_schemas[schema_name]:
                        if endpoint_id in self.endpoints:
                            endpoint = self.endpoints[endpoint_id]
                            # Use first tag as parent controller
                            if endpoint.get('tags') and endpoint['tags']:
                                controller_tag = endpoint['tags'][0]
                                controller_uri = f"{self.base_uri}{self.sanitize_for_uri(controller_tag)}"
                                if controller_uri not in subclass_uris:
                                    subclass_uris.append(controller_uri)
                
                # Check if this schema is used in responses
                if schema_name in self.response_schemas:
                    for endpoint_id in self.response_schemas[schema_name]:
                        if endpoint_id in self.endpoints:
                            endpoint = self.endpoints[endpoint_id]
                            # Use first tag as parent controller
                            if endpoint.get('tags') and endpoint['tags']:
                                controller_tag = endpoint['tags'][0]
                                controller_uri = f"{self.base_uri}{self.sanitize_for_uri(controller_tag)}"
                                if controller_uri not in subclass_uris:
                                    subclass_uris.append(controller_uri)
                
                # If no specific usage found, use API title as parent
                if not subclass_uris:
                    subclass_uris.append(base_title_uri)
                
                # Resolve schema if it's a reference
                if '$ref' in schema_def:
                    resolved = self.resolve_ref(schema_def['$ref'])
                    if resolved:
                        schema_def = resolved
                
                # Get or generate a label for the schema
                # If schema has title, use that, otherwise generate from name
                schema_label = schema_def.get('title', schema_name)
                if not schema_label:
                    schema_label = ' '.join(word.capitalize() for word in schema_name.split('_'))
                
                # Build the class definition
                class_def = f"""
    <owl:Class rdf:about="{schema_uri}">
        <rdfs:label xml:lang="en">{self.sanitize_text(schema_label)}</rdfs:label>
        <dc:description xml:lang="en">{self.sanitize_text(schema_def.get('description', ''))}</dc:description>
"""
                
                # Add subclass relationships
                for subclass_uri in subclass_uris:
                    class_def += f'        <rdfs:subClassOf rdf:resource="{subclass_uri}"/>\n'
                
                # Add any schema-level annotations
                if 'deprecated' in schema_def:
                    class_def += f'        <owl:deprecated>{str(schema_def["deprecated"]).lower()}</owl:deprecated>\n'
                
                # Add example if available at schema level
                if 'example' in schema_def:
                    example = schema_def['example']
                    if isinstance(example, (str, int, float, bool)):
                        class_def += f'        <dc:example xml:lang="en">{self.sanitize_text(str(example))}</dc:example>\n'
                
                class_def += "    </owl:Class>\n"
                classes_output += class_def
                created_classes.add(schema_name)
                
                # Process properties for this schema
                properties = {}
                
                # Handle properties directly in schema
                if 'properties' in schema_def:
                    properties.update(schema_def['properties'])
                
                # Handle allOf composition
                if 'allOf' in schema_def:
                    for part in schema_def['allOf']:
                        if '$ref' in part:
                            resolved = self.resolve_ref(part['$ref'])
                            if resolved and 'properties' in resolved:
                                properties.update(resolved['properties'])
                        elif 'properties' in part:
                            properties.update(part['properties'])
                
                # Identify required properties
                required_props = schema_def.get('required', [])
                
                # Generate data type property restrictions for the schema
                for prop_name, prop_def in properties.items():
                    # Skip metadata properties
                    if prop_name in ['@id', '@type', '@context']:
                        continue
                    
                    # Create property restriction for this schema
                    is_required = prop_name in required_props
                    
                    # If it's an object property, create a property restriction class
                    if self._is_object_property(prop_def):
                        range_class = self._extract_range_class(prop_def)
                        
                        if range_class and range_class in schemas:
                            # Create a restriction on this object property
                            restriction_def = f"""
    <owl:Restriction>
        <owl:onProperty rdf:resource="{self.base_uri}{prop_name}"/>
        <owl:someValuesFrom rdf:resource="{self.base_uri}{range_class}"/>
    </owl:Restriction>
"""
                            # Connect this restriction to the schema class
                            # We could add this directly in the class definition above
                            # For this example, we'll just output it as a comment
                            classes_output += f"    <!-- Property restriction: {schema_name}.{prop_name} -> {range_class} -->\n"
                            classes_output += f"    <!-- {restriction_def} -->\n"
            
            return classes_output
        
        except Exception as e:
            print(f"Error in generate_schema_classes: {e}")
            print(traceback.format_exc())
        
        return ""

    def _is_object_property(self, prop_def):
        """Determine if a property is an object property (references another class)."""
        # If it's a direct $ref, it's an object property
        if '$ref' in prop_def:
            return True
        
        # If it's an array of objects, it's an object property
        if prop_def.get('type') == 'array' and 'items' in prop_def:
            items = prop_def['items']
            if '$ref' in items or items.get('type') == 'object':
                return True
        
        # If it has oneOf or anyOf with refs, it's an object property
        if 'oneOf' in prop_def:
            for option in prop_def['oneOf']:
                if '$ref' in option:
                    return True
                    
        if 'anyOf' in prop_def:
            for option in prop_def['anyOf']:
                if '$ref' in option:
                    return True
        
        return False
    
    def _extract_range_class(self, prop_def):
        """Extract the range class from a property definition."""
        # Direct reference
        if '$ref' in prop_def:
            return prop_def['$ref'].split('/')[-1]
        
        # Array of objects
        if prop_def.get('type') == 'array' and 'items' in prop_def:
            items = prop_def['items']
            if '$ref' in items:
                return items['$ref'].split('/')[-1]
        
        # oneOf or anyOf with references
        if 'oneOf' in prop_def:
            for option in prop_def['oneOf']:
                if '$ref' in option:
                    return option['$ref'].split('/')[-1]
                    
        if 'anyOf' in prop_def:
            for option in prop_def['anyOf']:
                if '$ref' in option:
                    return option['$ref'].split('/')[-1]
        
        return None

    def generate_object_properties(self):
        """Generate object properties from schema relationships."""
        properties_output = """

    <!-- 
    ///////////////////////////////////////////////////////////////////////////////////////
    //
    // Object Properties
    //
    ///////////////////////////////////////////////////////////////////////////////////////
     -->
"""
        try:
            # Process schemas to find object properties
            schemas = self.swagger_data.get('components', {}).get('schemas', {})
            
            for schema_name, schema_def in schemas.items():
                # Skip utility schemas
                if (schema_name.endswith('Filter') or schema_name.endswith('Wrapper')):
                    continue
                
                # Resolve schema if it's a reference
                if '$ref' in schema_def:
                    resolved = self.resolve_ref(schema_def['$ref'])
                    if resolved:
                        schema_def = resolved
                
                # Extract properties section, handling allOf composition
                properties = {}
                
                if 'properties' in schema_def:
                    properties.update(schema_def['properties'])
                
                if 'allOf' in schema_def:
                    for part in schema_def['allOf']:
                        if '$ref' in part:
                            resolved = self.resolve_ref(part['$ref'])
                            if resolved and 'properties' in resolved:
                                properties.update(resolved['properties'])
                        elif 'properties' in part:
                            properties.update(part['properties'])
                
                # Identify required properties
                required_props = schema_def.get('required', [])
                
                # Process each property to identify object properties
                for prop_name, prop_def in properties.items():
                    # Skip metadata properties
                    if prop_name in ['@id', '@type', '@context', 'id']:
                        continue
                    
                    # Check if this is an object property
                    if self._is_object_property(prop_def):
                        prop_uri = f"{self.base_uri}{prop_name}"
                        
                        # Skip if we've already processed this property
                        if prop_name in self.object_properties:
                            continue
                        
                        self.object_properties.add(prop_name)
                        
                        # Extract range class
                        range_class = self._extract_range_class(prop_def)
                        
                        # Get the property description
                        description = prop_def.get('description', f"The {prop_name} property of {schema_name}.")
                        
                        # Determine if this is a collection
                        is_collection = False
                        if prop_def.get('type') == 'array':
                            is_collection = True
                        
                        # Create the object property
                        property_def = f"""
    <owl:ObjectProperty rdf:about="{prop_uri}">
        <rdfs:label xml:lang="en">{prop_name}</rdfs:label>
        <rdfs:comment xml:lang="en">{self.sanitize_text(description)}</rdfs:comment>
        <rdfs:domain rdf:resource="{self.base_uri}{schema_name}"/>
"""
                        
                        if range_class:
                            property_def += f'        <rdfs:range rdf:resource="{self.base_uri}{range_class}"/>\n'
                        
                        # Add required flag
                        is_required = prop_name in required_props
                        property_def += f'        <dc:required xml:lang="en">{str(is_required).lower()}</dc:required>\n'
                        
                        # Add collection flag
                        if not is_collection:
                            property_def += f'        <rdf:type rdf:resource="http://www.w3.org/2002/07/owl#FunctionalProperty"/>\n'
                        
                        property_def += "    </owl:ObjectProperty>\n"
                        properties_output += property_def
                        
                        # For collections, also create a has-one inverse relationship
                        if is_collection and range_class:
                            inverse_name = f"belongsTo{schema_name}"
                            if inverse_name not in self.object_properties:
                                self.object_properties.add(inverse_name)
                                inverse_uri = f"{self.base_uri}{inverse_name}"
                                
                                inverse_def = f"""
    <owl:ObjectProperty rdf:about="{inverse_uri}">
        <rdfs:label xml:lang="en">belongs to {schema_name}</rdfs:label>
        <rdfs:comment xml:lang="en">Inverse relationship from {range_class} to {schema_name}</rdfs:comment>
        <rdfs:domain rdf:resource="{self.base_uri}{range_class}"/>
        <rdfs:range rdf:resource="{self.base_uri}{schema_name}"/>
        <owl:inverseOf rdf:resource="{prop_uri}"/>
    </owl:ObjectProperty>
"""
                                properties_output += inverse_def
            
            # Also process paths to create additional object properties based on API structure
            resource_name_pattern = re.compile(r'^/([^/]+)(?:/\{[^}]+\})?$')
            sub_resource_pattern = re.compile(r'^/([^/]+)/\{[^}]+\}/([^/]+)$')
            
            # Map of path resources to their likely classes
            resource_to_class = {}
            
            # First pass: identify resources and their classes
            for path in self.swagger_data.get('paths', {}).keys():
                # Check for base resources
                base_match = resource_name_pattern.match(path)
                if base_match:
                    resource = base_match.group(1)
                    # Convert to camel case if it's kebab-case or snake_case
                    if '-' in resource:
                        parts = resource.split('-')
                        class_name = parts[0].title() + ''.join(p.title() for p in parts[1:])
                    elif '_' in resource:
                        parts = resource.split('_')
                        class_name = ''.join(p.title() for p in parts)
                    else:
                        class_name = resource.title()
                        
                    resource_to_class[resource] = class_name
            
            # Second pass: identify relationships based on nested paths
            for path in self.swagger_data.get('paths', {}).keys():
                sub_match = sub_resource_pattern.match(path)
                if sub_match:
                    parent_resource = sub_match.group(1)
                    child_resource = sub_match.group(2)
                    
                    if parent_resource in resource_to_class and child_resource in resource_to_class:
                        parent_class = resource_to_class[parent_resource]
                        child_class = resource_to_class[child_resource]
                        
                        # Create has/is relationship property names
                        has_prop = f"has{child_class}"
                        is_prop = f"is{child_class}Of{parent_class}"
                        
                        if has_prop not in self.object_properties:
                            self.object_properties.add(has_prop)
                            has_uri = f"{self.base_uri}{has_prop}"
                            
                            properties_output += f"""
    <owl:ObjectProperty rdf:about="{has_uri}">
        <rdfs:label xml:lang="en">{has_prop}</rdfs:label>
        <rdfs:comment xml:lang="en">Relationship from {parent_class} to {child_class}.</rdfs:comment>
        <rdfs:domain rdf:resource="{self.base_uri}{parent_class}"/>
        <rdfs:range rdf:resource="{self.base_uri}{child_class}"/>
    </owl:ObjectProperty>
"""
                        
                        if is_prop not in self.object_properties:
                            self.object_properties.add(is_prop)
                            is_uri = f"{self.base_uri}{is_prop}"
                            
                            properties_output += f"""
    <owl:ObjectProperty rdf:about="{is_uri}">
        <rdfs:label xml:lang="en">{is_prop}</rdfs:label>
        <rdfs:comment xml:lang="en">Inverse relationship from {child_class} to {parent_class}.</rdfs:comment>
        <rdfs:domain rdf:resource="{self.base_uri}{child_class}"/>
        <rdfs:range rdf:resource="{self.base_uri}{parent_class}"/>
    </owl:ObjectProperty>
"""
        except Exception as e:
            print(f"Error in generate_object_properties: {e}")
            print(traceback.format_exc())
        
        return properties_output

    def generate_data_properties(self):
        """Generate data properties from schema definitions."""
        properties_output = """

    <!-- 
    ///////////////////////////////////////////////////////////////////////////////////////
    //
    // Data Properties
    //
    ///////////////////////////////////////////////////////////////////////////////////////
     -->
"""
        try:
            # Process schemas to find data properties
            schemas = self.swagger_data.get('components', {}).get('schemas', {})
            
            for schema_name, schema_def in schemas.items():
                # Resolve schema if it's a reference
                if '$ref' in schema_def:
                    resolved = self.resolve_ref(schema_def['$ref'])
                    if resolved:
                        schema_def = resolved
                
                # Extract properties section, handling allOf composition
                properties = {}
                
                if 'properties' in schema_def:
                    properties.update(schema_def['properties'])
                
                if 'allOf' in schema_def:
                    for part in schema_def['allOf']:
                        if '$ref' in part:
                            resolved = self.resolve_ref(part['$ref'])
                            if resolved and 'properties' in resolved:
                                properties.update(resolved['properties'])
                        elif 'properties' in part:
                            properties.update(part['properties'])
                
                # Identify required properties
                required_props = schema_def.get('required', [])
                
                # Process each property to identify data properties
                for prop_name, prop_def in properties.items():
                    # Skip metadata properties and object properties
                    if prop_name in ['@id', '@type', '@context', 'id'] or self._is_object_property(prop_def):
                        continue
                    
                    prop_uri = f"{self.base_uri}{prop_name}"
                    
                    # Skip if we've already processed this property
                    if prop_name in self.data_properties:
                        continue
                    
                    self.data_properties.add(prop_name)
                    
                    # Get the property description
                    description = prop_def.get('description', f"The {prop_name} property of {schema_name}.")
                    
                    # Check if property is required
                    is_required = prop_name in required_props
                    
                    # Create the data property
                    property_def = f"""
    <owl:DatatypeProperty rdf:about="{prop_uri}">
        <rdfs:label xml:lang="en">{prop_name}</rdfs:label>
        <rdfs:comment xml:lang="en">{self.sanitize_text(description)}</rdfs:comment>
        <rdfs:domain rdf:resource="{self.base_uri}{schema_name}"/>
"""
                    
                    # Add range based on type
                    range_type = self._get_xsd_type(prop_def)
                    if range_type:
                        property_def += f'        <rdfs:range rdf:resource="http://www.w3.org/2001/XMLSchema#{range_type}"/>\n'
                    
                    # Add required flag
                    property_def += f'        <dc:required xml:lang="en">{str(is_required).lower()}</dc:required>\n'
                    
                    # Add format if available
                    if 'format' in prop_def:
                        property_def += f'        <dc:format xml:lang="en">{self.sanitize_text(prop_def["format"])}</dc:format>\n'
                    
                    # Add pattern if available
                    if 'pattern' in prop_def:
                        property_def += f'        <dc:pattern xml:lang="en">{self.sanitize_text(prop_def["pattern"])}</dc:pattern>\n'
                    
                    # Add example if available
                    if 'example' in prop_def:
                        example = prop_def['example']
                        if isinstance(example, (str, int, float, bool)):
                            property_def += f'        <dc:example xml:lang="en">{self.sanitize_text(str(example))}</dc:example>\n'
                    
                    # Add enum values if available
                    if 'enum' in prop_def:
                        enum_values = prop_def['enum']
                        for enum_value in enum_values:
                            if isinstance(enum_value, (str, int, float, bool)):
                                property_def += f'        <rdfs:comment xml:lang="en">Allowed value: {self.sanitize_text(str(enum_value))}</rdfs:comment>\n'
                    
                    # Add min/max constraints
                    if 'minimum' in prop_def:
                        property_def += f'        <rdfs:comment xml:lang="en">Minimum value: {prop_def["minimum"]}</rdfs:comment>\n'
                    if 'maximum' in prop_def:
                        property_def += f'        <rdfs:comment xml:lang="en">Maximum value: {prop_def["maximum"]}</rdfs:comment>\n'
                    if 'minLength' in prop_def:
                        property_def += f'        <rdfs:comment xml:lang="en">Minimum length: {prop_def["minLength"]}</rdfs:comment>\n'
                    if 'maxLength' in prop_def:
                        property_def += f'        <rdfs:comment xml:lang="en">Maximum length: {prop_def["maxLength"]}</rdfs:comment>\n'
                    
                    property_def += "    </owl:DatatypeProperty>\n"
                    properties_output += property_def
            
        except Exception as e:
            print(f"Error in generate_data_properties: {e}")
            print(traceback.format_exc())
            
        return properties_output
    
    def _get_xsd_type(self, prop_def):
        """Map Swagger types to XSD types."""
        type_map = {
            'string': 'string',
            'integer': 'integer',
            'number': 'decimal',
            'boolean': 'boolean',
        }
        
        # Check for format-specific mappings
        format_map = {
            'date': 'date',
            'date-time': 'dateTime',
            'uri': 'anyURI',
            'email': 'string',
            'uuid': 'string',
            'int32': 'integer',
            'int64': 'integer',
            'float': 'decimal',
            'double': 'decimal'
        }
        
        # Direct type mapping
        prop_type = prop_def.get('type')
        
        # Handle format-specific mappings
        prop_format = prop_def.get('format')
        
        if prop_format and prop_format in format_map:
            return format_map[prop_format]
        elif prop_type and prop_type in type_map:
            return type_map[prop_type]
        
        # Default to string
        return 'string'
    
    def generate_individuals(self):
        """Generate individuals from schema examples and enums."""
        individuals_output = """

    <!-- 
    ///////////////////////////////////////////////////////////////////////////////////////
    //
    // Individuals
    //
    ///////////////////////////////////////////////////////////////////////////////////////
     -->
"""
        try:
            # Process schemas to find individuals from enums and examples
            schemas = self.swagger_data.get('components', {}).get('schemas', {})
            
            for schema_name, schema_def in schemas.items():
                # Check if this schema defines an enum
                if 'enum' in schema_def:
                    enum_values = schema_def['enum']
                    for value in enum_values:
                        # Create an individual for each enum value
                        indiv_name = f"{schema_name}_{self.sanitize_for_uri(str(value))}"
                        
                        # Skip if already processed
                        if indiv_name in self.individuals:
                            continue
                            
                        self.individuals.add(indiv_name)
                        indiv_uri = f"{self.base_uri}{indiv_name}"
                        
                        individuals_output += f"""
    <owl:NamedIndividual rdf:about="{indiv_uri}">
        <rdf:type rdf:resource="{self.base_uri}{schema_name}"/>
        <rdfs:label xml:lang="en">{self.sanitize_text(str(value))}</rdfs:label>
    </owl:NamedIndividual>
"""
                
                # Check if this schema has an example
                if 'example' in schema_def:
                    example = schema_def['example']
                    if isinstance(example, dict):
                        # Create an individual from the example
                        indiv_name = f"{schema_name}_Example"
                        
                        # Skip if already processed
                        if indiv_name in self.individuals:
                            continue
                            
                        self.individuals.add(indiv_name)
                        indiv_uri = f"{self.base_uri}{indiv_name}"
                        
                        individual_def = f"""
    <owl:NamedIndividual rdf:about="{indiv_uri}">
        <rdf:type rdf:resource="{self.base_uri}{schema_name}"/>
        <rdfs:label xml:lang="en">{schema_name} Example</rdfs:label>
"""
                        
                        # Add properties from the example
                        for prop_name, prop_value in example.items():
                            if isinstance(prop_value, (str, int, float, bool)):
                                # For simple values, add as a data property
                                individual_def += f'        <api:{prop_name}>{self.sanitize_text(str(prop_value))}</api:{prop_name}>\n'
                        
                        individual_def += "    </owl:NamedIndividual>\n"
                        individuals_output += individual_def
                        
            # Process security schemes to create individuals
            security_schemes = self.swagger_data.get('components', {}).get('securitySchemes', {})
            
            if security_schemes:
                individuals_output += """
    <!-- 
    ///////////////////////////////////////////////////////////////////////////////////////
    //
    // Security Scheme Individuals
    //
    ///////////////////////////////////////////////////////////////////////////////////////
     -->
"""
                
                # Create a security scheme class first if not already defined
                security_class_uri = f"{self.base_uri}SecurityScheme"
                security_class_name = "SecurityScheme"
                
                if security_class_name not in self.classes:
                    self.classes.add(security_class_name)
                    
                    security_class_def = f"""
    <owl:Class rdf:about="{security_class_uri}">
        <rdfs:label xml:lang="en">Security Scheme</rdfs:label>
        <rdfs:comment xml:lang="en">Base class for API security schemes</rdfs:comment>
    </owl:Class>
"""
                    individuals_output += security_class_def
                
                # Create subclasses for different security scheme types
                scheme_types = {
                    "apiKey": "ApiKeySecurityScheme",
                    "http": "HttpSecurityScheme",
                    "oauth2": "OAuth2SecurityScheme",
                    "openIdConnect": "OpenIdConnectSecurityScheme"
                }
                
                for scheme_type, class_name in scheme_types.items():
                    if class_name not in self.classes:
                        self.classes.add(class_name)
                        scheme_class_uri = f"{self.base_uri}{class_name}"
                        
                        scheme_class_def = f"""
    <owl:Class rdf:about="{scheme_class_uri}">
        <rdfs:label xml:lang="en">{class_name}</rdfs:label>
        <rdfs:comment xml:lang="en">{scheme_type} security scheme</rdfs:comment>
        <rdfs:subClassOf rdf:resource="{security_class_uri}"/>
    </owl:Class>
"""
                        individuals_output += scheme_class_def
                
                # Create individuals for each security scheme
                for scheme_name, scheme_def in security_schemes.items():
                    # Determine the appropriate security scheme class
                    scheme_type = scheme_def.get('type', 'apiKey')
                    scheme_class = scheme_types.get(scheme_type, "SecurityScheme")
                    
                    # Create the security scheme instance
                    indiv_name = f"SecurityScheme_{self.sanitize_for_uri(scheme_name)}"
                    
                    # Skip if already processed
                    if indiv_name in self.individuals:
                        continue
                        
                    self.individuals.add(indiv_name)
                    indiv_uri = f"{self.base_uri}{indiv_name}"
                    
                    individual_def = f"""
    <owl:NamedIndividual rdf:about="{indiv_uri}">
        <rdf:type rdf:resource="{self.base_uri}{scheme_class}"/>
        <rdfs:label xml:lang="en">{self.sanitize_text(scheme_name)}</rdfs:label>
"""
                    
                    # Add scheme properties based on type
                    if scheme_type == 'apiKey':
                        individual_def += f'        <dc:description xml:lang="en">API Key in {scheme_def.get("in", "header")}</dc:description>\n'
                        individual_def += f'        <rdfs:comment xml:lang="en">Parameter name: {scheme_def.get("name", "")}</rdfs:comment>\n'
                        
                    elif scheme_type == 'http':
                        individual_def += f'        <dc:description xml:lang="en">HTTP {scheme_def.get("scheme", "bearer")} authentication</dc:description>\n'
                        if 'bearerFormat' in scheme_def:
                            individual_def += f'        <rdfs:comment xml:lang="en">Bearer format: {scheme_def["bearerFormat"]}</rdfs:comment>\n'
                    
                    elif scheme_type == 'oauth2':
                        individual_def += f'        <dc:description xml:lang="en">OAuth2 authentication</dc:description>\n'
                        # Add flow information if available
                        for flow_type, flow_def in scheme_def.get('flows', {}).items():
                            individual_def += f'        <rdfs:comment xml:lang="en">Flow type: {flow_type}</rdfs:comment>\n'
                    
                    elif scheme_type == 'openIdConnect':
                        individual_def += f'        <dc:description xml:lang="en">OpenID Connect authentication</dc:description>\n'
                        individual_def += f'        <rdfs:seeAlso rdf:resource="{self.sanitize_text(scheme_def.get("openIdConnectUrl", ""))}"/>\n'
                    
                    individual_def += "    </owl:NamedIndividual>\n"
                    individuals_output += individual_def
                    
                # Create object property for security requirements
                has_security_prop = "hasSecurityRequirement"
                if has_security_prop not in self.object_properties:
                    self.object_properties.add(has_security_prop)
                    prop_uri = f"{self.base_uri}{has_security_prop}"
                    
                    prop_def = f"""
    <owl:ObjectProperty rdf:about="{prop_uri}">
        <rdfs:label xml:lang="en">has security requirement</rdfs:label>
        <rdfs:comment xml:lang="en">Relates an API or endpoint to a security scheme</rdfs:comment>
        <rdfs:domain rdf:resource="http://www.w3.org/2002/07/owl#API"/>
        <rdfs:range rdf:resource="{security_class_uri}"/>
    </owl:ObjectProperty>
"""
                    individuals_output += prop_def
                    
            # Process global API security requirements
            if 'security' in self.swagger_data:
                # Create a special API Security class
                api_security_class_uri = f"{self.base_uri}ApiSecurity"
                api_security_class_name = "ApiSecurity"
                
                if api_security_class_name not in self.classes:
                    self.classes.add(api_security_class_name)
                    
                    security_class_def = f"""
    <owl:Class rdf:about="{api_security_class_uri}">
        <rdfs:label xml:lang="en">API Security</rdfs:label>
        <rdfs:comment xml:lang="en">Security requirements for the API</rdfs:comment>
        <rdfs:subClassOf rdf:resource="{self.base_uri}{self.sanitize_for_uri(self.api_title)}"/>
    </owl:Class>
"""
                    individuals_output += security_class_def
                
                # Create individual for the API security
                api_security_uri = f"{self.base_uri}ApiSecurityRequirements"
                api_security_name = "ApiSecurityRequirements"
                
                if api_security_name not in self.individuals:
                    self.individuals.add(api_security_name)
                    
                    security_def = f"""
    <owl:NamedIndividual rdf:about="{api_security_uri}">
        <rdf:type rdf:resource="{api_security_class_uri}"/>
        <rdfs:label xml:lang="en">API Security Requirements</rdfs:label>
"""
                    
                    # Add references to security schemes
                    for sec_req in self.swagger_data['security']:
                        for scheme_name in sec_req.keys():
                            scheme_uri = f"{self.base_uri}SecurityScheme_{self.sanitize_for_uri(scheme_name)}"
                            security_def += f'        <api:hasSecurityRequirement rdf:resource="{scheme_uri}"/>\n'
                    
                    security_def += "    </owl:NamedIndividual>\n"
                    individuals_output += security_def
                    
        except Exception as e:
            print(f"Error in generate_individuals: {e}")
            print(traceback.format_exc())
        
        return individuals_output


def main():
    """Main function to handle command-line usage."""
    parser = argparse.ArgumentParser(description='Convert Swagger/OpenAPI JSON to RDF/XML ontology with comprehensive relationship modeling.')
    parser.add_argument('input_file', help='Input Swagger/OpenAPI JSON file')
    parser.add_argument('output_file', help='Output RDF/XML file')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose output')
    args = parser.parse_args()
    
    # Check if input file exists
    if not os.path.isfile(args.input_file):
        print(f"Error: Input file '{args.input_file}' not found.")
        sys.exit(1)
    
    try:
        # Load Swagger JSON
        with open(args.input_file, 'r', encoding='utf-8') as f:
            swagger_data = json.load(f)
        
        # Convert to RDF
        converter = EnhancedSwaggerToRDFConverter(swagger_data)
        rdf_xml = converter.convert_to_rdf()
        
        # Write output file
        with open(args.output_file, 'w', encoding='utf-8') as f:
            f.write(rdf_xml)
        
        print(f"Successfully converted {args.input_file} to {args.output_file}")
        print(f"Generated {len(converter.classes)} classes, {len(converter.object_properties)} object properties, "
              f"{len(converter.data_properties)} data properties, and {len(converter.individuals)} individuals.")
        
        # Verbose statistics
        if args.verbose:
            print("\nDetailed Statistics:")
            print(f"- Controllers: {len(converter.controllers)}")
            print(f"- Endpoints: {len(converter.endpoints)}")
            print(f"- Parameters: {len(converter.parameters)}")
            print(f"- Request Bodies: {len(converter.request_bodies)}")
            print(f"- Responses: {len(converter.responses)}")
            print(f"- Request Body Schemas: {len(converter.request_body_schemas)}")
            print(f"- Response Schemas: {len(converter.response_schemas)}")
            
            # Print all classes
            print("\nGenerated Classes:")
            for class_name in sorted(converter.classes):
                print(f"- {class_name}")
            
            # Print all object properties
            print("\nGenerated Object Properties:")
            for prop_name in sorted(converter.object_properties):
                print(f"- {prop_name}")
        
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON from '{args.input_file}': {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error during conversion: {e}")
        print(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()