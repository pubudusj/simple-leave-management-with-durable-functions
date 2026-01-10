import os
import json
import re
import boto3
from datetime import datetime

lambda_client = boto3.client("lambda")
durable_function_arn = os.environ["DURABLE_FUNCTION_ARN"]

EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def validate_leave_request(body):
    # Validate required fields
    required_fields = ["start_date", "end_date", "employee_email"]
    missing_fields = [field for field in required_fields if field not in body]

    if missing_fields:
        return False, f"Missing required fields: {', '.join(missing_fields)}"

    # Validate date format (YYYY-MM-DD)
    try:
        start_date = datetime.strptime(body["start_date"], "%Y-%m-%d")
        end_date = datetime.strptime(body["end_date"], "%Y-%m-%d")

        # Validate end_date is after start_date
        if end_date < start_date:
            return False, "end_date must be equal to or after start_date"
    except ValueError as e:
        return False, f"Invalid date format. Use YYYY-MM-DD. {str(e)}"

    # Validate email format
    email = body["employee_email"]
    if not EMAIL_PATTERN.match(email):
        return False, "Invalid email format"

    return True, None


def handler(event, context):
    try:
        # Parse the body
        body = json.loads(event["body"])

        # Validate the request
        is_valid, error_message = validate_leave_request(body)
        if not is_valid:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": error_message}),
            }

        # Invoke durable function
        lambda_client.invoke(
            FunctionName=durable_function_arn,
            InvocationType="Event",
            Payload=json.dumps(body),
        )

        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Leave request submitted successfully"}),
        }

    except json.JSONDecodeError:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Invalid JSON in request body"}),
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": f"Internal server error: {str(e)}"}),
        }
