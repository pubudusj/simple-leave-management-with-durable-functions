import json
import boto3

lambda_client = boto3.client("lambda")


def handler(event, context):
    event = json.loads(event["body"])
    if "decision" not in event or event.get("decision") not in ["approve", "reject"]:
        return {
            "statusCode": 400,
            "body": json.dumps(
                {"message": "Invalid decision value, must be 'approve' or 'reject'."}
            ),
        }

    if "callback_id" not in event:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": "callback_id is required."}),
        }

    callback_id = event["callback_id"]
    decision = event["decision"]

    try:
        if decision == "approve":
            lambda_client.send_durable_execution_callback_success(
                CallbackId=callback_id, Result=json.dumps({"approved": True})
            )
        else:
            lambda_client.send_durable_execution_callback_failure(
                CallbackId=callback_id,
                Error={
                    "ErrorType": "LeaveRequestRejected",
                    "ErrorMessage": "Leave request was rejected by manager.",
                },
            )
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "message": "Error processing request",
                    "error": str(e),
                }
            ),
        }

    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Leave processed successfully."}),
    }
