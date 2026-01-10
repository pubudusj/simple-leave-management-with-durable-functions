import os
import json
import uuid
import boto3
from aws_durable_execution_sdk_python import (
    DurableContext,
    durable_execution,
    durable_step,
)
from aws_durable_execution_sdk_python.config import Duration, WaitForCallbackConfig
from aws_durable_execution_sdk_python.exceptions import CallableRuntimeError

dynamodb = boto3.resource("dynamodb")
ses = boto3.client("ses")

table = dynamodb.Table(os.environ["DDB_TABLE_NAME"])
MANAGER_EMAIL = os.environ["MANAGER_EMAIL"]
SYSTEM_FROM_EMAIL = os.environ["SYSTEM_FROM_EMAIL"]


@durable_execution
def handler(event, context: DurableContext):
    # Add leave record to DynamoDB
    leave_id = context.step(add_leave_record(event))

    # Send email to employee confirming leave request submission
    context.step(
        notify_employee_leave_submission(
            employee_email=event["employee_email"],
            leave_id=leave_id,
        )
    )

    # Send notification email to manager and wait for manager approval
    try:
        manager_approval = context.wait_for_callback(
            lambda step_context, callback_id: notify_manager(
                step_context,
                callback_id,
                manager_email=MANAGER_EMAIL,
                leave_id=leave_id,
            ),
            name="manager-approval",
            config=WaitForCallbackConfig(
                timeout=Duration.from_minutes(5),
                heartbeat_timeout=Duration.from_minutes(5),
            ),
        )

        if manager_approval:
            approval_data = json.loads(manager_approval)
            new_status = "approved" if approval_data.get("approved") else "rejected"
    except CallableRuntimeError as e:
        if "Callback timed out" in str(e):
            # Callback timed out
            new_status = "expired"
        elif "Leave request rejected by manager" in str(e):
            # Rejection callback
            new_status = "rejected"
        else:
            raise e

    # Update the leave status in DynamoDB
    context.step(
        update_leave_status(leave_id, event["employee_email"], status=new_status)
    )

    # Send email to the employee about the approval/rejection
    context.step(
        notify_employee_leave_process(
            employee_email=event["employee_email"],
            leave_id=leave_id,
            status=new_status,
        )
    )

    return {
        "statusCode": 200,
        "body": json.dumps(
            {"message": "Leave request processed successfully", "leave_id": leave_id}
        ),
    }


@durable_step
def add_leave_record(
    step_context,
    event: dict,
) -> str:
    employee_email = event["employee_email"]
    start_date = event["start_date"]
    end_date = event["end_date"]

    # Generate unique leave ID
    leave_id = str(uuid.uuid4())
    pk = f"Leave#{leave_id}"

    # Add record to DynamoDB table
    table.put_item(
        Item={
            "pk": pk,
            "sk": employee_email,
            "start_date": start_date,
            "end_date": end_date,
            "status": "pending",
        }
    )

    return leave_id


@durable_step
def update_leave_status(
    step_context,
    leave_id: str,
    employee_email: str,
    status: str,
) -> None:
    pk = f"Leave#{leave_id}"

    # Update the leave status in DynamoDB table
    table.update_item(
        Key={"pk": pk, "sk": employee_email},
        UpdateExpression="SET #s = :new_status",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":new_status": status},
    )


@durable_step
def notify_employee_leave_submission(step_context, employee_email: str, leave_id: str):
    subject = "Leave Request Submitted"
    body = f"<p>Your leave request with ID {leave_id} has been submitted and is pending approval from the manager.</p>"
    send_email(employee_email, subject, body)


@durable_step
def notify_employee_leave_process(
    step_context,
    employee_email: str,
    leave_id: str,
    status: str,
):
    subject = "Leave Request Processed"
    body = f"<p>Your leave request with ID {leave_id} has been <b>{status}</b>.</p>"
    send_email(employee_email, subject, body)


def notify_manager(
    callback_id,
    step_context,
    manager_email: str,
    leave_id: str,
):
    subject = "Leave Request Submitted"
    body = f"<p>Leave request with ID {leave_id} has been submitted and is pending your approval.</p><p>Please approve or reject using the callback id below.</p><p><b>{callback_id}</b></p>"
    send_email(manager_email, subject, body)


def send_email(to_address: str, subject: str, body: str):
    html_body = f"<!DOCTYPE html><html><body><p><h3>Simple Leave Management</h3></p>{body}</body></html>"
    ses.send_email(
        Source=SYSTEM_FROM_EMAIL,
        Destination={"ToAddresses": [to_address]},
        Message={
            "Subject": {
                "Data": subject,
            },
            "Body": {
                "Html": {
                    "Charset": "UTF-8",
                    "Data": html_body,
                }
            },
        },
    )
