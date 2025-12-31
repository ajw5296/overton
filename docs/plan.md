# Plan for OpenAlex Data Fetcher

This document outlines the plan for creating a Python script to fetch DOIs from the OpenAlex API.

## 1. Script Objective

The primary goal is to create a script (`scripts/openalex_fetch.py`) that retrieves all DOIs from OpenAlex associated with a specific research institution (e.g., Penn State) within a given year range.

## 2. Key Features

- **API Connection:** Connect to the OpenAlex API to fetch works.
- **Filtering:** Filter works by institution and publication year.
- **Data Extraction:** Extract the DOI from each relevant work.
- **Pagination:** Handle paginated results to retrieve all records.
- **Configuration:** Use a `.env` file for API keys or other sensitive information.
- **Output:** Save the list of DOIs to a file (e.g., `psu_dois.json`).

## 3. Implementation Steps

1.  **Create `scripts/openalex_fetch.py`:** A new Python script to house the logic.
2.  **Implement `get_openalex_data` function:**
    -   Construct the API request URL with filters for institution ROR and publication year range.
    -   Use the `requests` library to make the API call.
    -   Loop through the paginated results using the `cursor` feature.
    -   Extract the DOI from each result.
    -   Store the DOIs in a list.
3.  **Implement `main` function:**
    -   Define the target institution and year range.
    -   Call `get_openalex_data` to get the list of DOIs.
    -   Save the list of DOIs to a JSON file in the `keep/openalex_exports/` directory.
4.  **Add Error Handling and Logging:** Include `try-except` blocks to handle potential API errors and add print statements or logging to track progress.

## 4. Next Steps

- Switch to **Code** mode.
- Create the `scripts/openalex_fetch.py` file with the initial code structure.
- Implement the API fetching logic.