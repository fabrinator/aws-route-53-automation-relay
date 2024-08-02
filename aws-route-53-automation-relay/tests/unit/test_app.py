import pytest, boto3, os, json
from moto import mock_aws
from .events import get_event_file


@pytest.fixture(scope='module')
def create_aws_resources():
    stack_name = "unitest"
    sns_name = stack_name + "-sns"
    with mock_aws():
        """Simulate multi account environment and create the SNS in another account."""
        # os.environ["MOTO_ACCOUNT_ID"] = "111111111111"
        client_sns = boto3.client("sns")
        sns_topic = client_sns.create_topic(Name=sns_name)
        sns_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "AWS": "root"
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
        # del os.environ["MOTO_ACCOUNT_ID"]

        yield {
            "snsArn": sns_topic["TopicArn"],
        }


class Context:
    log_stream_name = "unittest"

@mock_aws
def test_lambda_handler_terraform(create_aws_resources, monkeypatch):
    monkeypatch.setenv('SNS_ARN', create_aws_resources["snsArn"])
    from src import app
    actions_to_test = ["create", "update", "delete"]
    for action in actions_to_test:
        event_invoke = get_event_file("event-{}-terraform.json".format(action))
        response = app.lambda_handler(event_invoke, "")
        data = json.loads(response["body"])
        assert response["statusCode"] == 200
        assert data["ResponseMetadata"]["HTTPStatusCode"] == 200
@mock_aws
def test_lambda_handler_cloudformation(create_aws_resources, monkeypatch):
    monkeypatch.setenv('SNS_ARN', create_aws_resources["snsArn"])
    from src import app
    actions_to_test = ["create", "update", "delete"]
    for action in actions_to_test:
        event_invoke = get_event_file("event-{}-custom-cf.json".format(action))
        response = app.lambda_handler(event_invoke, Context)
        data = json.loads(response["body"])
        assert response["statusCode"] == 200
        assert data["ResponseMetadata"]["HTTPStatusCode"] == 200

@mock_aws
def test_lambda_handler_cloudformation_bad(create_aws_resources, monkeypatch):
    monkeypatch.setenv('SNS_ARN', create_aws_resources["snsArn"])
    from src import app
    event_invoke = get_event_file("event-create-custom-cf-bad.json")
    with pytest.raises(ValueError):
        app.lambda_handler(event_invoke, Context)

@mock_aws
def test_lambda_handler_terraform_bad(create_aws_resources, monkeypatch):
    monkeypatch.setenv('SNS_ARN', create_aws_resources["snsArn"])
    from src import app
    event_invoke = get_event_file("event-create-terraform-bad.json")
    with pytest.raises(ValueError):
        app.lambda_handler(event_invoke, Context)


@mock_aws
def test_lambda_handler_random_event(create_aws_resources, monkeypatch):
    monkeypatch.setenv('SNS_ARN', create_aws_resources["snsArn"])
    from src import app
    response = app.lambda_handler({}, Context)
    data = json.loads(response["body"])
    assert response["statusCode"] == 500
    assert data["message"] == "Invalid RequestType"

