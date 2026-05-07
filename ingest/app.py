import logging
from datetime import datetime, timezone

import boto3


import requests
from boto3.dynamodb.conditions import Key

import os

# =========================
# Basic configuration (using kubernetes secret)
# =========================
API_KEY = os.environ["API_KEY"]
S3_BUCKET = os.environ["S3_BUCKET"]

DDB_TABLE = os.environ.get("DDB_TABLE", "zyh4up-dp3")
AWS_REGION = "us-east-1"

# Keep this small so the plot stays readable
SECTIONS = ["world", "science", "business", "technology"]


# =========================
# Logging setup
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)


# =========================
# AWS clients
# =========================
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(DDB_TABLE)
s3 = boto3.client("s3", region_name=AWS_REGION)


def get_current_timestamp():
    """
    Return the current UTC timestamp in ISO format.

    This is used as the DynamoDB sort key so each run gets a unique time value.
    """
    try:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    except Exception as e:
        logger.error(f"Failed to create timestamp: {e}")
        raise

def get_seen_urls_for_section(section):
    """
    Read all historical rows for one section and collect every article URL
    previously stored for that section.

    Returns a set of URLs that have already been seen.
    """
    try:
        items = read_history_for_section(section)
        seen_urls = set()

        for item in items:
            urls = item.get("article_urls", [])
            if urls:
                for url in urls:
                    seen_urls.add(url)

        logger.info(f"Loaded {len(seen_urls)} seen URLs for section '{section}'")
        return seen_urls

    except Exception as e:
        logger.error(f"Failed to load seen URLs for section '{section}': {e}")
        raise

def fetch_section_count(section):
    """
    Call the NYT TimesWire API for one section and count only articles
    whose URLs have not been seen before for that section.

    First run is treated as a baseline:
    - store the returned URLs
    - set article_count to 0
    - prevents the initial API batch from creating a fake spike
    """
    try:
        url = f"https://api.nytimes.com/svc/news/v3/content/all/{section}.json"
        params = {"api-key": API_KEY}

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()

        data = response.json()
        results = data.get("results", [])

        current_urls = []
        for item in results:
            article_url = item.get("url")
            if article_url:
                current_urls.append(article_url)

        current_urls = list(dict.fromkeys(current_urls))

        seen_urls = get_seen_urls_for_section(section)

        if len(seen_urls) == 0:
            article_count = 0
            new_urls = current_urls
            is_baseline = True
        else:
            new_urls = [u for u in current_urls if u not in seen_urls]
            article_count = len(new_urls)
            is_baseline = False

        record = {
            "section": section,
            "timestamp": get_current_timestamp(),
            "article_count": article_count,
            "article_urls": new_urls,
            "is_baseline": is_baseline
        }

        logger.info(
            f"Fetched {section}: article_count={article_count}, "
            f"{len(current_urls)} URLs returned, baseline={is_baseline}"
        )

        return record

    except requests.RequestException as e:
        logger.error(f"Request failed for section '{section}': {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error while fetching section '{section}': {e}")
        raise


def write_record(record):
    """
    Write one record into DynamoDB.

    The table uses:
    - partition key: section
    - sort key: timestamp
    """
    try:
        table.put_item(Item=record)
        logger.info(
            f"Wrote record to DynamoDB: "
            f"{record['section']} | {record['timestamp']} | {record['article_count']}"
        )
    except Exception as e:
        logger.error(f"Failed to write record to DynamoDB: {e}")
        raise


def read_history_for_section(section):
    """
    Read all saved records for a single section from DynamoDB.

    Because section is the partition key, we query one section at a time.
    """
    try:
        items = []

        response = table.query(
            KeyConditionExpression=Key("section").eq(section)
        )
        items.extend(response.get("Items", []))

        while "LastEvaluatedKey" in response:
            response = table.query(
                KeyConditionExpression=Key("section").eq(section),
                ExclusiveStartKey=response["LastEvaluatedKey"]
            )
            items.extend(response.get("Items", []))

        logger.info(f"Loaded {len(items)} historical rows for section '{section}'")
        return items

    except Exception as e:
        logger.error(f"Failed to read history for section '{section}': {e}")
        raise




def main(event=None, context=None):
    """
    Run one ingestion cycle.

    Steps:
    1. Fetch current NYT section counts
    2. Write each result to DynamoDB

    Plotting is handled separately by plotter/app.py.
    """
    try:
        logger.info("Starting NYT ingestion run")

        for section in SECTIONS:
            record = fetch_section_count(section)
            write_record(record)

        logger.info("Ingestion run completed successfully")

    except Exception as e:
        logger.error(f"Ingestion run failed: {e}")
        raise