import torch
from transformers import pipeline
from openai import OpenAI
from anthropic import Anthropic
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


def load_model(model_name):
    """
    Load a designated open-source LLM from Hugging Face using pipeline.
    
    Args:
    model_name (str): The name of the model on Hugging Face.
    cache_dir (str): The directory to cache the model.

    Returns:
    pipeline: The loaded model pipeline for text generation.
    """
    return pipeline("text-generation", model=model_name, device_map="auto")


def generate_summary_hf(model_pipeline, prompt, **kwargs):
    """
    Generate a summary using the loaded model pipeline.
    
    Args:
    model_pipeline: The loaded language model pipeline.
    prompt (str): The input prompt for summarization.
    max_tokens (int): Maximum number of new tokens to generate.
    
    Returns:
    str: The generated summary.
    """
    output = model_pipeline(prompt, **kwargs)
    generated_text = output[0]['generated_text']
    # Extract only the answer (summary) by removing the original prompt
    summary = generated_text[len(prompt):].strip()
    return summary


def generate_summary_openai(prompt, engine, **kwargs):
    """Generate a summary using OpenAI's API with retry logic for rate limits."""
    openai = OpenAI()
    
    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        stop=stop_after_attempt(5)
    )
    def _generate_with_retry():
        chat_completion = openai.chat.completions.create(
            model=engine,
            messages=[{"role": "user", "content": prompt}],
            **kwargs
        )
        return chat_completion.choices[0].message.content.strip()
        
    return _generate_with_retry()


def generate_summary_claude(prompt, engine, **kwargs):
    """Generate a summary using Claude's API with retry logic for rate limits."""
    anthropic = Anthropic()
    
    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        stop=stop_after_attempt(5)
    )
    def _generate_with_retry():
        response = anthropic.messages.create(
            model=engine,
            messages=[{"role": "user", "content": prompt}],
            **kwargs
        )
        return response.content[0].text.strip()
        
    return _generate_with_retry()

def summarize_text(prefix, suffix, text, provider, model_name, **kwargs):
    """
    Main function to summarize text using a specified model or API.
    
    Args:
    text (str): The text to summarize.
    provider (str): The provider of the model (e.g., "openai", "claude", "hf").
    model_name (str): The name of the model to use (e.g., "facebook/opt-350m", "chatgpt-4o").
    cache_dir (str, optional): The directory to cache the model (for Hugging Face models).
    
    Returns:
    str: The generated summary.
    """
    prompt = f"{prefix}\n\n{text}\n\n{suffix}"
    
    if provider.lower() == "openai":
        return generate_summary_openai(prompt, model_name, **kwargs)
    elif provider.lower() == "claude":
        return generate_summary_claude(prompt, model_name, **kwargs)
    elif provider.lower() == "hf":
        model_pipeline = load_model(model_name)
        return generate_summary_hf(model_pipeline, prompt, **kwargs)
    else:
        raise ValueError(f"Unsupported provider: {provider}")
