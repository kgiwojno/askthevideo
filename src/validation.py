"""Input validation helpers."""

from src.transcript import extract_video_id


def validate_youtube_url(url: str) -> str:
    """Extract and validate a YouTube video ID from a URL.

    Returns:
        video_id string

    Raises:
        ValueError: if URL is invalid
    """
    return extract_video_id(url)


def validate_question(text: str) -> str:
    """Validate a question string.

    Returns:
        stripped question text

    Raises:
        ValueError: if empty or over 500 characters
    """
    text = text.strip()
    if not text:
        raise ValueError("Question cannot be empty.")
    if len(text) > 500:
        raise ValueError("Question must be 500 characters or fewer.")
    return text
