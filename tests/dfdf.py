from dotenv import load_dotenv
load_dotenv()

from flow_engine.secrets.service import decrypt_secret_by_name
print(decrypt_secret_by_name("pwd1", profile="default"))