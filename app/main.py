import os
import json
import sys
from datetime import datetime, timedelta
from strands import Agent, tool
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from mcp_client.client import get_streamable_http_mcp_client
from model.load import load_model

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from infrastructure.load import load_dynamodb_table

app = BedrockAgentCoreApp()
log = app.logger

REGION = os.getenv("AWS_REGION")

mcp_client = get_streamable_http_mcp_client()

@tool
def log_meal(meal_type: str, foods: str, time: str, feeling: str = "") -> str:
    """
    Log meal data for tracking dietary patterns.

    Args:
        meal_type: Type of meal (e.g., "breakfast", "lunch", "dinner", "snack")
        foods: Description of foods eaten
        time: Time of meal in HH:MM format (e.g., "12:30")
        feeling: Optional - how you felt after eating
    """
    user_id = getattr(log_meal, '_current_user_id', 'default-user')
    table = load_dynamodb_table()
    timestamp = datetime.utcnow().isoformat()
    date = datetime.utcnow().date().isoformat()

    item = {
        'user_id': user_id,
        'timestamp_type': f"{timestamp}#meal",
        'date': date,
        'type': 'meal',
        'data': {
            'meal_type': meal_type.lower(),
            'foods': foods,
            'time': time,
            'feeling': feeling,
            'timestamp': timestamp
        }
    }

    table.put_item(Item=item)
    return f"Logged {meal_type} at {time}: {foods}"

@app.entrypoint
async def invoke(payload, context):
    session_id = getattr(context, 'session_id', 'default')
    user_id = 'default-user'
    log.info(f"Session: {session_id} | User: {user_id}")
    log_meal._current_user_id = user_id

    with mcp_client as client:
        tools = client.list_tools_sync()

        agent = Agent(
            model=load_model(),
            system_prompt="""
                You are a personal nutrition coach focused on helping improve dietary habits.

                Your role:
                - Track and remember patterns in meal choices and eating habits
                - Listen when the user shares what they eat and how they feel afterward
                - Ask clarifying questions to understand context
                - Identify patterns over time between food choices and how the user feels
                - Provide personalized, actionable recommendations based on observed patterns

                Guidelines:
                - Be supportive and non-judgmental
                - Focus on sustainable changes, not extreme diets
                - Consider meal timing, food combinations, and how they affect energy and mood
                - Remember previous conversations and build on them
                - When making recommendations, reference specific patterns you have observed
                - Ask permission before giving advice
                - Only use the log_meal tool when the user reports a specific meal they actually ate (with foods and time). Do NOT log meals when the user is sharing general preferences or favorites.
                - Do not include <thinking> tags or any internal reasoning in your responses. Respond directly to the user.
            """,
            tools=[log_meal] + tools
        )

        prompt = payload.get("prompt") if isinstance(payload, dict) else payload
        stream = agent.stream_async(prompt)

        async for event in stream:
            if "data" in event and isinstance(event["data"], str):
                yield event["data"]

if __name__ == "__main__":
    app.run()
