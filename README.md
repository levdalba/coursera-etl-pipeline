# Coursera ETL Pipeline

This repository contains an ETL (Extract, Transform, Load) pipeline built with Google Cloud services. The pipeline extracts course data from the Coursera API, saves it to Google Cloud Storage (GCS), transforms the data, and loads it into BigQuery. The pipeline is deployed as two Cloud Run functions, with the extract function triggered on a schedule using Cloud Scheduler.

## Architecture

1. **Extract Service (`extract-service`)**: A Cloud Run function that fetches course data from the Coursera GraphQL API and uploads it as a JSON file to GCS. It is triggered daily by Cloud Scheduler.
2. **Transform Service (`transform-service`)**: A Cloud Run function that transforms the JSON data into CSV format and loads it into BigQuery. This is manually triggered after the extract service runs.
3. **Cloud Scheduler**: Triggers the `extract-service` daily to automate the pipeline.

## Directory Structure
```
coursera-etl-pipeline/
├── extract-service/
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
├── transform-service/
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
├── .dockerignore
├── .gitignore
├── cloudbuild.yaml
├── cloudbuild-extract.yaml
├── cloudbuild-transform.yaml
├── README.md
└── requirements.txt
```

## Prerequisites

- A Google Cloud project (e.g., `training-triggering-pipeline`) with the following APIs enabled:
  - Cloud Run API
  - Cloud Storage API
  - BigQuery API
  - Cloud Scheduler API
  - Cloud Build API
- A GCS bucket (e.g., `etlpipelinehomeworkhbcloudrun-asia-southeast1`).
- A BigQuery dataset (e.g., `coursera_data`) and table (e.g., `courses`) with the following schema:

```json
[
  {"name": "collection_label", "type": "STRING"},
  {"name": "collection_id", "type": "STRING"},
  {"name": "course_name", "type": "STRING"},
  {"name": "course_id", "type": "STRING"},
  {"name": "slug", "type": "STRING"},
  {"name": "url", "type": "STRING"},
  {"name": "image_url", "type": "STRING"},
  {"name": "partners", "type": "STRING"},
  {"name": "partner_ids", "type": "STRING"},
  {"name": "difficulty_level", "type": "STRING"},
  {"name": "is_part_of_coursera_plus", "type": "BOOLEAN"},
  {"name": "course_count", "type": "STRING"},
  {"name": "is_cost_free", "type": "STRING"},
  {"name": "marketing_product_type", "type": "STRING"},
  {"name": "is_pathway_content", "type": "BOOLEAN"}
]
```

## Setup Instructions

### 1. Clone the Repository
```bash
git clone https://github.com/levandalbashvili/coursera-etl-pipeline.git
cd coursera-etl-pipeline
```

### 2. Update the Coursera API Token
Open `extract-service/main.py` and update the `x-csrf3-token` in the `HEADERS` dictionary with a fresh token obtained from the Coursera website (see Troubleshooting for details).

### 3. Deploy the Cloud Run Functions
Deploy both services using Cloud Build:
```bash
gcloud builds submit --config cloudbuild.yaml
```
Alternatively, deploy individually:
```bash
gcloud builds submit --config cloudbuild-extract.yaml
gcloud builds submit --config cloudbuild-transform.yaml
```

### 4. Fix Authentication
Grant unauthenticated access to both services:
```bash
gcloud beta run services add-iam-policy-binding extract-service \
  --region=asia-southeast1 \
  --member=allUsers \
  --role=roles/run.invoker

gcloud beta run services add-iam-policy-binding transform-service \
  --region=asia-southeast1 \
  --member=allUsers \
  --role=roles/run.invoker
```

### 5. Set Up Cloud Scheduler
Create a job to trigger `extract-service` daily:
```bash
gcloud scheduler jobs create http etl-extract-job \
  --schedule="0 0 * * *" \
  --uri="https://extract-service-974091072034.asia-southeast1.run.app" \
  --http-method=GET \
  --location=asia-southeast1
```
Grant Cloud Scheduler permission to invoke `extract-service`:
```bash
gcloud run services add-iam-policy-binding extract-service \
  --region=asia-southeast1 \
  --member=serviceAccount:service-974091072034@gcp-sa-cloudscheduler.iam.gserviceaccount.com \
  --role=roles/run.invoker
```

### 6. Test the Pipeline
Trigger `extract-service` manually (or wait for the scheduled run):
```bash
curl https://extract-service-974091072034.asia-southeast1.run.app
```
Verify that a file (e.g., `coursera_response_YYYYMMDD_HHMMSS.json`) is uploaded to GCS:
```bash
gsutil ls "gs://etlpipelinehomeworkhbcloudrun-asia-southeast1/coursera_response_*"
```
Trigger `transform-service` manually to process the file:
```bash
curl https://transform-service-974091072034.asia-southeast1.run.app
```
Check `transform-service` logs to confirm it processed the file and loaded data into BigQuery:
```bash
gcloud logging read 'resource.type="cloud_run_revision" resource.labels.service_name="transform-service"' --limit=10 --format="value(textPayload)"
```
Query BigQuery to confirm the data:
```bash
bq query --location=asia-southeast1 --nouse_legacy_sql "SELECT * FROM coursera_data.courses LIMIT 10"
```

## IAM Permissions
Ensure the following roles are assigned:

### Cloud Run Service Account (`974091072034-compute@developer.gserviceaccount.com`):
- `roles/storage.admin` (for GCS access)
- `roles/bigquery.dataEditor` (for BigQuery access)

### Cloud Scheduler Service Account (`service-974091072034@gcp-sa-cloudscheduler.iam.gserviceaccount.com`):
- `roles/run.invoker` (to invoke `extract-service`)

## Troubleshooting

### Cloud Scheduler Not Triggering
Check the scheduler job status and logs:
```bash
gcloud scheduler jobs describe etl-extract-job --location=asia-southeast1
gcloud logging read "resource.type=cloud_scheduler_job" --limit=10
```

### Coursera API Token Expired
The `x-csrf3-token` in `extract-service/main.py` may expire. To update it:
1. Open a browser and go to [Coursera](https://www.coursera.org).
2. Open Developer Tools (`F12`) and go to the **Network** tab.
3. Filter for GraphQL requests and find a request to `https://www.coursera.org/graphql-gateway`.
4. Copy the `x-csrf3-token` from the request headers.
5. Update the token in `extract-service/main.py` and redeploy.

### zsh Wildcard Issue
If using `zsh`, quote the URL when using wildcards with `gsutil`:
```bash
gsutil ls "gs://etlpipelinehomeworkhbcloudrun-asia-southeast1/coursera_response_*"
