import requests
from datetime import datetime, timedelta
from typing import Iterator, Any, Union
import time

from pyspark.sql.types import (
    StructType,
    StructField,
    StringType,
    LongType,
    TimestampType,
    ArrayType,
    BooleanType,
    DoubleType,
    DateType,
    MapType,
)

# This is the class each source connector needs to implement.
# !! DO NOT CHANGE THE CLASS NAME OR CREATE AN SUBCLASS OF THIS CLASS !! Please directly implement the methods below.
class LakeflowConnect:
    def __init__(self, options: dict[str, str]) -> None:
        """
        Initialize the source connector with parameters needed to connect to the source.
        Args:
            options: A dictionary of parameters like authentication tokens, table names, and other configurations.
                     Expected options:
                     - access_token: OAuth Access Token
                     - access_token_expires_at: ISO formatted string of when the access token expires (e.g., "YYYY-MM-DDTHH:MM:SS.ffffffZ")
                     - organization_id: Zoho Books Organization ID
                     - region: Zoho Books API region (e.g., 'com', 'eu', 'in')
        """
        self.access_token = options.get("access_token")
        self.access_token_expires_at_str = options.get("access_token_expires_at")
        self.organization_id = options.get("organization_id")
        self.region = options.get("region", "com") # Default to .com if not specified

        if not all([self.access_token, self.access_token_expires_at_str, self.organization_id]):
            raise ValueError("Missing required authentication or organization parameters.")

        try:
            # Parse the expiry time string into a datetime object
            self.access_token_expires_at = datetime.fromisoformat(self.access_token_expires_at_str.replace('Z', '+00:00'))
        except ValueError:
            raise ValueError(f"Invalid access_token_expires_at format: {self.access_token_expires_at_str}. Expected ISO format.")

        self.base_api_uri = f"https://www.zohoapis.{self.region}/books/v3"

        # Supported tables from zoho_books_api_doc.md
        self.supported_tables = [
            "Organizations", "Contacts", "Contact Persons", "Estimates", "Sales Orders",
            "Sales Receipts", "Invoices", "Recurring Invoices", "Credit Notes",
            "Customer Debit Notes", "Customer Payments", "Expenses", "Recurring Expenses",
            "Bills", "Vendor Credits", "Purchase Orders", "Recurring Bills", "Vendors",
            "Chart of Accounts", "Bank Accounts", "Bank Rules", "Transaction Categories",
            "Currencies", "Taxes", "Items", "Locations", "Opening Balance", "Users",
            "Zoho CRM Integration" # Note: This is an integration, likely not a direct table for data pull
        ]

    def _get_valid_access_token(self) -> str:
        """
        Returns a valid access token. This method assumes the provided access_token is always valid and
        refreshed externally before being passed to the connector.
        """
        if datetime.now() >= self.access_token_expires_at:
            raise ValueError("Access token has expired. It must be refreshed externally.")
        return self.access_token

    def _make_api_call(
        self, endpoint: str, params: dict = None, method: str = "GET"
    ) -> dict:
        """
        Makes an authenticated API call to Zoho Books.
        Args:
            endpoint: The API endpoint relative to the base URI (e.g., "/contacts").
            params: Optional dictionary of query parameters.
            method: HTTP method (GET, POST, PUT).
        Returns:
            The JSON response from the API.
        """
        access_token = self._get_valid_access_token()
        headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
        url = f"{self.base_api_uri}{endpoint}"

        if params is None:
            params = {}
        params["organization_id"] = self.organization_id

        if method == "GET":
            response = requests.get(url, headers=headers, params=params)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=params) # Assuming JSON body for POST/PUT
        elif method == "PUT":
            response = requests.put(url, headers=headers, json=params)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        response.raise_for_status() # Raise an exception for HTTP errors
        return response.json()

    def list_tables(self) -> list[str]:
        """
        List names of all the tables supported by the source connector.
        Returns:
            A list of table names.
        """
        return self.supported_tables

    def _infer_spark_type(self, value: Any) -> StructType | ArrayType | StringType | LongType | DoubleType | BooleanType | TimestampType | DateType:
        """
        Infers the Spark SQL type for a given Python value.
        Prefers LongType over IntegerType.
        """
        if isinstance(value, str):
            # Try to parse as datetime for TimestampType or DateType
            try:
                datetime.fromisoformat(value.replace('Z', '+00:00')) # Handles 'Z' for UTC
                return TimestampType()
            except ValueError:
                pass
            try:
                datetime.strptime(value, "%Y-%m-%d")
                return DateType()
            except ValueError:
                pass
            return StringType()
        elif isinstance(value, bool):
            return BooleanType()
        elif isinstance(value, int):
            return LongType() # Prefer LongType over IntegerType
        elif isinstance(value, float):
            return DoubleType()
        elif isinstance(value, list):
            if not value:
                return ArrayType(StringType()) # Default to StringType for empty lists
            # Infer type from the first element
            first_element_type = self._infer_spark_type(value[0])
            # If it's a StructField (which it shouldn't be, _infer_spark_type returns dataType directly now)
            # or a StructType, extract its dataType or use directly
            if isinstance(first_element_type, StructType):
                return ArrayType(first_element_type)
            return ArrayType(first_element_type)
        elif isinstance(value, dict):
            # Recursively build schema for nested dictionaries
            return self._build_struct_type_from_json(value)
        elif value is None:
            return StringType() # Default to StringType for None, schema inference is tricky with None
        else:
            return StringType() # Catch-all for unknown types

    def _build_struct_type_from_json(self, json_data: dict) -> StructType:
        """
        Builds a StructType schema from a dictionary of JSON data.
        Avoids flattening nested fields.
        """
        fields = []
        for key, value in json_data.items():
            field_type = self._infer_spark_type(value)
            fields.append(StructField(key, field_type, True))
        return StructType(fields)


    def get_table_schema(
        self, table_name: str, table_options: dict[str, str]
    ) -> StructType:
        """
        Fetch the schema of a table.
        Args:
            table_name: The name of the table to fetch the schema for.
            table_options: A dictionary of options for accessing the table.
        Returns:
            A StructType object representing the schema of the table.
        """
        if table_name not in self.supported_tables:
            raise ValueError(f"Table '{table_name}' is not supported.")

        # Special handling for "Organizations" as it's a top-level endpoint
        if table_name == "Organizations":
            endpoint = "/organizations"
        else:
            # Most tables follow a pluralized endpoint name
            endpoint = f"/{table_name.lower().replace(' ', '')}s" # Basic pluralization

        # Attempt to fetch a single record or a list to infer schema
        try:
            response_data = self._make_api_call(endpoint, params={"per_page": 1})
            if table_name == "Organizations":
                records = response_data.get("organizations", [])
            else:
                # Assuming the key for the list of records is the lowercase plural of the table name
                key = table_name.lower().replace(' ', '') + "s"
                records = response_data.get(key, [])

            if records:
                # Use the first record to infer the schema
                return self._build_struct_type_from_json(records[0])
            else:
                # If no records, try to fetch a single object if a 'get' endpoint exists and infer from there
                # This is a simplification; a more robust solution would know the singular endpoint for each object
                # For now, return an empty StructType if no data to infer from
                return StructType([])
        except Exception as e:
            # Handle API errors or no data found
            print(f"Error fetching data for schema inference for table {table_name}: {e}")
            return StructType([]) # Return empty schema on error or no data

    def read_table_metadata(
        self, table_name: str, table_options: dict[str, str]
    ) -> dict:
        """
        Fetch the metadata of a table.
        Args:
            table_name: The name of the table to fetch the metadata for.
            table_options: A dictionary of options for accessing the table.
        Returns:
            A dictionary containing the metadata of the table.
        """
        if table_name not in self.supported_tables:
            raise ValueError(f"Table '{table_name}' is not supported.")

        primary_keys = []
        cursor_field = None
        ingestion_type = "snapshot" # Default ingestion type

        # Primary Keys (from zoho_books_api_doc.md)
        if table_name == "Organizations":
            primary_keys = ["organization_id"]
        elif table_name == "Contacts":
            primary_keys = ["contact_id"]
        elif table_name == "Invoices":
            primary_keys = ["invoice_id"]
        elif table_name == "Estimates":
            primary_keys = ["estimate_id"]
        elif table_name == "Sales Orders":
            primary_keys = ["salesorder_id"]
        elif table_name == "Users":
            primary_keys = ["user_id"]
        # Add more primary keys for other tables as needed based on API docs

        # Ingestion Types and Cursor Fields (from zoho_books_api_doc.md, Fivetran, Airbyte)
        cdc_tables = [
            "BILL", "CHART_OF_ACCOUNT", "CREDIT_NOTE_REFUND", "CURRENCY", "ESTIMATE",
            "EXPENSE", "ITEM", "JOURNAL_LIST", "PROJECT", "PURCHASE_ORDER",
            "SALES_ORDER", "TAX", "TIME_ENTRY", # Fivetran lists these for deletes, implying CDC
        ]
        append_tables = [
            "Contacts", "Credit Notes", "Customer Payments", "Invoices" # Fivetran lists these for incremental new records
        ]

        # Normalize table names for comparison with the doc's lists which are capitalized
        normalized_table_name = table_name.replace(' ', '_').upper()

        if normalized_table_name in [t.replace(' ', '_').upper() for t in cdc_tables]:
            ingestion_type = "cdc"
            # Common cursor fields for CDC
            cursor_field = "last_modified_time" # Assuming common pattern
            if not primary_keys: # If primary_keys were not set above, it means no explicit PK in docs
                raise ValueError(f"Primary keys are required for CDC table '{table_name}'.")
        elif normalized_table_name in [t.replace(' ', '_').upper() for t in append_tables]:
            ingestion_type = "append"
            # Common cursor fields for append
            cursor_field = "created_time" # Assuming common pattern
            if not primary_keys: # If primary_keys were not set above, it means no explicit PK in docs
                raise ValueError(f"Primary keys are required for append table '{table_name}'.")
        elif table_name == "Users":
            ingestion_type = "snapshot" # Airbyte specifies full sync only
            # primary_keys already set above
        # TBD: For other tables not explicitly categorized, it defaults to snapshot.
        # If primary keys are crucial for snapshot tables, they should be defined.

        return {
            "primary_keys": primary_keys,
            "cursor_field": cursor_field,
            "ingestion_type": ingestion_type,
        }

    def read_table(
        self, table_name: str, start_offset: dict, table_options: dict[str, str]
    ) -> (Iterator[dict], dict):
        """
        Read the records of a table and return an iterator of records and an offset.
        The read starts from the provided start_offset.
        Records returned in the iterator will be one batch of records marked by the offset as its end_offset.
        The read_table function could be called multiple times to read the entire table in multiple batches and
        it stops when the same offset is returned again.
        If the table cannot be incrementally read, the offset can be None if we want to read the entire table in one batch.
        We could still return some fake offsets (cannot checkpointing) to split the table into multiple batches.
        Args:
            table_name: The name of the table to read.
            start_offset: The offset to start reading from.
            table_options: A dictionary of options for accessing the table.
        Returns:
            An iterator of records in JSON format and an offset.
        """
        if table_name not in self.supported_tables:
            raise ValueError(f"Table '{table_name}' is not supported.")

        metadata = self.read_table_metadata(table_name, table_options)
        ingestion_type = metadata.get("ingestion_type")
        cursor_field = metadata.get("cursor_field")

        current_page = int(start_offset.get("page", 1)) if start_offset else 1
        records_per_page = 200 # A reasonable default, Zoho API might have its own default or max.

        params = {"per_page": records_per_page, "page": current_page}

        if ingestion_type in ["cdc", "append"] and cursor_field and start_offset and start_offset.get(cursor_field):
            # For incremental reads, filter by cursor_field if available in start_offset
            # Zoho Books API doesn't seem to have a generic `created_time_gte` or `last_modified_time_gte`
            # for all objects in the v3 docs. This is a potential limitation.
            # For now, we'll assume pagination is the primary mechanism and this will handle "new records".
            # True incremental (e.g., CDC based on timestamps) would require more specific API features.
            pass # Placeholder, as direct timestamp filtering might not be universally supported for incremental in Zoho Books API v3 without explicit API calls per object

        # Special handling for "Organizations"
        if table_name == "Organizations":
            endpoint = "/organizations"
            response_key = "organizations"
        else:
            endpoint = f"/{table_name.lower().replace(' ', '')}s"
            response_key = table_name.lower().replace(' ', '') + "s"

        try:
            response_data = self._make_api_call(endpoint, params=params)
            records = response_data.get(response_key, [])
            page_context = response_data.get("page_context", {})
            has_more_pages = page_context.get("has_more_page", False)

            if records:
                next_offset = {"page": current_page + 1} if has_more_pages else None
                return iter(records), next_offset
            else:
                return iter([]), None # No more records
        except Exception as e:
            print(f"Error reading table {table_name}: {e}")
            return iter([]), None # Return empty iterator on error
