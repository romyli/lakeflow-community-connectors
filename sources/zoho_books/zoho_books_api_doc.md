# **Zoho Books API Documentation**

**Note on API Version**: The initial request mentioned Zoho Books API v4 OAuth. However, the most comprehensive API documentation found and used for populating the general API details (objects, schemas, read/write operations) is for Zoho Books API v3. Specific OAuth details provided initially for v4 are integrated where applicable, as the OAuth flow is largely consistent across versions.

## **Authorization**
Zoho Books API uses OAuth 2.0 for authentication. The connector will store `client_id`, `client_secret`, and `refresh_token`, and use the refresh token to obtain a new `access_token` at runtime. The connector does not run user-facing OAuth flows.

### OAuth Flow Steps:
1.  **Register Your Application**:
    *   Access the [Zoho API Console](https://api-console.zoho.com/) and create a new client of type "Server-based Applications".
    *   Provide a Client Name, Homepage URL, and Authorized Redirect URIs.
    *   Obtain your `Client ID` and `Client Secret`.

2.  **Generate the Authorization Code**:
    *   Direct users to the authorization URL:
        ```
        https://accounts.zoho.com/oauth/v2/auth?response_type=code&client_id=YOUR_CLIENT_ID&redirect_uri=YOUR_REDIRECT_URI&scope=ZohoBooks.fullaccess.all&access_type=offline&prompt=consent
        ```
    *   Parameters:
        *   `response_type=code`: Requests an authorization code.
        *   `client_id`: Your application's Client ID.
        *   `redirect_uri`: The URL where users will be redirected after authorization.
        *   `scope=ZohoBooks.fullaccess.all`: Defines the level of access requested.
        *   `access_type=offline`: Requests a refresh token.
        *   `prompt=consent`: Ensures the consent screen is displayed.
    *   Upon user approval, Zoho redirects to `redirect_uri` with an authorization `code`.

3.  **Exchange Authorization Code for Access and Refresh Tokens**:
    *   Send a POST request to Zoho's token endpoint:
        `https://accounts.zoho.com/oauth/v2/token`
    *   Headers:
        *   `Content-Type: application/x-www-form-urlencoded`
    *   Body Parameters:
        *   `code`: The authorization code.
        *   `client_id`: Your application's Client ID.
        *   `client_secret`: Your application's Client Secret.
        *   `redirect_uri`: The same redirect URI used in the authorization request.
        *   `grant_type=authorization_code`.
    *   Response will contain `access_token`, `refresh_token`, and `expires_in`.

4.  **Make API Requests**:
    *   Include the `access_token` in the Authorization header for each API request:
        `Authorization: Zoho-oauthtoken ACCESS_TOKEN`
    *   Example for Zoho Books API v3:
        ```
        GET https://www.zohoapis.com/books/v3/invoices?organization_id=YOUR_ORGANIZATION_ID
        Headers:
          Authorization: Zoho-oauthtoken ACCESS_TOKEN
        ```
    *   **Organization ID**: All API requests require the `organization_id` as a query parameter. This can be obtained from the `GET /organizations` API endpoint.
    *   **Multiple Data Centers**: Zoho Books is hosted in multiple data centers. The API endpoint domain must match the organization's data center (e.g., `.com`, `.eu`, `.in`, `.com.au`, `.jp`, `.ca`, `.com.cn`, `.sa`). The base API URI is `https://www.zohoapis.<domain>/books/v3/`.

5.  **Refreshing the Access Token**:
    *   When the `access_token` expires, use the `refresh_token` to get a new one.
    *   Send a POST request to Zoho's token endpoint:
        `https://accounts.zoho.com/oauth/v2/token`
    *   Headers:
        *   `Content-Type: application/x-www-form-urlencoded`
    *   Body Parameters:
        *   `refresh_token`: The refresh token.
        *   `client_id`: Your application's Client ID.
        *   `client_secret`: Your application's Client Secret.
        *   `grant_type=refresh_token`.
    *   Zoho will respond with a new `access_token`.

## **Object List**
The following objects can be retrieved from Zoho Books API v3:
*   Organizations
*   Contacts
*   Contact Persons
*   Estimates
*   Sales Orders
*   Sales Receipts
*   Invoices
*   Recurring Invoices
*   Credit Notes
*   Customer Debit Notes
*   Customer Payments
*   Expenses
*   Recurring Expenses
*   Bills
*   Vendor Credits
*   Purchase Orders
*   Recurring Bills
*   Vendors
*   Chart of Accounts
*   Bank Accounts
*   Bank Rules
*   Transaction Categories
*   Currencies
*   Taxes
*   Items
*   Locations
*   Opening Balance
*   Users
*   Zoho CRM Integration (import functionality)

The object list is static, derived from the Zoho Books API v3 documentation.

## **Object Schema**
The schema for a specific object can be inferred from the JSON response of the API when retrieving an individual object or a list of objects. For example, a `GET /contacts` request will return a list of contacts, from which the structure of a Contact object can be determined.

## **Get Object Primary Keys**
Primary key columns for objects can be identified from the API responses. Examples include:
*   Organizations: `organization_id`
*   Contacts: `contact_id`
*   Invoices: `invoice_id`
*   Estimates: `estimate_id`
*   Sales Orders: `salesorder_id`

## **Object's ingestion type**
The ingestion type for objects varies:

*   **`cdc` (Incremental with Deletes Captured)**: The Fivetran connector captures deletes for the following tables, implying a `cdc` (Change Data Capture) or similar incremental strategy that handles deletes:
    *   `BILL`
    *   `CHART_OF_ACCOUNT`
    *   `CREDIT_NOTE_REFUND`
    *   `CURRENCY`
    *   `ESTIMATE`
    *   `EXPENSE`
    *   `ITEM`
    *   `JOURNAL_LIST`
    *   `PROJECT`
    *   `PURCHASE_ORDER`
    *   `SALES_ORDER`
    *   `TAX`
    *   `TIME_ENTRY`
    *   `USERS`: `snapshot` (full sync; Airbyte documentation indicates it does not support incremental sync).

*   **`append` (Incremental)**: The Fivetran connector captures new records incrementally for tables like:
    *   `CONTACT`
    *   `CREDIT_NOTE`
    *   `CUSTOMER_PAYMENT`
    *   `INVOICE`

*   **Other Objects**: For objects not explicitly mentioned in Fivetran's documentation regarding incremental sync or delete capture, the ingestion type is TBD. These might default to `snapshot` if no incremental mechanism is available through the API.

## **Read API for Data Retrieval**
Data retrieval for objects is typically done using HTTP GET requests to their respective endpoints (e.g., `GET /contacts`, `GET /invoices`).

*   **Pagination**: The API supports pagination to retrieve large datasets. Parameters like `page` and `per_page` (or similar) are typically used, although explicit details on pagination parameters for each endpoint would need to be observed from individual API calls or further documentation.
*   **Incremental Data Retrieval & Delete Handling**: Based on Fivetran's implementation, some tables (`CONTACT`, `CREDIT_NOTE`, `CUSTOMER_PAYMENT`, `INVOICE`) support incremental sync for new records. For other tables (`BILL`, `CHART_OF_ACCOUNT`, `CREDIT_NOTE_REFUND`, `CURRENCY`, `ESTIMATE`, `EXPENSE`, `ITEM`, `JOURNAL_LIST`, `PROJECT`, `PURCHASE_ORDER`, `SALES_ORDER`, `TAX`, `TIME_ENTRY`, `USERS`), deletes are captured by re-importing the entire table.
*   **Query Parameters**: Each object's list endpoint supports various query parameters for filtering, sorting, and searching. Refer to the specific object's documentation within the Zoho Books API v3 reference for available parameters.
*   **Rate Limits**:
    *   **Per Minute**: 100 requests per minute per organization.
    *   **Per Day**:
        *   Free Plan - 1000 API requests/day
        *   Standard Plan - 2000 requests/day
        *   Professional Plan - 5000 requests/day
        *   Premium/Elite/Ultimate Plan - 10000 requests/day
    *   **Concurrent Calls**:
        *   Free Plan - 5 concurrent calls
        *   Paid Plans - 10 concurrent calls (soft limit)
    *   An HTTP status code 429 will be returned if limits are exceeded.
*   **Sync Frequency Recommendation**: Due to Zoho Books' API rate limitations, a sync frequency of 24 hours is recommended.

## **Field Type Mapping**
Field types are inferred from the example API responses. Common mappings to standard data types include:
*   Strings (e.g., names, addresses, descriptions)
*   Integers (e.g., IDs, quantities)
*   Floating-point numbers (e.g., amounts, rates)
*   Booleans (e.g., flags like `is_active`)
*   Date/Datetime (e.g., `account_created_date`, `created_time`)
*   Arrays of objects (for nested structures)

## **Write API**
The Zoho Books API v3 supports inserting and updating data using HTTP POST and PUT methods, respectively, for various objects.

*   **Create**: Use POST requests to the object's collection endpoint (e.g., `POST /contacts` to create a new contact). The request body typically contains the JSON representation of the object to be created.
*   **Update**: Use PUT requests to an individual object's endpoint (e.g., `PUT /contacts/{contact_id}` to update an existing contact). The request body contains the fields to be updated.
*   **Validation**: The API performs validation on the data submitted during write operations. Responses will indicate success or failure with relevant error messages.

## **Research Log**

| Source Type | URL | Accessed (UTC) | Confidence (High/Med/Low) | What it confirmed |
|---|---|---|---|---|
| Official Docs | https://www.zoho.com/books/api/v4/oauth/#overview | 2026-01-08 | High | OAuth 2.0 authorization flow, token exchange, refresh token usage, API request authentication. |
| Official Docs | https://www.zoho.com/books/api/v3/introduction/#overview | 2026-01-08 | High | Object list, general API structure, organization ID, multiple data centers, API call limits, concurrent rate limits, pagination, HTTP methods (GET, POST, PUT). |
| Fivetran Docs | https://fivetran.com/docs/connectors/applications/zoho-books | 2026-01-08 | High | Incremental sync strategies, delete capture mechanisms, recommended sync frequency, Fivetran-specific OAuth redirect URI. |
| Airbyte Docs | https://docs.airbyte.com/integrations/sources/zoho-books | 2026-01-08 | High | Confirmation of configuration parameters (Region, Client ID, Client Secret, Refresh Token, Start Date), and sync mode for the `USERS` stream. |

## **Sources and References**
*   [Zoho Books API v4 OAuth Overview](https://www.zoho.com/books/api/v4/oauth/#overview)
*   [Zoho Books API Docs v3 Introduction](https://www.zoho.com/books/api/v3/introduction/#overview)
*   [Fivetran Zoho Books Connector Documentation](https://fivetran.com/docs/connectors/applications/zoho-books)
