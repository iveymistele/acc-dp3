from chalice import Chalice
import os
import boto3
from boto3.dynamodb.conditions import Key

app = Chalice(app_name="nyt-dp3-api")

DDB_TABLE = os.environ.get("DDB_TABLE", "zyh4up-dp3")
S3_BUCKET = os.environ.get("S3_BUCKET")
AWS_REGION = "us-east-1"

dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(DDB_TABLE)

SECTIONS = ["world", "science", "business", "technology"]


def latest_for_section(section):
    response = table.query(
        KeyConditionExpression=Key("section").eq(section),
        ScanIndexForward=False,
        Limit=1
    )
    items = response.get("Items", [])
    return items[0] if items else None


@app.route("/")
def index():
    return {
        "about": "Tracks new NYT TimesWire articles across world, science, business, and technology over time.",
        "resources": ["current", "trend", "plot"]
    }


@app.route("/current")
def current():
    latest = {}

    for section in SECTIONS:
        item = latest_for_section(section)
        if item:
            latest[section] = int(item.get("article_count", 0))

    return {
        "response": latest
    }


@app.route("/trend")
def trend():
    latest = {}

    for section in SECTIONS:
        item = latest_for_section(section)
        if item:
            latest[section] = int(item.get("article_count", 0))

    if not latest:
        return {"response": "No data available yet."}

    top_section = max(latest, key=latest.get)

    return {
        "response": f"{top_section} currently has the most new articles, with {latest[top_section]} new articles in the latest run."
    }


@app.route("/plot")
def plot():
    plot_url = f"https://{S3_BUCKET}.s3.amazonaws.com/plot.png"

    return {
        "response": plot_url
    }