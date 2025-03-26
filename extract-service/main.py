import os
import json
import requests
from google.cloud import storage
import functions_framework

# Configuration
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "etlpipelinehomeworkhbcloudrun")

# GraphQL API endpoint and headers
URL = "https://www.coursera.org/graphql-gateway?opname=DiscoveryCollections"
HEADERS = {
    "accept": "application/json",
    "content-type": "application/json",
    "operation-name": "DiscoveryCollections",
    "origin": "https://www.coursera.org",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "x-csrf3-token": "1743681871.xQuQa8u8tAbHg2hP",  # Replace with a fresh token
}
PAYLOAD = [
    {
        "operationName": "DiscoveryCollections",
        "variables": {"contextType": "PAGE", "contextId": "search-zero-state"},
        "query": """
        query DiscoveryCollections($contextType: String!, $contextId: String!, $passThroughParameters: [DiscoveryCollections_PassThroughParameter!]) {
          DiscoveryCollections {
            queryCollections(
              input: {contextType: $contextType, contextId: $contextId, passThroughParameters: $passThroughParameters}
            ) {
              id
              label
              entities {
                id
                slug
                name
                url
              }
            }
          }
        }
    """,
    }
]


def upload_to_gcs(bucket_name, source_file_name, destination_blob_name):
    """Uploads a file to GCS."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_filename(source_file_name)
    print(f"Uploaded {source_file_name} to gs://{bucket_name}/{destination_blob_name}")


def extract_data():
    """Extracts data from the Coursera API and returns the raw JSON response."""
    try:
        response = requests.post(URL, headers=HEADERS, json=PAYLOAD)
        if response.status_code != 200:
            print(f"API failed with status {response.status_code}: {response.text}")
            raise Exception(f"API request failed: {response.status_code}")
        data = response.json()
        print("API request succeeded")
        return data
    except Exception as e:
        print(f"Error during extraction: {str(e)}")
        raise e


@functions_framework.http
def main(request):
    try:
        # Extract data from Coursera API
        raw_data = extract_data()

        # Save raw JSON to GCS
        json_file_path = "/tmp/coursera_response.json"
        with open(json_file_path, "w") as json_file:
            json.dump(raw_data, json_file)
        upload_to_gcs(GCS_BUCKET_NAME, json_file_path, "coursera_response.json")

        return (
            json.dumps({"status": "success"}),
            200,
            {"Content-Type": "application/json"},
        )

    except Exception as e:
        print(f"Error: {str(e)}")
        return (
            json.dumps({"status": "error", "message": str(e)}),
            500,
            {"Content-Type": "application/json"},
        )
