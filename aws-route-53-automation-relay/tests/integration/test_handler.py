import json, pytest, boto3, os, zipfile, re
from datetime import datetime
from .events import get_event_file
from moto import mock_aws
from moto.server import ThreadedMotoServer

script_path = os.path.realpath(__file__)

@pytest.fixture(scope='module')
def start_moto_server():
    server = ThreadedMotoServer()
    server.start()
    yield

def zip_code():
    directory_path = os.path.abspath(os.path.join(script_path, "../../../.aws-sam/build/ThisFunction"))
    change_client_endpoint_boto3(directory_path)
    with zipfile.ZipFile('app_file.zip', 'w', zipfile.ZIP_DEFLATED) as zip:
        for root, dirs, files in os.walk(directory_path):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, start=directory_path)
                zip.write(file_path, arcname=arcname)

@pytest.fixture(scope='module')
def create_aws_resources():
    zip_code()
    stack_name = "unitest"
    lambda_role_name = stack_name + "-lambda-role"
    lambda_name = stack_name + "-lambda"
    sns_name = stack_name + "-sns"
    with mock_aws():
        """Working in the regular account from moto"""
        client_iam = boto3.client('iam')
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
        assume_role_lambda = client_iam.create_role(
            RoleName=lambda_role_name, AssumeRolePolicyDocument=json.dumps(trust_policy)
        )

        """Simulate multi account environment and create the SNS in another account."""
        os.environ["MOTO_ACCOUNT_ID"] = "111111111111"
        client_sns = boto3.client("sns")
        sns_topic = client_sns.create_topic(Name=sns_name)
        sns_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "AWS": assume_role_lambda["Role"]["Arn"]
                    },
                    "Action": "SNS:Publish",
                    "Resource": sns_topic["TopicArn"]
                }
            ]
        }
        client_sns.set_topic_attributes(
            TopicArn=sns_topic["TopicArn"],
            AttributeName='Policy',
            AttributeValue=json.dumps(sns_policy)
        )
        del os.environ["MOTO_ACCOUNT_ID"]

        """Working in the regular account from moto"""
        client_lambda = boto3.client("lambda")
        lambda_resource = client_lambda.create_function(
            FunctionName=lambda_name,
            Runtime="python3.10",
            Handler='app.lambda_handler',
            Role=assume_role_lambda["Role"]["Arn"],
            PackageType="Zip",
            Code={
                'ZipFile': open('./app_file.zip', 'rb').read()
            },
            Environment={
                'Variables': {
                    'SNS_ARN': sns_topic["TopicArn"]
                }
            },
        )

        yield {
            "functionArn": lambda_resource["FunctionArn"],
        }

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def change_client_endpoint_boto3(directory_path):
    file_path = directory_path + "/app.py"
    def replace_with_additional_text(match):
        current_content = match.group(1)
        new_content = current_content + """, endpoint_url=os.environ.get("MOTO_HOST") + ":" + os.environ.get("MOTO_PORT")"""
        return f"boto3.client({new_content})"

    with open(file_path, 'r') as file:
        text = file.read()

    modified_text = re.sub(r"boto3.client\((.*)\)", replace_with_additional_text, text)

    with open(file_path, 'w') as file:
        file.write(modified_text)

@mock_aws
def test_lambda_invoke_terraform(create_aws_resources, start_moto_server):
    event_invoke = get_event_file("event-create-terraform.json")
    client = boto3.client("lambda")
    response = client.invoke(
        FunctionName=create_aws_resources["functionArn"],
        InvocationType='RequestResponse',
        Payload=json.dumps(event_invoke),
        LogType="Tail"
    )
    payload_stream = response['Payload']
    payload_string = payload_stream.read().decode('utf-8')
    payload_data = json.loads(payload_string)
    assert response["ResponseMetadata"]["HTTPStatusCode"] == 200
    assert "FunctionError" not in response
    assert payload_data["statusCode"] == 200

@mock_aws
def test_lambda_invoke_cloudformation(create_aws_resources, start_moto_server):
    event_invoke = get_event_file("event-delete-custom-cf.json")
    client = boto3.client("lambda")
    response = client.invoke(
        FunctionName=create_aws_resources["functionArn"],
        InvocationType='RequestResponse',
        Payload=json.dumps(event_invoke),
        LogType="Tail"
    )
    payload_stream = response['Payload']
    payload_string = payload_stream.read().decode('utf-8')
    payload_data = json.loads(payload_string)
    assert response["ResponseMetadata"]["HTTPStatusCode"] == 200
    assert "FunctionError" not in response
    assert payload_data["statusCode"] == 200

@mock_aws
def test_lambda_invoke_cloudformation_bad(create_aws_resources, start_moto_server):
    """The event is incomplete, lambda should return some failure"""
    event_invoke = get_event_file("event-create-custom-cf-bad.json")
    client = boto3.client("lambda")
    response = client.invoke(
        FunctionName=create_aws_resources["functionArn"],
        InvocationType='RequestResponse',
        Payload=json.dumps(event_invoke),
        LogType="Tail"
    )
    payload_stream = response['Payload']
    payload_string = payload_stream.read().decode('utf-8')
    payload_data = json.loads(payload_string)
    assert response["ResponseMetadata"]["HTTPStatusCode"] == 200
    assert "FunctionError" in response
    assert payload_data["errorType"] == "ValueError"
    assert payload_data["errorMessage"] == 'Missing an argument for the message'


# @mock_aws
# def test_lamda_two(start_moto_server):
#     client = boto3.client("lambda")
#     response = client.list_functions()
#     print("list_functions",response)
