from flask import Flask
import os
import json
import csv
import logging
from google.cloud import storage
from google.cloud import bigquery
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
GCS_BUCKET_NAME = os.getenv(
    "GCS_BUCKET_NAME", "etlpipelinehomeworkhbcloudrun-asia-southeast1"
)
BQ_DATASET = "coursera_data"
BQ_TABLE = "courses"


def download_from_gcs(bucket_name, source_blob_name, destination_file_name):
    """Download a file from GCS."""
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(source_blob_name)
        blob.download_to_filename(destination_file_name)
        logger.info(
            f"Downloaded gs://{bucket_name}/{source_blob_name} to {destination_file_name}"
        )
    except Exception as e:
        logger.error(f"Error downloading from GCS: {str(e)}")
        raise


def upload_to_gcs(bucket_name, source_file_name, destination_blob_name):
    """Upload a file to GCS."""
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)
        blob.upload_from_filename(source_file_name)
        logger.info(
            f"Uploaded {source_file_name} to gs://{bucket_name}/{destination_blob_name}"
        )
    except Exception as e:
        logger.error(f"Error uploading to GCS: {str(e)}")
        raise


def load_to_bigquery(dataset_id, table_id, source_file_name):
    """Load CSV data into BigQuery."""
    try:
        client = bigquery.Client()
        dataset_ref = client.dataset(dataset_id)
        table_ref = dataset_ref.table(table_id)

        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,  # Skip the header row
            autodetect=True,  # Automatically detect schema
            write_disposition="WRITE_APPEND",  # Append data to the table
        )

        with open(source_file_name, "rb") as source_file:
            job = client.load_table_from_file(
                source_file, table_ref, job_config=job_config
            )
        job.result()  # Wait for the job to complete
        logger.info(f"Inserted {job.output_rows} rows into BigQuery table {table_id}")
    except Exception as e:
        logger.error(f"Error loading to BigQuery: {str(e)}")
        raise


@app.route("/", methods=["GET"])
def main():
    """Main endpoint to transform JSON to CSV and load into BigQuery."""
    try:
        # Find the latest JSON file in GCS
        storage_client = storage.Client()
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blobs = list(bucket.list_blobs(prefix="coursera_response_"))
        if not blobs:
            raise Exception("No JSON files found in GCS")
        latest_blob = max(blobs, key=lambda b: b.name)
        json_file_path = f"/tmp/{latest_blob.name}"
        download_from_gcs(GCS_BUCKET_NAME, latest_blob.name, json_file_path)

        # Read the JSON file
        with open(json_file_path, "r") as json_file:
            data = json.load(json_file)

        # Extract collections
        collections = data[0]["data"]["DiscoveryCollections"]["queryCollections"]

        # Prepare data for CSV
        csv_data = []
        for collection in collections:
            collection_label = collection["label"]
            collection_id = collection["id"]
            for entity in collection["entities"]:
                # Flatten nested partner data
                partners = ", ".join(
                    [partner["name"] for partner in entity["partners"]]
                )
                partner_ids = ", ".join(entity["partnerIds"])

                # Base entity fields
                row = {
                    "collection_label": collection_label,
                    "collection_id": collection_id,
                    "course_name": entity["name"],
                    "course_id": entity["id"],
                    "slug": entity["slug"],
                    "url": entity["url"],
                    "image_url": entity["imageUrl"],
                    "partners": partners,
                    "partner_ids": partner_ids,
                    "difficulty_level": entity.get("difficultyLevel", "N/A"),
                    "is_part_of_coursera_plus": entity.get(
                        "isPartOfCourseraPlus", False
                    ),
                    "course_count": entity.get("courseCount", "N/A"),
                    "is_cost_free": entity.get("isCostFree", "N/A"),
                    "marketing_product_type": entity["productCard"][
                        "marketingProductType"
                    ],
                    "is_pathway_content": entity["productCard"][
                        "productTypeAttributes"
                    ]["isPathwayContent"],
                }
                csv_data.append(row)

        logger.info(f"Transformed {len(csv_data)} rows")

        # Define CSV headers
        csv_headers = [
            "collection_label",
            "collection_id",
            "course_name",
            "course_id",
            "slug",
            "url",
            "image_url",
            "partners",
            "partner_ids",
            "difficulty_level",
            "is_part_of_coursera_plus",
            "course_count",
            "is_cost_free",
            "marketing_product_type",
            "is_pathway_content",
        ]

        # Save to CSV
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        csv_file_path = f"/tmp/coursera_courses_{timestamp}.csv"
        with open(csv_file_path, "w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=csv_headers)
            writer.writeheader()
            writer.writerows(csv_data)
        logger.info(f"Wrote {len(csv_data)} rows to {csv_file_path}")

        # Upload CSV to GCS
        csv_blob_name = f"coursera_courses_{timestamp}.csv"
        upload_to_gcs(GCS_BUCKET_NAME, csv_file_path, csv_blob_name)

        # Load CSV into BigQuery
        load_to_bigquery(BQ_DATASET, BQ_TABLE, csv_file_path)

        return {"status": "success", "csv_blob_name": csv_blob_name}, 200
    except Exception as e:
        logger.error(f"Error in transform service: {str(e)}")
        return {"status": "error", "message": str(e)}, 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
