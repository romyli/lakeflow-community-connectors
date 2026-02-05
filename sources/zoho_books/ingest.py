import json
import os
from pipeline.ingestion_pipeline import ingest
from libs.source_loader import get_register_function

# =============================================================================
# SOURCE CONFIGURATION
# =============================================================================
source_name = "zoho_books"
connection_name = "zoho_books_trial"

# List tables to ingest; set to None to load all from dev_table_config.json
TABLES = [
    "Contacts",
    "Invoices",
    "Organizations"
]

# Path to table configuration JSON
table_config_path = "sources/zoho_books/configs/dev_table_config.json"

# Load table configuration if the JSON exists
if os.path.exists(table_config_path):
    with open(table_config_path) as f:
        table_config = json.load(f)
else:
    table_config = {}
    print(f"Warning: Table config JSON not found at {table_config_path}, using defaults")

# =============================================================================
# HELPER FUNCTION
# =============================================================================
def build_table_spec(table_name: str) -> dict:
    """Build a table spec for the ingestion pipeline."""
    table_spec = {"source_table": table_name}

    # Apply table-specific config if available
    if table_name in table_config:
        options = table_config[table_name]
        config = {}
        if "primary_keys" in options:
            print("yes")
            config["primary_keys"] = options["primary_keys"]
        if "scd_type" in options:
            config["scd_type"] = options["scd_type"]
        if config:
            table_spec["table_configuration"] = config

    return {"table": table_spec}

# =============================================================================
# BUILD PIPELINE SPEC
# =============================================================================
if TABLES is None:
    # Ingest all tables from the config
    objects = [build_table_spec(name) for name in table_config.keys()]
    print(f"Loaded all {len(objects)} tables from dev_table_config.json")
else:
    # Ingest only specified tables
    objects = [build_table_spec(name) for name in TABLES]
    print(f"Configured {len(objects)} tables: {TABLES}")

pipeline_spec = {
    "connection_name": connection_name,
    "objects": objects,
}

# =============================================================================
# REGISTER AND INGEST
# =============================================================================
# Dynamically register Zoho Books as a LakeFlow source
register_lakeflow_source = get_register_function(source_name)
register_lakeflow_source(spark)

# Run the ingestion pipeline
ingest(spark, pipeline_spec)
