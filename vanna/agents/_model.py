"""Shared model factory: DeepSeek for all agents."""
import os

from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider


def make_model():
    return OpenAIModel(
        os.environ.get('VANNA_MODEL', 'deepseek-chat'),
        provider=OpenAIProvider(
            base_url='https://api.deepseek.com',
            api_key=os.environ.get('DEEPSEEK_API_KEY', ''),
        ),
    )
