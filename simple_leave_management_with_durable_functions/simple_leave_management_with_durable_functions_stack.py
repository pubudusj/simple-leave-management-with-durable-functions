import os
from aws_cdk import (
    BundlingOptions,
    CfnOutput,
    Duration,
    Stack,
    aws_lambda as _lambda,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
)
from constructs import Construct
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class SimpleLeaveManagementWithDurableFunctionsStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Leaves DynamoDB table
        leaves_table = dynamodb.Table(
            self,
            "LeaveManagementTable",
            partition_key=dynamodb.Attribute(
                name="pk",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="sk",
                type=dynamodb.AttributeType.STRING,
            ),
        )

        # Create Leaves Lambda Durable Function
        create_leave_durable_function = _lambda.Function(
            self,
            "CreateLeavesDurableFunction",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="index.handler",
            code=_lambda.Code.from_asset("lambda/create_leave"),
            environment={
                "SYSTEM_FROM_EMAIL": os.environ["SYSTEM_FROM_EMAIL"],
                "MANAGER_EMAIL": os.environ["MANAGER_EMAIL"],
                "DDB_TABLE_NAME": leaves_table.table_name,
            },
            durable_config=_lambda.DurableConfig(execution_timeout=Duration.days(1)),
        )

        # add version and alias prod
        create_leave_durable_function_version = (
            create_leave_durable_function.current_version
        )
        create_leave_durable_function_alias = _lambda.Alias(
            self,
            "ProdAlias",
            alias_name="prod",
            version=create_leave_durable_function_version,
        )

        # Grant DynamoDB write permissions to create_leave_durable_function
        leaves_table.grant_write_data(create_leave_durable_function_alias)

        # Grant SES send email permissions to create_leave_durable_function
        create_leave_durable_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ses:SendEmail", "ses:SendRawEmail"],
                resources=["*"],
            )
        )

        # Proxy Lambda function to invoke the durable function
        create_leave_proxy_function = _lambda.Function(
            self,
            "CreateLeaveProxyFunction",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="index.handler",
            code=_lambda.Code.from_asset("lambda/create_leave_proxy"),
            timeout=Duration.seconds(10),
            environment={
                "DURABLE_FUNCTION_ARN": create_leave_durable_function_alias.function_arn,
            },
        )

        create_leave_url = create_leave_proxy_function.add_function_url(
            auth_type=_lambda.FunctionUrlAuthType.NONE,
        )

        # Grant invoke permissions to the proxy function
        create_leave_durable_function_alias.grant_invoke(create_leave_proxy_function)

        # Process Leave Lambda function to handle approval/rejection callbacks
        process_leave_function = _lambda.Function(
            self,
            "ProcessLeaveFunction",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="index.handler",
            code=_lambda.Code.from_asset(
                "lambda/process_leave",
                bundling=BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_13.bundling_image,
                    platform="linux/amd64",
                    command=[
                        "bash",
                        "-c",
                        "pip install -r requirements.txt -t /asset-output && cp -r . /asset-output",
                    ],
                ),
            ),
        )

        process_leave_url = process_leave_function.add_function_url(
            auth_type=_lambda.FunctionUrlAuthType.NONE,
        )

        process_leave_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "lambda:SendDurableExecutionCallbackSuccess",
                    "lambda:SendDurableExecutionCallbackFailure",
                ],
                resources=[
                    f"{create_leave_durable_function.function_arn}:*/durable-execution/*/*"
                ],
            )
        )

        # Output the Function URLs
        CfnOutput(
            self,
            "CreateLeaveFunctionUrl",
            value=create_leave_url.url,
        )
        CfnOutput(
            self,
            "ProcessLeaveFunctionUrl",
            value=process_leave_url.url,
        )
