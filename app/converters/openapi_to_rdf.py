import json
from rdflib import Graph, Namespace, RDF, RDFS, OWL, XSD, URIRef, Literal

class SwaggerToRDFConverter:
    def __init__(self, swagger_data):
        self.data = swagger_data
        # Base URI for ontology (edit as needed)
        self.BASE = Namespace("http://example.com/api-ontology#")
        self.g = Graph()
        self.g.bind("api", self.BASE)
        self.g.bind("rdf", RDF)
        self.g.bind("rdfs", RDFS)
        self.g.bind("owl", OWL)
        self.g.bind("xsd", XSD)
        
    def convert(self):
        # Example: add API metadata as an OWL class
        info = self.data.get('info', {})
        api_class = URIRef(self.BASE["Api"])
        self.g.add((api_class, RDF.type, OWL.Class))
        if 'title' in info:
            self.g.add((api_class, RDFS.label, Literal(info['title'])))
        if 'description' in info:
            self.g.add((api_class, RDFS.comment, Literal(info['description'])))
        
        # Parse paths -> endpoints, methods, parameters, etc.
        for path, operations in self.data.get('paths', {}).items():
            path_uri = URIRef(self.BASE[self._sanitize_path(path)])
            self.g.add((path_uri, RDF.type, OWL.Class))
            self.g.add((path_uri, RDFS.label, Literal(path)))
            self.g.add((path_uri, RDFS.subClassOf, api_class))
            
            for method, op in operations.items():
                op_uri = URIRef(self.BASE[f"{method.upper()}_{self._sanitize_path(path)}"])
                self.g.add((op_uri, RDF.type, OWL.Class))
                self.g.add((op_uri, RDFS.label, Literal(f"{method.upper()} {path}")))
                self.g.add((op_uri, RDFS.subClassOf, path_uri))
                if 'summary' in op:
                    self.g.add((op_uri, RDFS.comment, Literal(op['summary'])))
        
        # Schema definitions (components/schemas)
        for sname, sdef in self.data.get('components', {}).get('schemas', {}).items():
            schema_uri = URIRef(self.BASE[sname])
            self.g.add((schema_uri, RDF.type, OWL.Class))
            self.g.add((schema_uri, RDFS.label, Literal(sname)))
            # You might process properties here and create properties/types

        # ...add additional RDF mapping logic here for parameters, responses, etc.

    def serialize(self, format="xml"):
        return self.g.serialize(format=format)

    def _sanitize_path(self, path):
        # Simple sanitizer for URI (replace slashes/braces)
        return path.strip('/').replace('/', '_').replace('{', '').replace('}', '')

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python swagger_to_rdf.py <input_swagger.json> <output_rdf.xml>")
        sys.exit(1)
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        swagger = json.load(f)
    converter = SwaggerToRDFConverter(swagger)
    converter.convert()
    output = converter.serialize()
    with open(sys.argv[2], "wb") as out:
        out.write(output)
