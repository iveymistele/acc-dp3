import logging
import os
from decimal import Decimal

import boto3
import matplotlib.pyplot as plt
import pandas as pd
from boto3.dynamodb.conditions import Key

DDB_TABLE = os.environ.get("DDB_TABLE", "zyh4up-dp3")
S3_BUCKET = os.environ["S3_BUCKET"]
AWS_REGION = "us-east-1"

SECTIONS = ["world", "science", "business", "technology"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(DDB_TABLE)
s3 = boto3.client("s3", region_name=AWS_REGION)


def read_history_for_section(section):
    """
    Read all saved records for a single section from DynamoDB.
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


def read_all_history():
    """
    Read all historical records for all tracked sections and combine into a DataFrame.
    """
    try:
        all_items = []

        for section in SECTIONS:
            all_items.extend(read_history_for_section(section))

        if not all_items:
            logger.warning("No historical data found")
            return pd.DataFrame(columns=["section", "timestamp", "article_count", "is_baseline"])

        df = pd.DataFrame(all_items)

        df["article_count"] = pd.to_numeric(df["article_count"], errors="coerce")
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")

        if "is_baseline" in df.columns:
            df = df[df["is_baseline"] != True]

        df = df.sort_values(["section", "timestamp"]).reset_index(drop=True)

        logger.info(f"Built plot DataFrame with {len(df)} rows")
        return df

    except Exception as e:
        logger.error(f"Failed to build historical DataFrame: {e}")
        raise


def make_plot(df, output_file="/tmp/plot.png"):
    """
    Create a line plot of new article counts over time for each section.
    """
    try:
        plt.figure(figsize=(10, 6))

        if df.empty:
            plt.text(0.5, 0.5, "No data available yet", ha="center", va="center")
            plt.title("NYT Section Activity Over Time")
            plt.xlabel("Time")
            plt.ylabel("New Articles per Run")
        else:
            label_map = {
                "world": "World News",
                "business": "Business",
                "science": "Science",
                "technology": "Technology"
            }

            for section in sorted(df["section"].unique()):
                section_df = df[df["section"] == section]

                plt.plot(
                    section_df["timestamp"],
                    section_df["article_count"],
                    marker="o",
                    label=label_map.get(section, section)
                )

            plt.title("NYT Section Activity Over Time")
            plt.xlabel("Timestamp (UTC)")
            plt.ylabel("New Articles per Run")
            plt.xticks(rotation=30, ha="right")
            plt.legend()

        plt.tight_layout()
        plt.savefig(output_file, dpi=150)
        plt.close()

        logger.info(f"Saved plot to {output_file}")

    except Exception as e:
        logger.error(f"Failed to create plot: {e}")
        raise


def save_csv(df, output_file="/tmp/data.csv"):
    """
    Save historical data to CSV.
    """
    try:
        df_to_save = df.copy()

        if "timestamp" in df_to_save.columns:
            df_to_save["timestamp"] = df_to_save["timestamp"].astype(str)

        df_to_save.to_csv(output_file, index=False)
        logger.info(f"Saved CSV to {output_file}")

    except Exception as e:
        logger.error(f"Failed to save CSV: {e}")
        raise


def upload_to_s3(local_file, s3_key, content_type):
    """
    Upload file to S3.
    """
    try:
        with open(local_file, "rb") as f:
            s3.upload_fileobj(
                f,
                S3_BUCKET,
                s3_key,
                ExtraArgs={
                    "ContentType": content_type
                }
            )

        logger.info(f"Uploaded {local_file} to s3://{S3_BUCKET}/{s3_key}")

    except Exception as e:
        logger.error(f"Failed to upload {local_file} to S3: {e}")
        raise


def main(event=None, context=None):
    """
    Render latest plot and CSV from DynamoDB history.
    """
    try:
        logger.info("Starting plot render run")

        history_df = read_all_history()

        make_plot(history_df, "/tmp/plot.png")
        save_csv(history_df, "/tmp/data.csv")

        upload_to_s3("/tmp/plot.png", "plot.png", "image/png")
        upload_to_s3("/tmp/data.csv", "data.csv", "text/csv")

        logger.info("Plot render completed successfully")

    except Exception as e:
        logger.error(f"Plot render failed: {e}")
        raise


if __name__ == "__main__":
    main()