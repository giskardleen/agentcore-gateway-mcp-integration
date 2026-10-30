from strands.models import BedrockModel

MODEL_ID = "us.amazon.nova-pro-v1:0"

def load_model() -> BedrockModel:
    """Get Bedrock model client."""
    return BedrockModel(model_id=MODEL_ID)
