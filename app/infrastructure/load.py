import boto3
import os

TABLE_NAME = os.getenv("HEALTH_TRACKER_TABLE_NAME", "health-tracker")
REGION = os.getenv("AWS_REGION", "us-west-2")

_dynamodb_table = None

def load_dynamodb_table():
    """Get DynamoDB table resource with connection reuse."""
    global _dynamodb_table
    if _dynamodb_table is None:
        dynamodb_resource = boto3.resource('dynamodb', region_name=REGION)
        _dynamodb_table = dynamodb_resource.Table(TABLE_NAME)
    return _dynamodb_table
