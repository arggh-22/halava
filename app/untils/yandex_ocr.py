import base64
import requests
import config
import loaders


def analyze_file(file_path):
    try:
        with open(file_path, "rb") as file:
            file_content = file.read()
    except IOError:
        return

    # Convert file content to base64
    content = base64.b64encode(file_content)
    content_str = content.decode('utf-8')

    # Determine the mime type based on file extension
    mime_type = "image/jpeg"
    if file_path.lower().endswith(".pdf"):
        mime_type = "application/pdf"
    elif file_path.lower().endswith(".png"):
        mime_type = "image/png"

    # Construct request body
    request_body = {
        "folderId": config.FOLDER_ID,
        "analyze_specs": {
            "content": content_str,
            "mime_type": mime_type,
            "features": {
                "type": "TEXT_DETECTION",
                "text_detection_config": {
                    "language_codes": ["en", "ru"]
                }
            }
        }
    }

    try:
        response = requests.post(config.URL_VISION_API, headers=loaders.request_header, json=request_body)
        response.raise_for_status()
        response_data = response.json()
    except requests.exceptions.HTTPError:
        return
    except requests.exceptions.RequestException:
        return

    words = json_extract(response_data, 'text')
    return " ".join(words)


def json_extract(_object, key):
    array = []

    def extract(obj, arr, _key):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    extract(v, arr, _key)
                elif k == _key:
                    arr.append(v)
        elif isinstance(obj, list):
            for item in obj:
                extract(item, arr, _key)
        return arr

    values = extract(_object, array, key)
    return values


#  _    _        _      _____              _
# | |  | |      | |    |_   _|            | |
# | |  | |  ___ | |__    | |    ___   ___ | |__
# | |/\| | / _ \| '_ \   | |   / _ \ / __|| '_ \
# \  /\  /|  __/| |_) |  | |  |  __/| (__ | | | |
#  \/  \/  \___||_.__/   \_/   \___| \___||_| |_|
