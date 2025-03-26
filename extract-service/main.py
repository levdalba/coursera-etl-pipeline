from flask import Flask
import os
import requests
from google.cloud import storage
import json
import logging
from datetime import datetime

# Set up logging for better debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration (use environment variables for flexibility)
GCS_BUCKET_NAME = os.getenv(
    "GCS_BUCKET_NAME", "etlpipelinehomeworkhbcloudrun-asia-southeast1"
)

# Coursera API headers (update x-csrf3-token with a fresh value)
HEADERS = {
    "accept": "application/json",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "en",
    "apollographql-client-name": "search-v2",
    "apollographql-client-version": "7632fa15d8fa40347c6e478bba89b2bbc90f70a7",
    "content-type": "application/json",
    "operation-name": "DiscoveryCollections",
    "origin": "https://www.coursera.org",
    "referer": "https://www.coursera.org/search?query=machine%20learning",
    "sec-ch-ua": '"Chromium";v="134", "Not:A-Brand";v="24", "Brave";v="134"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "x-csrf3-token": os.getenv(
        "COURSEERA_CSRF_TOKEN",
        "1743681871.xQuQa8u8tAbHg2hP",  # Replace with a fresh token
    ),
    "cookie": f"csrf3-token={os.getenv('COURSEERA_CSRF_TOKEN', '1743681871.xQuQa8u8tAbHg2hP')}",
}

# Coursera API query
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
              ...DiscoveryCollections_DiscoveryCollection
              __typename
            }
            __typename
          }
        }

        fragment DiscoveryCollections_DiscoveryCollection on DiscoveryCollections_productCollection {
          __typename
          id
          label
          linkedCollectionPageMetadata {
            url
            __typename
          }
          entities {
            ...DiscoveryCollections_DiscoveryEntity
            __typename
          }
        }

        fragment DiscoveryCollections_DiscoveryEntity on DiscoveryCollections_learningProduct {
          __typename
          id
          slug
          name
          url
          partnerIds
          imageUrl
          partners {
            ...DiscoveryCollections_DiscoveryCollectionsPartner
            __typename
          }
          ... on DiscoveryCollections_specialization {
            courseCount
            difficultyLevel
            isPartOfCourseraPlus
            productCard {
              ...DiscoveryCollections_ProductCard
              __typename
            }
            __typename
          }
          ... on DiscoveryCollections_course {
            difficultyLevel
            isPartOfCourseraPlus
            isCostFree
            productCard {
              ...DiscoveryCollections_ProductCard
              __typename
            }
            __typename
          }
          ... on DiscoveryCollections_professionalCertificate {
            difficultyLevel
            isPartOfCourseraPlus
            productCard {
              ...DiscoveryCollections_ProductCard
              __typename
            }
            __typename
          }
        }

        fragment DiscoveryCollections_DiscoveryCollectionsPartner on DiscoveryCollections_partner {
          id
          name
          logo
          __typename
        }

        fragment DiscoveryCollections_ProductCard on ProductCard_ProductCard {
          id
          marketingProductType
          productTypeAttributes {
            ... on ProductCard_Specialization {
              isPathwayContent
              __typename
            }
            ... on ProductCard_Course {
              isPathwayContent
              __typename
            }
            __typename
          }
          __typename
        }
        """,
    }
]


def extract_data():
    """Fetch data from the Coursera GraphQL API."""
    try:
        url = "https://www.coursera.org/graphql-gateway?opname=DiscoveryCollections"
        response = requests.post(url, headers=HEADERS, json=PAYLOAD)
        response.raise_for_status()  # Raises an exception for 4xx/5xx status codes
        logger.info("API request succeeded")

        # Parse the response
        data = response.json()

        # Check for errors in the response
        if isinstance(data, list) and len(data) > 0 and "error" in data[0]:
            error_message = data[0].get("message", "Unknown error")
            raise Exception(
                f"API returned an error: {data[0]['error']} - {error_message}"
            )

        # Extract collections
        collections = (
            data[0]
            .get("data", {})
            .get("DiscoveryCollections", {})
            .get("queryCollections", [])
        )
        if not collections:
            raise Exception("No collections found in API response")

        # Extract courses from the collections
        courses = []
        for collection in collections:
            for entity in collection.get("entities", []):
                courses.append(entity)

        logger.info(f"Received {len(courses)} courses")
        if not courses:
            raise Exception("No courses found in API response")

        return data
    except requests.RequestException as e:
        logger.error(f"Error during API request: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error processing API response: {str(e)}")
        raise


def upload_to_gcs(data, bucket_name, destination_blob_name):
    """Upload data to Google Cloud Storage."""
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)
        blob.upload_from_string(
            json.dumps(data, indent=2), content_type="application/json"
        )
        logger.info(
            f"Uploaded {destination_blob_name} to gs://{bucket_name}/{destination_blob_name}"
        )
    except Exception as e:
        logger.error(f"Error uploading to GCS: {str(e)}")
        raise


@app.route("/", methods=["GET"])
def main():
    """Main endpoint to trigger the extract process."""
    try:
        data = extract_data()
        # Use a timestamp to avoid overwriting files
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        destination_blob_name = f"coursera_response_{timestamp}.json"
        upload_to_gcs(data, GCS_BUCKET_NAME, destination_blob_name)
        return {"status": "success", "blob_name": destination_blob_name}, 200
    except Exception as e:
        logger.error(f"Error in extract service: {str(e)}")
        return {"status": "error", "message": str(e)}, 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
