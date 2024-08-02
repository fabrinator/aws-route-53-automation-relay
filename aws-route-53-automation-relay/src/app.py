import cfnresponse
import json, boto3, os
from datetime import datetime

sns_arn = os.environ['SNS_ARN']

class DateTimeEncoder(json.JSONEncoder): # pragma: no cover
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def build_terraform_payload(event):
    if event["tf"]["prev_input"]:
        action = "delete"
        record_name = event.get("record_name")
        dns_zone = event.get("dns_zone")
        record_type = event.get("record_type")
        record_value = event.get("record_value")
        response = send_message_sns(action, record_name, dns_zone, record_type, record_value)
        print(json.dumps(response, indent=2, cls=DateTimeEncoder))
    action = event["tf"]["action"].lower()
    record_name = event.get("record_name")
    dns_zone = event.get("dns_zone")
    record_type = event.get("record_type")
    record_value = event.get("record_value")
    response = send_message_sns(action, record_name, dns_zone, record_type, record_value)
    print(json.dumps(response, indent=2, cls=DateTimeEncoder))
    return response


def build_cloudformation_payload(event):
    if "OldResourceProperties" in event:
        action = "delete"
        record_name = event["OldResourceProperties"].get("record_name")
        dns_zone = event["OldResourceProperties"].get("dns_zone")
        record_type = event["OldResourceProperties"].get("record_type")
        record_value = event["OldResourceProperties"].get("record_value")
        response = send_message_sns(action, record_name, dns_zone, record_type, record_value)
        print(json.dumps(response, indent=2, cls=DateTimeEncoder))
    action = event["RequestType"].lower()
    record_name = event["ResourceProperties"].get("record_name")
    dns_zone = event["ResourceProperties"].get("dns_zone")
    record_type = event["ResourceProperties"].get("record_type")
    record_value = event["ResourceProperties"].get("record_value")
    response = send_message_sns(action, record_name, dns_zone, record_type, record_value)
    print(json.dumps(response, indent=2, cls=DateTimeEncoder))
    return response


def send_message_sns(action, record_name, dns_zone, record_type, record_value):
    arguments = locals()
    print(arguments)
    if None in arguments.values():
        raise ValueError("Missing an argument for the message")
    message = json.dumps(arguments)
    sns = boto3.client('sns')
    response = sns.publish(
        TopicArn=sns_arn,
        Message=message,
        Subject="Automation"
    )
    return response


def lambda_handler(event, context):
    external_tool = ""
    if "RequestType" in event:
        external_tool = "CF"
        response = build_cloudformation_payload(event)
    elif "tf" in event:
        response = build_terraform_payload(event)
    else:
        return {
            "statusCode": 500,
            "body": json.dumps({
                "message": "Invalid RequestType"
            })
        }

    if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
        if external_tool == "CF":
            cfnresponse.send(event, context, cfnresponse.SUCCESS, "", "CustomResourcePhysicalID")
        return {
            "statusCode": 200,
            "body": json.dumps(response, cls=DateTimeEncoder)
        }
    else: # pragma: no cover
        if external_tool == "CF":
            cfnresponse.send(event, context, cfnresponse.FAILED, "", "CustomResourcePhysicalID")
        return {
            "statusCode": 500,
            "body": json.dumps(response, cls=DateTimeEncoder)
        }
