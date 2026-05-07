# DP3: NYT TimesWire Section Activity Tracker

## Project Overview

This project tracks article activity from the New York Times TimesWire API across four major sections: world, science, business, and technology. The goal is to collect a time series of newly observed articles by section so that changes in news activity can be monitored over time. A single API pull is not very meaningful on its own, but repeated samples can show which sections are more active, when spikes happen, and how article volume changes across runs.

## Data Source

The data source is the NYT TimesWire API:

- Source: New York Times TimesWire API
- Tracked sections:
  - `world`
  - `science`
  - `business`
  - `technology`

I chose this source because it changes frequently throughout the day and naturally fits a time-series ingestion project. Each run checks the most recent articles returned by the API and compares their URLs against previously seen article URLs in DynamoDB. This avoids counting the same returned API batch repeatedly.

The first run for each section is treated as a baseline. Since the NYT API returns a recent batch of articles, the first run stores those URLs but sets the article count to `0` so the visualization does not start with a fake spike.

## Sampling Cadence

The ingestion Lambda is scheduled to run every hour using EventBridge.

Each run:

1. Calls the NYT TimesWire API for each tracked section.
2. Extracts article URLs from the API response.
3. Checks DynamoDB for URLs that have already been seen.
4. Counts only newly observed article URLs.
5. Writes a timestamped record to DynamoDB.

A separate plotter Lambda reads the accumulated DynamoDB records, regenerates the latest plot using matplotlib, and uploads the image to S3. The API’s `/plot` resource returns the public S3 URL for that latest plot.

## Storage Schema

The project uses DynamoDB as the persistent store.

Table name:

```text
zyh4up-dp3
```

Primary key design:

| Attribute | Type | Purpose |
|---|---|---|
| `section` | String | Partition key. Identifies the NYT section being tracked. |
| `timestamp` | String | Sort key. Stores the UTC timestamp for each ingestion run. |

Additional fields:

| Attribute | Type | Description |
|---|---|---|
| `article_count` | Number | Number of newly observed article URLs for that section during the run. |
| `article_urls` | List | New article URLs found during that run. |
| `is_baseline` | Boolean | Marks whether the row is the initial baseline sample for that section. |

Example item:

```json
{
  "section": "science",
  "timestamp": "2026-05-07T02:45:00+00:00",
  "article_count": 3,
  "article_urls": [
    "https://www.nytimes.com/example-article.html"
  ],
  "is_baseline": false
}
```

This schema makes it easy to query each section as its own time series using `section` as the partition key and `timestamp` as the sort key.

## API Resources

The integration API is built with Chalice and deployed through API Gateway + Lambda. The API follows the required course bot format, where the root endpoint lists available resources and each resource returns a JSON object with a `response` key.

### `GET /`

Returns a short description of the project and the list of available API resources.

Example response:

```json
{
  "about": "Tracks new NYT TimesWire articles across world, science, business, and technology over time.",
  "resources": ["current", "trend", "plot"]
}
```

### `GET /current`

Returns the most recent new-article count for each tracked section.

Example response:

```json
{
  "response": {
    "world": 2,
    "science": 1,
    "business": 4,
    "technology": 3
  }
}
```

### `GET /trend`

Returns a short summary of which section had the most new articles in the latest run.

Example response:

```json
{
  "response": "business currently has the most new articles, with 4 new articles in the latest run."
}
```

### `GET /plot`

Returns the public S3 URL for the latest generated plot.

Example response:

```json
{
  "response": "https://zyh4up-dp3.s3.amazonaws.com/plot.png"
}
```

The plot is stored in S3 as a PNG and is publicly readable so it can be opened by the course Discord bot.

## Plot

The plot shows new NYT TimesWire articles per run over time for each tracked section. The baseline rows are filtered out so the chart reflects new activity after tracking begins rather than the initial batch returned by the API.

The plot is generated using matplotlib and uploaded to S3 at a stable key:

```text
s3://zyh4up-dp3/plot.png
```

The API does not regenerate the plot on request. Instead, the `/plot` endpoint returns the latest plot URL from S3.

## Architecture

```text
EventBridge Schedule
        ↓
Ingest Lambda
        ↓
NYT TimesWire API
        ↓
DynamoDB table: zyh4up-dp3
        ↓
Plotter Lambda
        ↓
S3: plot.png and data.csv
        ↓
Chalice API
        ↓
Discord bot / API users
```



