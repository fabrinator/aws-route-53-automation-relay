import os, json

def get_event_file(file):
    file_path = os.path.realpath(__file__)
    json_sns = os.path.abspath(os.path.join(file_path, "../../../", "events/" + file))
    with open(json_sns) as file:
        data = json.load(file)
    return data

