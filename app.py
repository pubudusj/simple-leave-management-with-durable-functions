#!/usr/bin/env python3
import aws_cdk as cdk

from simple_leave_management_with_durable_functions.simple_leave_management_with_durable_functions_stack import (  # pylint: disable=line-too-long
    SimpleLeaveManagementWithDurableFunctionsStack,
)


app = cdk.App()
SimpleLeaveManagementWithDurableFunctionsStack(
    app,
    "SimpleLeaveManagementWithDurableFunctionsStack",
)

app.synth()
